"""Trích rút 60 đặc trưng âm thanh theo Phần II của báo cáo nhóm.

8 nhóm: MFCC (17), Centroid, Bandwidth, Rolloff (85%), Flatness,
Contrast (7 dải), RMS, ZCR. Mỗi thành phần được mô tả bằng mean/std.

Chạy:
    python extract_features_60d.py
    python extract_features_60d.py --dataset dataset_processed
"""
from __future__ import annotations

import argparse
from pathlib import Path

import librosa
import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
SAMPLE_RATE = 22050
N_FFT = 2048
HOP_LENGTH = 512
N_MFCC = 17
FEATURE_COLS = [f"f{i:02d}" for i in range(1, 61)]
META_COLS = ["filename", "path", "instrument"]


def summarize(matrix: np.ndarray) -> np.ndarray:
    """Với mỗi hàng đặc trưng, ghép mean của các hàng rồi đến std."""
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        raise ValueError("Ma trận đặc trưng rỗng hoặc không có 2 chiều")
    return np.concatenate(
        [np.mean(matrix, axis=1), np.std(matrix, axis=1)]
    )


def extract_vector(path: Path) -> np.ndarray:
    y, sr = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    if y.size == 0 or not np.isfinite(y).all():
        raise ValueError("File không có mẫu âm thanh hợp lệ")

    # Các đặc trưng phổ dùng nhất quán n_fft=2048, hop_length=512.
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH))

    mfcc = librosa.feature.mfcc(
        y=y, sr=sr, n_mfcc=N_MFCC,
        n_fft=N_FFT, hop_length=HOP_LENGTH
    )
    centroid = librosa.feature.spectral_centroid(S=S, sr=sr)
    bandwidth = librosa.feature.spectral_bandwidth(S=S, sr=sr)
    rolloff = librosa.feature.spectral_rolloff(
        S=S, sr=sr, roll_percent=0.85
    )
    flatness = librosa.feature.spectral_flatness(S=S ** 2)
    contrast = librosa.feature.spectral_contrast(
        S=S, sr=sr, n_bands=6
    )  # 6 điểm chia tạo ra 7 dải
    rms = librosa.feature.rms(
        y=y, frame_length=N_FFT, hop_length=HOP_LENGTH
    )
    zcr = librosa.feature.zero_crossing_rate(
        y, frame_length=N_FFT, hop_length=HOP_LENGTH
    )

    vector = np.concatenate([
        summarize(mfcc),       # f01-f34: 17 mean + 17 std
        summarize(centroid),   # f35-f36
        summarize(bandwidth),  # f37-f38
        summarize(rolloff),    # f39-f40
        summarize(flatness),   # f41-f42
        summarize(contrast),   # f43-f56: 7 mean + 7 std
        summarize(rms),        # f57-f58
        summarize(zcr),        # f59-f60
    ])

    if vector.shape != (60,):
        raise ValueError(f"Sai kích thước vector: {vector.shape}")
    if not np.isfinite(vector).all():
        raise ValueError("Vector chứa NaN hoặc vô cực")
    return vector


def resolve_from_project(path_text: str) -> Path:
    path = Path(path_text).expanduser()
    return path if path.is_absolute() else PROJECT_DIR / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Trích xuất 60 đặc trưng âm thanh")
    parser.add_argument("--dataset", default="dataset_processed")
    parser.add_argument("--output", default="output/features_60d.csv")
    args = parser.parse_args()

    dataset = resolve_from_project(args.dataset)
    output = resolve_from_project(args.output)
    if not dataset.is_dir():
        raise SystemExit(f"Không tìm thấy thư mục: {dataset}")

    # Dataset đã chuẩn hóa: chỉ dùng WAV, không vô tình đọc lại file gốc.
    files = sorted(
        (p for p in dataset.rglob("*.wav") if p.is_file()),
        key=lambda p: str(p).lower()
    )
    if not files:
        raise SystemExit(f"Không tìm thấy WAV trong {dataset}")

    rows = []
    errors = []
    print(f"DATASET: {dataset}")
    print(f"Tổng file WAV cần trích xuất: {len(files)}")

    for i, path in enumerate(files, 1):
        try:
            vec = extract_vector(path)
            row = {
                "filename": path.name,
                "path": str(path.resolve()),
                "instrument": path.parent.name,
            }
            row.update({name: float(value) for name, value in zip(FEATURE_COLS, vec)})
            rows.append(row)
            print(f"[{i}/{len(files)}] OK: {path.parent.name}/{path.name}")
        except Exception as exc:
            errors.append({
                "path": str(path.resolve()),
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            print(f"[{i}/{len(files)}] LỖI: {path.name}: {type(exc).__name__}: {exc}")

    output.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=META_COLS + FEATURE_COLS)
    df.to_csv(output, index=False, encoding="utf-8-sig")
    error_path = output.parent / "feature_errors_60d.csv"
    pd.DataFrame(errors, columns=["path", "error_type", "error"]).to_csv(
        error_path, index=False, encoding="utf-8-sig"
    )

    print("\n========== KẾT QUẢ ==========")
    print("Số file đã duyệt:", len(files))
    print("Số file thành công:", len(df))
    print("Số file lỗi:", len(errors))
    print("Số chiều đặc trưng:", len(FEATURE_COLS))
    print("Số nhóm nhạc cụ:", df["instrument"].nunique())
    print("Kết quả:", output)
    print("Báo lỗi:", error_path)
    if len(files) != 645:
        print("LƯU Ý: Số file thực tế khác 645 trong báo cáo. Cần đối chiếu dataset.")


if __name__ == "__main__":
    main()
