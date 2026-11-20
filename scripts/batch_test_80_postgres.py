"""Kiem thu hang loat Top-5 cho 16 thu muc nhac cu (mac dinh 5 file/nhac cu).

CHAY:
    python batch_test_80_postgres.py --test-dir "test_dataset" --per-class 5

Cau truc:
    test_dataset/Flute/*.mp3
    test_dataset/Trumpet/*.wav
    test_dataset/English Horn/*.m4a
    ... (16 thu muc giong nhan trong PostgreSQL)

Dung lai ham extract_vector() cua extract_features_60d.py, dung cung Z-score
va Euclid nhu search_top5_postgres.py. Doc CSDL mot lan, nhap mat khau mot lan.
KHONG SUA CSDL, KHONG DOI TEN/XOA FILE TEST.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

from demo_app.extract_features_60d import extract_vector
from search_top5_postgres import GROUPS, load_database, path_key

ROOT = Path(__file__).resolve().parent
EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".aif", ".aiff",
    ".wma", ".opus", ".webm", ".mp4"
}


def path_from_root(text: str) -> Path:
    path = Path(text).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


def normalize_label(name: str) -> str:
    # English_Horn, English Horn, english-horn -> cung nhan.
    return "".join(c.casefold() for c in name if c.isalnum())


def write_csv(path: Path, records: list[dict], headers: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)


def select_test_files(folder: Path, known_instruments: list[str], per_class: int,
                      seed: int) -> tuple[list[tuple[Path, str]], dict]:
    labels = {normalize_label(label): label for label in known_instruments}
    grouped: dict[str, list[Path]] = defaultdict(list)
    unexpected: list[str] = []
    ignored_root_files: list[str] = []

    for candidate in sorted(folder.rglob("*"), key=lambda p: str(p).casefold()):
        if not candidate.is_file() or candidate.suffix.casefold() not in EXTENSIONS:
            continue
        rel_parts = candidate.relative_to(folder).parts
        if len(rel_parts) < 2:
            ignored_root_files.append(str(candidate))
            continue
        top_dir = rel_parts[0]
        label = labels.get(normalize_label(top_dir))
        if label is None:
            unexpected.append(str(candidate.relative_to(folder)))
            continue
        grouped[label].append(candidate.resolve())

    if unexpected:
        examples = "\n".join("  - " + p for p in unexpected[:12])
        raise ValueError(
            "Co file am thanh trong thu muc khong khop 16 nhan nhac cu o CSDL:\n"
            + examples + ("\n  ..." if len(unexpected) > 12 else "")
            + "\nHay doi ten THU MUC nhac cu cho phu hop, khong can doi ten file."
        )

    selection: list[tuple[Path, str]] = []
    report = {}
    rng = random.Random(seed)
    for label in sorted(known_instruments, key=str.casefold):
        candidates = sorted(grouped[label], key=lambda p: str(p).casefold())
        picked = (rng.sample(candidates, min(per_class, len(candidates)))
                  if per_class > 0 else candidates[:])
        picked.sort(key=lambda p: str(p).casefold())
        report[label] = {"available": len(candidates), "selected": len(picked)}
        selection.extend((p, label) for p in picked)
    return selection, {"by_instrument": report, "ignored_root_files": ignored_root_files}


def extract_with_fallback(path: Path, ffmpeg_path: str | None) -> np.ndarray:
    """Thu truc tiep; neu codec khong doc duoc thi nho FFmpeg giai ma WAV tam."""
    try:
        return np.asarray(extract_vector(path), dtype=np.float64)
    except Exception as original_error:
        if not ffmpeg_path:
            raise original_error
        with tempfile.TemporaryDirectory(prefix="wind_batch_audio_") as tmpdir:
            temp_wav = Path(tmpdir) / "decoded.wav"
            process = subprocess.run(
                [ffmpeg_path, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(path), "-vn", "-ac", "1", "-ar", "22050",
                 "-c:a", "pcm_s16le", str(temp_wav)],
                capture_output=True, text=True, check=False
            )
            if process.returncode != 0 or not temp_wav.is_file() or temp_wav.stat().st_size < 100:
                detail = process.stderr.strip()[-600:]
                raise RuntimeError(
                    f"Khong doc duoc file; FFmpeg cung khong giai ma duoc: {detail}"
                ) from original_error
            return np.asarray(extract_vector(temp_wav), dtype=np.float64)


def run_batch(rows, X: np.ndarray, selection: list[tuple[Path, str]],
              ffmpeg_path: str | None, top_k: int = 5,
              save_all: bool = False):
    """Core tach rieng de kiem thu; ket qua phu hop search_top5_postgres.py."""
    if top_k <= 0 or len(rows) < top_k:
        raise ValueError("CSDL khong du file de lay Top-K")
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std_safe = np.where(std < 1e-12, 1.0, std)
    Z = (X - mean) / std_safe
    ids = np.asarray([int(row[0]) for row in rows], dtype=np.int64)
    labels = [str(row[3]) for row in rows]
    db_paths = [path_key(str(row[2])) for row in rows]

    per_query: list[dict] = []
    top5: list[dict] = []
    failures: list[dict] = []
    all_distances: list[dict] = []

    for number, (query_file, truth) in enumerate(selection, 1):
        print(f"[{number}/{len(selection)}] {truth} / {query_file.name}", flush=True)
        try:
            q = extract_with_fallback(query_file, ffmpeg_path)
            if q.shape != (60,) or not np.isfinite(q).all():
                raise ValueError("Vector truy van khong phai 60 chieu hop le")
            qz = (q - mean) / std_safe
            diffs = Z - qz
            d2 = np.sum(diffs * diffs, axis=1)
            qkey = path_key(str(query_file))
            for j, dbkey in enumerate(db_paths):
                if qkey == dbkey:
                    # Khong danh gia file nam trong dataset. Neu bi trung path thi bao loi.
                    raise ValueError("File test trung DUONG DAN voi mot file trong CSDL; khong phai test ngoai dataset")
            # Xep theo d2 tang dan, neu bang nhau uu tien audio_id tang dan.
            ordered = np.lexsort((ids, d2))
            best = ordered[:top_k]
            matches = sum(labels[j] == truth for j in best)
            query_record = {
                "query_file": query_file.name,
                "query_path": str(query_file),
                "actual_instrument": truth,
                "top1_instrument": labels[best[0]],
                "top1_correct": int(labels[best[0]] == truth),
                "correct_in_top5": matches,
                "precision_at_5": matches / top_k,
                "top5_instruments": " | ".join(labels[j] for j in best),
                "top5_distances": " | ".join(f"{np.sqrt(d2[j]):.6f}" for j in best),
            }
            per_query.append(query_record)

            for rank, j in enumerate(best, 1):
                r = rows[j]
                contributions = {
                    f"d2_{name.lower().replace(' ', '_')}": float(np.sum(diffs[j, start:end] ** 2))
                    for name, start, end in GROUPS
                }
                distance = float(np.sqrt(d2[j]))
                top5.append({
                    "query_file": query_file.name,
                    "query_path": str(query_file),
                    "actual_instrument": truth,
                    "rank": rank,
                    "audio_id": int(r[0]),
                    "result_filename": str(r[1]),
                    "result_path": str(r[2]),
                    "result_instrument": labels[j],
                    "correct": int(labels[j] == truth),
                    "distance": distance,
                    "distance_squared": float(d2[j]),
                    "similarity_score": 1 / (1 + distance),
                    **contributions,
                })

            if save_all:
                for rank, j in enumerate(ordered, 1):
                    all_distances.append({
                        "query_file": query_file.name,
                        "actual_instrument": truth,
                        "rank": rank,
                        "result_instrument": labels[j],
                        "result_filename": str(rows[j][1]),
                        "distance": float(np.sqrt(d2[j])),
                    })
            print(f"    Top-1: {labels[best[0]]} | dung {matches}/{top_k} | P@5={matches / top_k:.0%}")
        except Exception as exc:
            failures.append({
                "query_file": query_file.name, "query_path": str(query_file),
                "actual_instrument": truth,
                "error_type": type(exc).__name__, "error": str(exc)
            })
            print(f"    LOI: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    return per_query, top5, failures, all_distances


def make_summary(per_query: list[dict], failures: list[dict], selection: list,
                 select_report: dict, num_db_vectors: int, seed: int, per_class: int):
    classes = sorted(select_report["by_instrument"], key=str.casefold)
    by_class = []
    for instrument in classes:
        selected_n = select_report["by_instrument"][instrument]["selected"]
        successes = [r for r in per_query if r["actual_instrument"] == instrument]
        n = len(successes)
        correct = sum(r["top1_correct"] for r in successes)
        correct5 = sum(r["correct_in_top5"] for r in successes)
        by_class.append({
            "instrument": instrument,
            "available_files": select_report["by_instrument"][instrument]["available"],
            "selected_files": selected_n,
            "successful_queries": n,
            "failed_queries": selected_n - n,
            "top1_correct": correct,
            "top1_accuracy": correct / n if n else "",
            "correct_in_top5_total": correct5,
            "mean_precision_at_5": correct5 / (n * 5) if n else "",
        })
    n = len(per_query)
    sum_top1 = sum(r["top1_correct"] for r in per_query)
    sum_correct5 = sum(r["correct_in_top5"] for r in per_query)
    summary = {
        "selected_test_files": len(selection),
        "successful_queries": n,
        "failed_queries": len(failures),
        "database_vectors": num_db_vectors,
        "candidate_count_per_external_query": num_db_vectors,
        "num_reference_instruments": len(classes),
        "num_test_instruments_with_success": len({r["actual_instrument"] for r in per_query}),
        "per_class_requested": per_class,
        "random_seed": seed,
        "top_k": 5,
        "top1_correct_queries": sum_top1,
        "top1_accuracy": sum_top1 / n if n else None,
        "top5_same_instrument_results": sum_correct5,
        "mean_precision_at_5": sum_correct5 / (n * 5) if n else None,
        "normalization": "Z-score computed only from database vector matrix, as in search_top5_postgres.py",
        "evaluation": "External query files; same-instrument retrieval evaluation; verify audio source independence",
        "warning": "Renaming files does not make copied or re-encoded recordings independent",
    }
    return summary, by_class


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kiem tra hang loat 5 file x 16 nhac cu tu PostgreSQL (mot lenh)"
    )
    parser.add_argument("--test-dir", required=True,
                        help="Thu muc goc chua 16 thu muc con theo ten nhac cu")
    parser.add_argument("--per-class", type=int, default=5,
                        help="So file chon ngau nhien moi nhac cu (0 = lay tat ca); mac dinh 5")
    parser.add_argument("--seed", type=int, default=42,
                        help="Hat giong chon ngau nhien de tai lap thuc nghiem; mac dinh 42")
    parser.add_argument("--output", default="output/batch_external_80",
                        help="Thu muc xuat ket qua")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--dbname", default="wind_instruments_db")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--ffmpeg", default="",
                        help="Duong dan ffmpeg.exe de giai ma codec kho (neu co)")
    parser.add_argument("--save-all-distances", action="store_true",
                        help="Xuat them khoang cach den TOAN BO 645 file cho moi truy van")
    args = parser.parse_args()
    if args.per_class < 0:
        parser.error("--per-class phai >= 0")
    test_root = path_from_root(args.test_dir)
    if not test_root.is_dir():
        parser.error(f"Khong tim thay thu muc test: {test_root}")
    output_dir = path_from_root(args.output)
    if test_root == output_dir or test_root in output_dir.parents:
        parser.error("Khong dat thu muc output trong thu muc test")

    password = os.environ.get("PGPASSWORD")
    if password is None:
        password = getpass.getpass("Mat khau PostgreSQL (khong hien thi): ")
    print("Dang ket noi PostgreSQL, doc tat ca vector MOT LAN ...")
    rows, X = load_database(args, password)
    known_classes = sorted({str(r[3]) for r in rows}, key=str.casefold)
    if len(known_classes) != 16:
        print(f"CANH BAO: Co {len(known_classes)} nhac cu trong CSDL, khong phai 16")
    selection, report = select_test_files(test_root, known_classes, args.per_class, args.seed)
    if not selection:
        parser.error("Khong co file am thanh hop le trong cac thu muc nhac cu")
    print("\nDanh sach file test theo nhac cu:")
    for instrument, rec in report["by_instrument"].items():
        print(f"  {instrument:17s}: co {rec['available']:3d}, chon {rec['selected']:3d}")
    print(f"Tong so file se xu ly: {len(selection)} (ky vong 80 neu 16 nhac cu x 5 file)")
    if len(selection) != 80 and args.per_class == 5:
        print("CANH BAO: So file duoc chon KHAC 80. Kiem tra cac thu muc thieu file.")
    if report["ignored_root_files"]:
        print(f"CANH BAO: Bo qua {len(report['ignored_root_files'])} file nam truc tiep duoi thu muc goc; "
              "hay dua file vao thu muc nhac cu tuong ung.")

    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if ffmpeg and not Path(ffmpeg).is_file() and shutil.which(ffmpeg) is None:
        parser.error(f"Khong tim thay FFmpeg: {ffmpeg}")
    print(f"FFmpeg du phong: {ffmpeg or 'khong co (se bao loi neu codec khong duoc ho tro)'}")
    print("\nTrich xuat va tim kiem Top 5:")
    per_query, top5, failures, all_distances = run_batch(
        rows, X, selection, ffmpeg, top_k=5,
        save_all=args.save_all_distances
    )
    summary, by_class = make_summary(per_query, failures, selection, report,
                                     len(rows), args.seed, args.per_class)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "selected_queries.csv",
              [{"query_path": str(p), "actual_instrument": y} for p, y in selection],
              ["query_path", "actual_instrument"])
    write_csv(output_dir / "per_query.csv", per_query, [
        "query_file", "query_path", "actual_instrument", "top1_instrument",
        "top1_correct", "correct_in_top5", "precision_at_5",
        "top5_instruments", "top5_distances"
    ])
    top_headers = (["query_file", "query_path", "actual_instrument", "rank", "audio_id",
                    "result_filename", "result_path", "result_instrument", "correct",
                    "distance", "distance_squared", "similarity_score"]
                   + [f"d2_{name.lower().replace(' ', '_')}" for name, _, _ in GROUPS])
    write_csv(output_dir / "top5_details.csv", top5, top_headers)
    write_csv(output_dir / "per_instrument.csv", by_class, [
        "instrument", "available_files", "selected_files", "successful_queries",
        "failed_queries", "top1_correct", "top1_accuracy",
        "correct_in_top5_total", "mean_precision_at_5"
    ])
    write_csv(output_dir / "errors.csv", failures, [
        "query_file", "query_path", "actual_instrument", "error_type", "error"
    ])
    if args.save_all_distances:
        write_csv(output_dir / "all_distances.csv", all_distances, [
            "query_file", "actual_instrument", "rank", "result_instrument",
            "result_filename", "distance"
        ])
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\n============ TONG KET TEST NGOAI DATASET ============")
    print(f"Da chon: {len(selection)} file | Thanh cong: {len(per_query)} | Loi: {len(failures)}")
    if per_query:
        print(f"Top-1 Accuracy: {summary['top1_accuracy']:.2%} "
              f"({summary['top1_correct_queries']}/{len(per_query)})")
        print(f"Precision@5 trung binh: {summary['mean_precision_at_5']:.2%} "
              f"({summary['top5_same_instrument_results']}/{len(per_query) * 5})")
    else:
        print("KHONG CO truy van nao thanh cong, xem errors.csv")
    print(f"Ket qua da luu: {output_dir}")
    print("Ghi chu: Chi tinh chi so tren file test doc duoc; file loi duoc ghi rieng.")
    print("Ghi chu: Doi ten ngau nhien khong tao su doc lap voi ban thu trong dataset.")


if __name__ == "__main__":
    main()
