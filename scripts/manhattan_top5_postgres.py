
# manhattan_top5_postgres.py
# Tim kiem Top 5 chi bang Manhattan + Z-score.
#
# Che do:
#   loo    : 645 truy van, moi truy van tim trong 644 file con lai
#   test   : test_dataset (160 file), tim trong 645 file CSDL
#   search : tim Top 5 cho mot file bat ky
#
# KHONG sua PostgreSQL hoac file am thanh.

import argparse
import getpass
import json
import os
import shutil
from collections import defaultdict
from pathlib import Path

import numpy as np

from search_top5_postgres import load_database, path_key
from batch_test_80_postgres import (
    extract_with_fallback,
    path_from_root,
    select_test_files,
    write_csv,
)


METHOD = "manhattan_z"

QUERY_FIELDS = [
    "query_file",
    "query_path",
    "actual_instrument",
    "top1_instrument",
    "top1_correct",
    "correct_in_top5",
    "precision_at_5",
    "top5_instruments",
    "top5_distances",
]

TOP5_FIELDS = [
    "query_file",
    "actual_instrument",
    "rank",
    "audio_id",
    "result_filename",
    "result_instrument",
    "result_path",
    "manhattan_distance",
    "correct",
]

SUMMARY_FIELDS = [
    "method",
    "queries",
    "top1_correct",
    "top1_accuracy",
    "top5_correct",
    "precision_at_5",
]

CLASS_FIELDS = [
    "instrument",
    "queries",
    "top1_correct",
    "top1_accuracy",
    "top5_correct",
    "precision_at_5",
]


def normalize_reference(X):
    """
    Z-score tung chieu.
    mean va std chi tinh tu cac vector trong PostgreSQL.
    """
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std = np.where(std < 1e-12, 1.0, std)
    Z = (X - mean) / std
    return Z, mean, std


def manhattan_distances(Z, query_z):
    """
    d(q, x) = sum_j |zq_j - zx_j|
    """
    return np.sum(
        np.abs(Z - query_z),
        axis=1,
    )


def search_topk(
    query_name,
    query_path,
    actual,
    query_z,
    excluded_indices,
    Z,
    ids,
    labels,
    rows,
    top_k,
    query_results,
    top5_results,
):
    distances = manhattan_distances(Z, query_z)

    # Loai file truy van neu no nam trong CSDL.
    for idx in excluded_indices:
        distances[idx] = np.inf

    candidates = int(np.isfinite(distances).sum())
    if candidates < top_k:
        raise ValueError(
            f"Chi con {candidates} ung vien, "
            f"khong du Top {top_k}"
        )

    # Xep hang theo khoang cach tang dan.
    # Neu bang nhau, uu tien audio_id nho hon.
    ranking = np.lexsort((ids, distances))[:top_k]

    predictions = [str(labels[i]) for i in ranking]
    selected_distances = [
        float(distances[i]) for i in ranking
    ]

    if actual is not None:
        correct1 = int(predictions[0] == actual)
        correct_k = sum(
            label == actual for label in predictions
        )
        precision_k = correct_k / top_k
    else:
        correct1 = ""
        correct_k = ""
        precision_k = ""

    query_results.append({
        "query_file": query_name,
        "query_path": str(query_path),
        "actual_instrument": actual or "",
        "top1_instrument": predictions[0],
        "top1_correct": correct1,
        "correct_in_top5": correct_k,
        "precision_at_5": precision_k,
        "top5_instruments": " | ".join(predictions),
        "top5_distances": " | ".join(
            f"{d:.6f}" for d in selected_distances
        ),
    })

    for rank, idx in enumerate(ranking, start=1):
        top5_results.append({
            "query_file": query_name,
            "actual_instrument": actual or "",
            "rank": rank,
            "audio_id": int(rows[idx][0]),
            "result_filename": str(rows[idx][1]),
            "result_instrument": str(labels[idx]),
            "result_path": str(rows[idx][2]),
            "manhattan_distance": float(distances[idx]),
            "correct": (
                int(labels[idx] == actual)
                if actual is not None else ""
            ),
        })

    return predictions, selected_distances, candidates


def make_summary(records):
    n = len(records)
    if n == 0:
        return [], []

    correct1 = sum(
        int(r["top1_correct"]) for r in records
    )
    correct5 = sum(
        int(r["correct_in_top5"]) for r in records
    )

    summary = [{
        "method": METHOD,
        "queries": n,
        "top1_correct": correct1,
        "top1_accuracy": correct1 / n,
        "top5_correct": correct5,
        "precision_at_5": correct5 / (5 * n),
    }]

    grouped = defaultdict(list)
    for r in records:
        grouped[r["actual_instrument"]].append(r)

    by_class = []
    for instrument, items in sorted(grouped.items()):
        m = len(items)
        c1 = sum(
            int(r["top1_correct"]) for r in items
        )
        c5 = sum(
            int(r["correct_in_top5"]) for r in items
        )

        by_class.append({
            "instrument": instrument,
            "queries": m,
            "top1_correct": c1,
            "top1_accuracy": c1 / m,
            "top5_correct": c5,
            "precision_at_5": c5 / (5 * m),
        })

    return summary, by_class


