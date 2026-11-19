# Kết quả kiểm tra bộ build QY

Kiểm tra ngày 2026-11-17. Repo cũ chỉ khai báo version-16/main, không có lock
để xác nhận đúng phiên bản đang chạy trên VPS. Không truy cập VPS trong lần kiểm tra này.

| App | Tag chọn cho build test | Điều kiện khai báo |
| --- | --- | --- |
| Frappe | v16.56.0 | Python >=3.14,<3.15; Node >=24 |
| ERPNext | v16.55.0 | Python >=3.14; Frappe >=16.55.0,<17 |
| Healthcare | v16.8.0 | Frappe và ERPNext >=16,<17; Python >=3.10 |
| Solvronix Desk | v3.0.1 | Frappe >=15,<17; Python >=3.10 |

Các điều kiện phiên bản trên khớp nhau. Đã build image ARM64 đầy đủ và PASS
smoke test version, code/asset và native import; chưa nghiệm thu luồng đo trên Jetson.
Commit đầy đủ ở sources.lock.json. Recipe frappe_docker được khóa trong versions.env,
mặc định Python 3.14, Node 24, Debian trixie. Socket.IO Node entrypoint vẫn tồn tại;
MariaDB setup cho phép khoảng phiên bản 10.6 đến 11.8.

Local QY required_apps=[smart_hospital]; smart_hospital required_apps=[healthcare].
Không thấy dependency khai báo vào TV trong hai app này. Không đồng nghĩa mọi luồng
scan/ảnh đều hoạt động khi không có media/QR/Face.

Đã kiểm tra manifest linux/arm64:

| Image | ARM64 manifest digest |
| --- | --- |
| python:3.14-slim-trixie | sha256:973d41424c3fd81029ac9230bcdec2580fb67b49af9004279001c301182ae868 |
| mariadb:10.6.25 | sha256:9e906f1af1904120e02cce37124d10696c0828f3dba8a848ae4c96812d3414c9 |
| redis:6.2.17-alpine | sha256:a2db07d99b2fab70933ea2fac33912a096fadccfdf596d66b49d0db6a5989e7f |
| eclipse-mosquitto:2.0.22 | sha256:49175e3b4f7609389193c86525f3f235b236b0843cae27960a62fad6649eeebf |

Manifest ARM64 không đảm bảo mọi Python wheel và package sẽ cài thành công.
Image đầy đủ đã build thành công. Việc chạy luồng đo thật và đo tài nguyên cần thực hiện trên Jetson.
Dependency khai báo không thay thế nghiệm thu. Không cần quyết định phiên bản từ người
vận hành để bắt đầu build thử bộ đã chọn này.

Nguồn: pyproject.toml, package.json, socketio.js/realtime/index.js và MariaDB setup
trong các repository chính thức frappe/frappe, frappe/erpnext, frappe/healthcare;
pyproject.toml và hooks.py của Solvronix/Solvronix-Desk tại commit đã khóa.

## Điều chỉnh build khi chạy QEMU

- Yarn: timeout 600000 ms, registry npm; giữ cache uv/Yarn giữa các lượt build.
- Tách cài app (`bench init --skip-assets`) và `bench build` thành hai lớp.
- Banking của ERPNext: thêm dev dependency chính xác `rolldown@1.2.18`, nằm trong
  range `~1.2.4` của Vite 8.2.4. Đây là thay đổi build so với source tag ERPNext;
  không sửa nghiệp vụ Python. Lockfile/package.json thực tế cần lưu kèm artifact.
- Giới hạn ROLLDOWN_WORKER_THREADS, TOKIO_WORKER_THREADS, RAYON_NUM_THREADS và
  UV_THREADPOOL_SIZE bằng 2 trong lệnh build asset, không đặt cho runtime Frappe.
- Lượt trước ghi nhận Vite ở rendering chunks, 0% CPU và worker chờ; không phải
  bằng chứng dependency Python sai. Banking và Patient Portal đã build asset thành công sau điều chỉnh.

Tham khảo: [Rolldown troubleshooting](https://github.com/rolldown/rolldown/blob/main/docs/guide/troubleshooting.md),
[upstream issue về QEMU](https://github.com/rolldown/rolldown/issues/11278).

Patient Portal v16.8.0 còn import socketio_port từ common_site_config lúc build,
và khi URL có port riêng thì trỏ Socket.IO sang cổng nội bộ đó. `patch_portal.py`
thay phần chọn URL bằng `window.location.origin` + site namespace, để HTTP LAN
18080 và HTTPS đều đi qua frontend proxy. Bản vá được kiểm tra trên source tag đã khóa;
không yêu cầu publish websocket 9000. Build config vẫn khởi tạo socketio_port=9000
nhất quán với Compose, không chứa secret hoặc địa chỉ production.

## Cấu hình khởi động đã kiểm tra thêm

Configurator ghi common_site_config và apps.txt nguyên tử trong một tiến trình Python,
giữ các khóa đã có và tránh gọi CLI Frappe nhiều lần chỉ để ghi JSON.
`mariadb-client.cnf` được mount read-only vào app containers: CLI client mới dùng
`skip-ssl` khi truy cập MariaDB 10.6 trong mạng Compose riêng, không publish cổng DB.
Không đổi cấu hình TLS của hệ thống production hoặc image MariaDB server.
