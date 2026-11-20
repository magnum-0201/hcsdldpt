# -*- coding: utf-8 -*-
"""Convert the project's instrument audio files to standardized WAV.

Processing matches the established FFmpeg conversion stage:
    -ac 1 -ar 22050 -c:a pcm_s16le

It does NOT remove silence, normalize volume, reduce noise, or trim duration.
Originals are never modified. By default, existing outputs are never replaced.

From a project containing either convert_to_wav.py or scripts/convert_to_wav.py:
    python -B scripts/convert_to_wav.py --input-dir dataset_v2 --output-dir dataset_processed_v2 --dry-run
    python -B scripts/convert_to_wav.py --input-dir dataset_v2 --output-dir dataset_processed_v2

The output structure mirrors instrument subfolders. For example:
    dataset_v2/Flute/example.mp3
    -> dataset_processed_v2/Flute/example_mp3.wav
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import wave
from collections import Counter
from pathlib import Path

SAMPLE_RATE = 22050
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2  # signed 16-bit PCM
AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac",
    ".wma", ".aif", ".aiff", ".opus", ".webm",
}

_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _SCRIPT_DIR.parent if _SCRIPT_DIR.name.lower() == "scripts" else _SCRIPT_DIR
DEFAULT_WINDOWS_FFMPEG = Path(r"C:\Users\kamen\Downloads\ffmpeg\ffmpeg\bin\ffmpeg.exe")


def project_path(raw):
    path = Path(raw).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def find_ffmpeg(custom):
    if custom:
        custom_path = Path(custom).expanduser()
        if custom_path.is_file():
            return str(custom_path.resolve())
        executable = shutil.which(custom)
        if executable:
            return executable
        raise FileNotFoundError(f"Khong thay FFmpeg: {custom}")
    if DEFAULT_WINDOWS_FFMPEG.is_file():
        return str(DEFAULT_WINDOWS_FFMPEG)
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    raise FileNotFoundError(
        "Khong tim thay ffmpeg.exe. Cai FFmpeg vao PATH hoac them "
        '--ffmpeg "C:\\duong_dan\\ffmpeg.exe".'
    )


def destination_for(source, input_root, output_root):
    relative = source.relative_to(input_root)
    # Include the original extension to prevent foo.mp3 and foo.wav colliding.
    new_name = f"{source.stem}_{source.suffix[1:].lower()}.wav"
    return output_root / relative.parent / new_name


def check_wav(path):
    with wave.open(str(path), "rb") as wav:
        info = (wav.getnchannels(), wav.getframerate(), wav.getsampwidth())
        if info != (CHANNELS, SAMPLE_RATE, SAMPLE_WIDTH_BYTES):
            raise ValueError(f"Thong so WAV khong dung: {info}")
        if wav.getnframes() == 0:
            raise ValueError("File WAV dau ra rong")


def convert_one(source, target, ffmpeg, overwrite):
    target.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary WAV in the target folder. Only publish a complete file.
    with tempfile.NamedTemporaryFile(
        prefix=".converting-", suffix=".wav", dir=target.parent, delete=False
    ) as f:
        tmp = Path(f.name)
    try:
        cmd = [
            ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", str(source), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
            "-c:a", "pcm_s16le", "-f", "wav", "-y", str(tmp),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if result.returncode != 0:
            error = result.stderr.strip() or f"FFmpeg exit code {result.returncode}"
            raise RuntimeError(error[-1200:])
        check_wav(tmp)
        if target.exists() and not overwrite:
            return "skip"
        tmp.replace(target)
        return "ok"
    finally:
        tmp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description="Chuyen bo du lieu sang WAV mono 22050 Hz PCM16, giu nguyen thoi luong."
    )
    parser.add_argument("--input-dir", default="dataset", help="Thu muc nhac cu goc (mac dinh: dataset)")
    parser.add_argument(
        "--output-dir", default="dataset_processed", help="Thu muc WAV dau ra (mac dinh: dataset_processed)"
    )
    parser.add_argument("--ffmpeg", default=None, help="Duong dan ffmpeg.exe; bo qua neu co trong PATH")
    parser.add_argument("--dry-run", action="store_true", help="Chi liet ke, KHONG tao WAV")
    parser.add_argument("--overwrite", action="store_true", help="Cho phep thay the file WAV dich da ton tai")
    parser.add_argument("--limit", type=int, default=0, help="Chi xu ly N file moi/dang duoc chon (0: tat ca)")
    parser.add_argument("--expected-total", type=int, default=0, help="Canh bao neu so file goc khac con so nay")
    args = parser.parse_args()

    input_root = project_path(args.input_dir)
    output_root = project_path(args.output_dir)
    if not input_root.is_dir():
        parser.error(f"Khong tim thay thu muc dataset: {input_root}")
    if output_root == input_root or input_root in output_root.parents:
        parser.error("Thu muc dau ra phai nam NGOAI thu muc du lieu goc de tranh xu ly lap.")
    if args.limit < 0 or args.expected_total < 0:
        parser.error("--limit va --expected-total phai >= 0")

    sources = sorted(
        (p for p in input_root.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS),
        key=lambda p: str(p.relative_to(input_root)).casefold(),
    )
    if not sources:
        parser.error(f"Khong thay file am thanh hop le trong: {input_root}")

    print("Nguon:", input_root)
    print("Dich :", output_root)
    print("Thong so: WAV / mono / 22050 Hz / PCM signed 16-bit")
    print("Khong cat khoang lang, khong chuan hoa am luong, khong loc nhieu, khong co dinh do dai.")
    print("Tong file am thanh dau vao:", len(sources))
    counts = Counter(str(p.relative_to(input_root).parts[0]) for p in sources)
    for instrument, count in sorted(counts.items(), key=lambda item: item[0].casefold()):
        print(f"  {instrument}: {count}")
    if args.expected_total and len(sources) != args.expected_total:
        print(f"CANH BAO: Du kien {args.expected_total} file, nhung tim thay {len(sources)}.")

    planned = []
    collisions = {}
    skipped_existing = 0
    for src in sources:
        dst = destination_for(src, input_root, output_root)
        key = str(dst).casefold()  # Windows output paths are case-insensitive.
        if key in collisions:
            parser.error(f"Hai file goc se trung ten file dich: {src} va {collisions[key]}")
        collisions[key] = src
        if dst.exists() and not args.overwrite:
            skipped_existing += 1
            continue
        planned.append((src, dst))
    if args.limit:
        planned = planned[:args.limit]

    print(f"Da ton tai (bo qua): {skipped_existing} | Se xu ly: {len(planned)}")
    if args.dry_run:
        print("CHE DO DRY-RUN: khong ghi file nao.")
        for index, (src, dst) in enumerate(planned, 1):
            print(f"[{index}/{len(planned)}] {src.relative_to(input_root)} -> {dst.relative_to(output_root)}")
        return 0
    if not planned:
        print("Khong co file moi can chuyen doi.")
        return 0

    try:
        ffmpeg = find_ffmpeg(args.ffmpeg)
    except FileNotFoundError as exc:
        print("LOI:", exc, file=sys.stderr)
        return 2
    print("FFmpeg:", ffmpeg)
    success, failed = 0, []
    for index, (src, dst) in enumerate(planned, 1):
        print(f"[{index}/{len(planned)}] {src.relative_to(input_root)}", flush=True)
        try:
            status = convert_one(src, dst, ffmpeg, args.overwrite)
            if status == "ok":
                success += 1
            else:
                print("  BO QUA: dich da ton tai")
        except Exception as exc:
            failed.append((src, str(exc)))
            print("  LOI:", exc, file=sys.stderr)

    print("\n========== TONG KET ==========")
    print("Dau vao:", len(sources))
    print("Chuyen thanh cong lan nay:", success)
    print("Da co tu truoc:", skipped_existing)
    print("Loi:", len(failed))
    print("Du lieu goc khong bi thay doi. Khong sua PostgreSQL.")
    if failed:
        for path, message in failed[:20]:
            print(f"  - {path.relative_to(input_root)}: {message[:350]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
