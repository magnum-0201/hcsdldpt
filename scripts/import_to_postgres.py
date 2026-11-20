
import csv
import math
import getpass
from pathlib import Path

import psycopg

# Đường dẫn tới CSV đã trích xuất
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "output" / "features_60d.csv"

FEATURE_COLS = [f"f{i:02d}" for i in range(1, 61)]

if not CSV_PATH.is_file():
    raise FileNotFoundError(f"Không tìm thấy: {CSV_PATH}")

# Mật khẩu PostgreSQL được nhập khi chạy, không ghi vào code
password = getpass.getpass("Nhập mật khẩu PostgreSQL: ")

conn_info = {
    "host": "localhost",
    "port": 5432,
    "dbname": "wind_instruments_db",
    "user": "postgres",
    "password": password,
}

with psycopg.connect(**conn_info) as conn:
    with conn.cursor() as cur:
        instrument_cache = {}
        imported = 0

        with CSV_PATH.open(
            "r", encoding="utf-8-sig", newline=""
        ) as f:
            reader = csv.DictReader(f)

            required = {
                "filename", "path", "instrument",
                *FEATURE_COLS
            }

            missing = required - set(reader.fieldnames or [])

            if missing:
                raise ValueError(
                    f"CSV thiếu các cột: {sorted(missing)}"
                )

            for row in reader:
                filename = row["filename"].strip()
                file_path = row["path"].strip()
                instrument = row["instrument"].strip()

                if not filename or not file_path or not instrument:
                    raise ValueError(
                        f"Thiếu thông tin ở dòng {imported + 2}"
                    )

                vector = [
                    float(row[col]) for col in FEATURE_COLS
                ]

                if not all(math.isfinite(v) for v in vector):
                    raise ValueError(
                        f"Vector không hợp lệ: {filename}"
                    )

                # 1. Lưu tên nhạc cụ
                if instrument not in instrument_cache:
                    cur.execute("""
                        INSERT INTO instruments (instrument_name)
                        VALUES (%s)
                        ON CONFLICT (instrument_name)
                        DO UPDATE SET
                            instrument_name = EXCLUDED.instrument_name
                        RETURNING instrument_id
                    """, (instrument,))

                    instrument_cache[instrument] = cur.fetchone()[0]

                instrument_id = instrument_cache[instrument]

                # 2. Lưu thông tin file âm thanh
                cur.execute("""
                    INSERT INTO audio_files
                        (instrument_id, filename, file_path)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (file_path)
                    DO UPDATE SET
                        instrument_id = EXCLUDED.instrument_id,
                        filename = EXCLUDED.filename
                    RETURNING audio_id
                """, (instrument_id, filename, file_path))

                audio_id = cur.fetchone()[0]

                # 3. Lưu vector 60 chiều
                cur.execute("""
                    INSERT INTO audio_features
                        (audio_id, feature_vector)
                    VALUES (%s, %s::double precision[])
                    ON CONFLICT (audio_id)
                    DO UPDATE SET
                        feature_vector = EXCLUDED.feature_vector
                """, (audio_id, vector))

                imported += 1

                if imported % 100 == 0:
                    print(f"Đã xử lý {imported} file...")

        # 4. Kiểm tra số lượng
        for table in [
            "instruments",
            "audio_files",
            "audio_features"
        ]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"{table}: {cur.fetchone()[0]}")

        cur.execute("""
            SELECT COUNT(*)
            FROM audio_features
            WHERE cardinality(feature_vector) <> 60
        """)

        print("Vector sai số chiều:", cur.fetchone()[0])
        print("Số dòng CSV đã xử lý:", imported)

print("Nhập dữ liệu hoàn tất!")