def main():
    parser = argparse.ArgumentParser(
        description="Top-5 Manhattan + Z-score, 60D"
    )

    parser.add_argument(
        "--mode",
        choices=["loo", "test", "search"],
        default=None,
    )
    parser.add_argument("--query", default="")
    parser.add_argument(
        "--test-dir", default="test_dataset"
    )
    parser.add_argument(
        "--per-class", type=int, default=0
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--ffmpeg", default="")
    parser.add_argument(
        "--output", default="output/manhattan_60d"
    )

    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument(
        "--dbname", default="wind_instruments_db"
    )
    parser.add_argument("--user", default="postgres")

    args = parser.parse_args()

    # Neu truyen --query ma khong co --mode,
    # tu dong chuyen sang che do search.
    mode = args.mode or (
        "search" if args.query else "loo"
    )

    if args.per_class < 0:
        parser.error("--per-class khong duoc am")

    if args.top < 1:
        parser.error("--top phai >= 1")

    if mode != "search" and args.top != 5:
        parser.error(
            "Che do loo/test su dung --top 5 "
            "de tinh Precision@5"
        )

    output = path_from_root(args.output) / mode

    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if ffmpeg:
        if (
            not Path(ffmpeg).is_file()
            and shutil.which(ffmpeg) is None
        ):
            parser.error(
                f"Khong tim thay FFmpeg: {ffmpeg}"
            )

    if mode == "test":
        test_root = path_from_root(args.test_dir)
        if not test_root.is_dir():
            parser.error(
                f"Khong thay test_dataset: {test_root}"
            )
        if output == test_root or test_root in output.parents:
            parser.error(
                "Khong duoc luu output trong test_dataset"
            )

    if mode == "search":
        if not args.query:
            parser.error(
                "Can --query khi chay mode search"
            )
        query_path = path_from_root(args.query)
        if not query_path.is_file():
            parser.error(
                f"Khong tim thay file: {query_path}"
            )

    password = os.environ.get("PGPASSWORD")
    if password is None:
        password = getpass.getpass(
            "Mat khau PostgreSQL (khong hien thi): "
        )

    print("\n[1/3] Ket noi va doc PostgreSQL...")
    rows, X = load_database(args, password)

    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 2 or X.shape[1] != 60:
        raise ValueError(
            f"Vector PostgreSQL khong dung 60D: {X.shape}"
        )

    if not np.isfinite(X).all():
        raise ValueError("CSDL co NaN hoac Inf")

    if len(rows) < args.top + 1:
        raise ValueError(
            "CSDL khong du file de tim Top 5"
        )

    ids = np.array(
        [int(row[0]) for row in rows],
        dtype=np.int64,
    )
    labels = np.array(
        [str(row[3]) for row in rows]
    )

    Z, mean, std = normalize_reference(X)

    print(f"Da doc {len(rows)} file, 60 dac trung.")
    print("Khoang cach: MANHATTAN")
    print("Chuan hoa: Z-SCORE")

    query_results = []
    top5_results = []
    errors = []
    selected_count = 0

    print("\n[2/3] Bat dau tim kiem...")

    if mode == "loo":
        selected_count = len(rows)

        for i, row in enumerate(rows):
            # Dung vector da luu trong PostgreSQL.
            # Loai chinh file do khi xep hang.
            search_topk(
                query_name=str(row[1]),
                query_path=str(row[2]),
                actual=str(labels[i]),
                query_z=Z[i],
                excluded_indices=[i],
                Z=Z,
                ids=ids,
                labels=labels,
                rows=rows,
                top_k=5,
                query_results=query_results,
                top5_results=top5_results,
            )

            if (
                (i + 1) % 25 == 0
                or i + 1 == len(rows)
            ):
                print(
                    f"Leave-One-Out: {i+1}/{len(rows)}",
                    flush=True,
                )

    elif mode == "test":
        classes = sorted(
            set(labels), key=str.casefold
        )

        selection, _ = select_test_files(
            test_root,
            classes,
            per_class=args.per_class,
            seed=args.seed,
        )

        selected_count = len(selection)
        if not selection:
            raise ValueError(
                "Khong tim thay file test hop le"
            )

        print(
            f"So file test duoc chon: {selected_count}"
        )

        db_paths = {
            path_key(str(row[2])) for row in rows
        }

        for number, (path, actual) in enumerate(
            selection, start=1
        ):
            print(
                f"[{number}/{selected_count}] "
                f"{actual} / {path.name}",
                flush=True,
            )

            try:
                if path_key(str(path)) in db_paths:
                    raise ValueError(
                        "File test trung duong dan CSDL"
                    )

                q = np.asarray(
                    extract_with_fallback(path, ffmpeg),
                    dtype=np.float64,
                )

                if (
                    q.shape != (60,)
                    or not np.isfinite(q).all()
                ):
                    raise ValueError(
                        "Vector file test khong hop le"
                    )

                qz = (q - mean) / std

                predictions, distances, _ = search_topk(
                    query_name=path.name,
                    query_path=path,
                    actual=actual,
                    query_z=qz,
                    excluded_indices=[],
                    Z=Z,
                    ids=ids,
                    labels=labels,
                    rows=rows,
                    top_k=5,
                    query_results=query_results,
                    top5_results=top5_results,
                )

                correct5 = sum(
                    name == actual for name in predictions
                )

                print(
                    f"   Top-1: {predictions[0]} "
                    f"| dung {correct5}/5 "
                    f"| P@5={correct5/5:.0%}"
                )

            except Exception as exc:
                print("   LOI:", exc)
                errors.append({
                    "query_file": path.name,
                    "error": str(exc),
                })

    else:
        q = np.asarray(
            extract_with_fallback(query_path, ffmpeg),
            dtype=np.float64,
        )

        if (
            q.shape != (60,)
            or not np.isfinite(q).all()
        ):
            raise ValueError(
                "Vector truy van khong hop le"
            )

        qz = (q - mean) / std
        selected_count = 1

        # Neu truy van la mot file nam trong 645 file:
        # loai chinh no khoi danh sach ung vien.
        key = path_key(str(query_path))
        excluded = [
            i for i, row in enumerate(rows)
            if path_key(str(row[2])) == key
        ]

        predictions, distances, candidates = search_topk(
            query_name=query_path.name,
            query_path=query_path,
            actual=None,
            query_z=qz,
            excluded_indices=excluded,
            Z=Z,
            ids=ids,
            labels=labels,
            rows=rows,
            top_k=args.top,
            query_results=query_results,
            top5_results=top5_results,
        )

        print(f"So ung vien: {candidates}")
        print("\nTOP KET QUA MANHATTAN:")
        for result in top5_results:
            print(
                f"#{result['rank']} "
                f"[{result['result_instrument']}] "
                f"{result['result_filename']} "
                f"| d={result['manhattan_distance']:.6f}"
            )

    print("\n[3/3] Luu ket qua...")

    output.mkdir(parents=True, exist_ok=True)

    write_csv(
        output / "chi_tiet_truy_van.csv",
        query_results,
        QUERY_FIELDS,
    )
    write_csv(
        output / "top5_chi_tiet.csv",
        top5_results,
        TOP5_FIELDS,
    )
    write_csv(
        output / "errors.csv",
        errors,
        ["query_file", "error"],
    )

    if mode == "search":
        summary, by_class = [], []
    else:
        summary, by_class = make_summary(
            query_results
        )

    write_csv(
        output / "tong_hop.csv",
        summary,
        SUMMARY_FIELDS,
    )
    write_csv(
        output / "theo_nhac_cu.csv",
        by_class,
        CLASS_FIELDS,
    )

    metadata = {
        "mode": mode,
        "method": METHOD,
        "reference_files": len(rows),
        "selected_queries": selected_count,
        "successful_queries": len(query_results),
        "failed_queries": len(errors),
        "feature_dimensions": 60,
        "normalization":
            "Z-score fit from PostgreSQL reference vectors",
        "distance":
            "sum(abs(z_query - z_reference))",
        "loo_note":
            "Exclude the query from search candidates. "
            "Normalization statistics use all reference vectors.",
    }

    (output / "metadata.json").write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n========== TONG KET ==========")

    if summary:
        result = summary[0]

        print(
            f"Top-1 Accuracy: "
            f"{result['top1_accuracy']:.2%} "
            f"({result['top1_correct']}/{result['queries']})"
        )

        print(
            f"Precision@5: "
            f"{result['precision_at_5']:.2%} "
            f"({result['top5_correct']}/"
            f"{5*result['queries']})"
        )
    else:
        print(
            f"Da tim Top {args.top} "
            f"bang Manhattan."
        )

    print("So file loi:", len(errors))
    print("Ket qua luu tai:", output)

    if (
        mode == "test"
        and selected_count == 160
        and len(errors) == 0
    ):
        if (
            summary[0]["top1_correct"] == 51
            and summary[0]["top5_correct"] == 187
        ):
            print(
                "[OK] Ket qua khop lan kiem thu "
                "Manhattan truoc do."
            )
        else:
            print(
                "[CANH BAO] Ket qua khac moc "
                "51/160 va 187/800. "
                "Can kiem tra du lieu/thu vien."
            )


if __name__ == "__main__":
    main()
