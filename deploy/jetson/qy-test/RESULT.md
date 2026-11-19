# Bàn giao build QY ARM64

Build image đầy đủ: PASS. Image: `visiontestai/frappe:qy-arm64-test1`.

- Manifest digest: `sha256:7f8cf000d91b45c1c226375459f29020dce30c56f91759ed6037e15aa05d785c`
- Image/config digest: `sha256:0830240ddbf8d45bf33e36cb5994b5f3bbb65740c300ad319fcc8a6375e3e554`
- Image size chưa nén: 3,594,007,239 bytes.
- Archive gồm 4 image ARM64: 1,215,827,236 bytes (~1.22 GB).

| Thành phần | Phiên bản thực tế |
| --- | --- |
| frappe | 16.56.0 |
| erpnext | 16.55.0 |
| healthcare | 16.8.0 |
| solvronix_desk | 3.0.1 |
| smart_hospital | 0.0.1 |
| qy_vision_hospital | 0.1.0 |
| paho-mqtt | 2.1.0 |

Đã PASS: build ARM64; import đủ app; native extensions MySQLdb/PyArrow/DuckDB/Orjson/Pillow;
asset Desk/Banking/Patient Portal/QY; không có app TV; kiểm tra tương thích 172 package Python;
CRC gzip/tar và manifest của cả 4 image; MQTT auth/QoS 1/chặn anonymous;
Redis queue giữ dữ liệu qua restart; Docker Compose config hợp lệ.

Cấu hình triển khai kèm `mariadb-client.cnf` cho CLI mới truy cập DB 10.6 nội bộ;
configurator ghi JSON nguyên tử. Mật khẩu runtime để trống trong env mẫu.

QA khởi tạo site đang chạy nền trên workspace x86 qua QEMU, kết quả cập nhật tại
`out/runtime-verification.json` của workspace. Chưa kết luận PASS cho toàn bộ
provision/migrate/realtime của site tại thời điểm đóng gói. Nếu QA PASS, monitor tự dừng
project qy-buildcheck và giữ volumes/logs. Bộ release không chứa env/password test.

Chưa nghiệm thu Jetson thật: luồng AC/SmartEyes/camera/audio, cancel/callback/raw trials,
RAM/latency/guardrail 1 GiB MemAvailable và backup/restore thực tế.
VPS production và DNS không thay đổi.

Xem README.md để load image và chạy Compose trên Jetson. Các file metadata trong out/
ghi source lock, commit thực tế, dependency freeze, lockfile Node và kết quả smoke test.
