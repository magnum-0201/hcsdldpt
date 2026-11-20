

\# HCSDLĐPT - Hệ thống tìm kiếm âm thanh tương đồng



\## Giới thiệu

Đồ án xây dựng hệ thống tìm kiếm 5 file âm thanh

tương đồng nhất với một file âm thanh truy vấn

thuộc nhóm nhạc cụ bộ hơi.



\## Công nghệ

\- Python

\- Librosa

\- FFmpeg

\- PostgreSQL

\- NumPy



\## Đặc trưng âm thanh

Mỗi file được biểu diễn bằng vector 60 chiều:

\- MFCC

\- Spectral Centroid

\- Spectral Bandwidth

\- Spectral Rolloff

\- Spectral Flatness

\- Spectral Contrast

\- RMS Energy

\- Zero Crossing Rate



\## Quy trình

1\. Chuẩn bị dữ liệu âm thanh.

2\. Chuyển sang WAV mono, 22050 Hz, PCM16.

3\. Trích xuất vector 60 chiều.

4\. Lưu vector vào PostgreSQL.

5\. Chuẩn hóa Z-score dựa trên dữ liệu tham chiếu.

6\. Tính khoảng cách Manhattan.

7\. Trả về Top-5 file có khoảng cách nhỏ nhất.



\## Cài đặt thư viện

python -m pip install -r requirements.txt



\## Dữ liệu

Dữ liệu âm thanh được lưu và chia sẻ riêng.

Không lưu dữ liệu âm thanh trong GitHub repository.



\## Phân chia công việc

Các thành viên cập nhật dataset và mã nguồn

thông qua GitHub.



