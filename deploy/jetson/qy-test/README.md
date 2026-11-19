# QY-only ARM64: build trên máy khác, chạy trên Jetson

Bản test riêng, không thay thế VPS production. AC/SmartEyes giữ native. Không có TV,
Face, media hoặc QR service. Các nút scan/ảnh trên Desk chưa thuộc nghiệm thu này.
Workspace đã cài Docker/Buildx/Compose/QEMU và build/chạy smoke test ARM64 thành công.
Image Frappe QY đầy đủ đã build ARM64 và qua smoke test code/asset/native import.
Chưa nghiệm thu trên Jetson thật. Xem BUILD_ENVIRONMENT.md và out/image-verification.json.

## 1. Máy build

Cần Docker Engine + Compose v2 + Buildx, Git, Python 3; đủ disk cho build Frappe.
Máy x86 cần builder đã hỗ trợ linux/arm64 (QEMU/binfmt hoặc remote ARM builder).
Kiểm tra `docker buildx inspect qy-arm64 --bootstrap`; danh sách Platforms phải có linux/arm64.
Nếu chưa có builder, tạo bằng `docker buildx create --name qy-arm64 --driver docker-container --use --bootstrap`.
Không chạy build trên Jetson đang phục vụ trạm. Script không tự cài binfmt hoặc đổi builder.

Từ thư mục này:

```bash
cp .env.example .env
chmod 600 .env
```

Khi chuẩn bị chạy site, điền ba password mạnh khác nhau trong `.env`; build image không cần password runtime. File được shell source: dùng giá trị
được quote đúng cú pháp Bash, không chứa xuống dòng. Chọn tag image riêng cho mỗi build.
Bộ mặc định đã chọn trong `versions.env`: Frappe v16.56.0, ERPNext v16.55.0,
Healthcare v16.8.0, Desk v3.0.1. `sources.lock.json` lưu commit tương ứng; script từ chối
nếu tag mặc định bị upstream đổi commit. Không cần tự chọn lại để build thử.
Đây chưa được xác nhận là bộ đang chạy trên VPS production.

```bash
# Script tự nạp phiên bản đã chọn từ versions.env.
export CUSTOM_IMAGE=visiontestai/frappe:qy-arm64-test1
./build.sh
```

Script dùng recipe custom chính thức đã khóa commit, áp dụng các điều chỉnh build-only
trong VERSION_CHECK.md (cache, timeout, Rolldown/worker QEMU), và ghép layer QY trong cùng
build graph; BuildKit nhận apps.json bằng secret. Nó kiểm tra image ARM64, import app,
lưu phiên bản, source commit/tag, build metadata, image inspect, ngày build và bản source
local đóng gói trong `out/`. Gói `out/qy-arm64-images.tar.gz` chứa cả image hạ tầng ARM64.
`SHA256SUMS` xác minh file chuyển máy; image ID/RepoDigests ở image-inspect là thông tin
image, không đồng nhất với checksum file tar. Build local có thể chưa có registry digest.
Tag hạ tầng trong env là bản cụ thể nhưng vẫn cần kiểm tra pull ARM64 thực tế.
Recipe upstream/dependency hệ điều hành chưa được khóa toàn bộ; không cam kết build
bit-for-bit giống nhau. Giữ archive image đã nghiệm thu để triển khai lại chính xác.

## 2. Chuyển và chạy trên Jetson

Chuyển `qy-arm64-images.tar.gz`, `qy-jetson-config.tar.gz` và `SHA256SUMS` qua SCP/USB.
Jetson cần Docker Engine và Compose v2. Giải nén bộ cấu hình trong thư mục riêng:

```bash
sha256sum -c SHA256SUMS
mkdir -p qy-jetson-test
tar -xzf qy-jetson-config.tar.gz -C qy-jetson-test
mkdir -p qy-jetson-test/out
cp qy-arm64-images.tar.gz qy-jetson-config.tar.gz SHA256SUMS qy-jetson-test/out/
cd qy-jetson-test
gunzip -c out/qy-arm64-images.tar.gz | docker load
cp .env.example .env
chmod 600 .env
# Sửa .env: password, tag image đúng bản build, hostname/port và station test.
docker image inspect --format '{{.Architecture}}' visiontestai/frappe:qy-arm64-test1
./init-mqtt.sh
docker compose --env-file .env config --quiet
docker compose --env-file .env -p qy-jetson-test up -d
docker compose --env-file .env -p qy-jetson-test ps -a
docker compose --env-file .env -p qy-jetson-test logs --tail 100 provision backend
```

Không in `docker compose config` đầy đủ vào log công khai vì có secrets.
Project/volumes riêng theo prefix `qy-jetson-test`; không dùng project name của VPS.
Chỉ publish frontend 18080 và MQTT 11883; DB/Redis/backend/websocket không publish.
Giữ `mariadb-client.cnf` cùng Compose: file này tương thích MariaDB CLI mới với
DB 10.6 nội bộ không TLS, bao gồm bootstrap và backup/restore SQL.
MQTT mặc định bind loopback cho AC cùng host. Muốn trạm khác truy cập, đổi MQTT_BIND
thành IP LAN cụ thể và giới hạn firewall. MQTT auth/ACL chỉ cho station test.
Password file là hash nhưng vẫn cần bảo vệ thư mục trên host.

Tạo DNS LAN hoặc hosts entry `JETSON_IP qy-test.lan` trên Jetson và máy trình duyệt.
Mở `http://qy-test.lan:18080`. Host header giữ đúng hostname site.
HTTP chỉ dùng thử trong LAN; nếu dùng HTTPS, đặt reverse proxy với WebSocket forwarding
và đổi QY_BASE_URL sang URL HTTPS. Không đổi DNS production.

Lưu cấu hình AC production trước. Cấu hình AC test:
- HOSPITAL_BASE_URL=http://qy-test.lan:18080
- MQTT host=127.0.0.1, port=11883, user/password giống env
- station ID=qy-test-01 (hoặc STATION_ID đã chọn)

Kiểm tra biến thực tế trong cấu hình AC trước khi đổi; không chạy start_station.sh với
default hostname production. Không dùng chung station ID với production.

## 3. Nghiệm thu và tài nguyên

Trước khi chạy: `free -h`, `/proc/meminfo`, `df -h`, `tegrastats`.
Ghi `docker stats --no-stream`, `vmstat 1`, MemAvailable và OOM journal lúc idle,
đo nhiều phiên, migrate và backup/restore. Thu peak cgroup memory. Các cap DB/Redis/MQTT
là giới hạn ban đầu; app chưa đặt cap trước khi đo. Mục tiêu steady-state 1.5–2 GiB
chưa được kiểm chứng. Không dùng tổng các cap làm mức RAM tiêu thụ dự kiến.

Tạo Vision Measurement, kiểm tra start/cancel/status trên đúng broker test,
SmartEyes/chart/audio native, callback receive_results lưu Visual Acuity + raw trials
và link phiên, Socket.IO refresh qua frontend. Xác minh không có traffic production.
Restart Compose rồi kiểm tra site/DB vẫn còn. Cần xác minh cơ chế subscriber status
hiện tại trong AC/Frappe: stack này không tự thêm subscriber mới.

Chỉ tiếp tục chạy cùng AC nếu MemAvailable >= khoảng 1 GiB, swap không tăng liên tục,
không OOM và camera/audio/chart không khựng. Nếu không đạt: dừng thử, không cutover.

## 4. Backup, restore, upgrade

Backup trước thay đổi (thay qy-test.lan nếu đổi QY_SITE):

```bash
docker compose -p qy-jetson-test exec backend bench --site qy-test.lan backup --with-files
mkdir -p out/backup
docker compose -p qy-jetson-test cp backend:/home/frappe/frappe-bench/sites/qy-test.lan/private/backups/. out/backup/
docker compose -p qy-jetson-test cp backend:/home/frappe/frappe-bench/sites/qy-test.lan/site_config.json out/backup/site_config.json
chmod -R go-rwx out/backup
```

Giữ site_config (encryption_key), env và MQTT config ở nơi bảo mật ngoài Git.
Dừng ghi dữ liệu trong suốt backup/restore để giữ DB và file nhất quán.
Restore thử trên project test mới với hostname/ports riêng, không dùng volume production.
Sau khi project mới provision site rỗng, copy backup vào container:

```bash
docker compose -p qy-jetson-restore cp out/backup backend:/tmp/qy-backup
docker compose -p qy-jetson-restore exec backend bench --site qy-test.lan restore /tmp/qy-backup/DB.sql.gz --with-public-files /tmp/qy-backup/FILES.tar --with-private-files /tmp/qy-backup/PRIVATE.tar
docker compose -p qy-jetson-restore exec backend bench --site qy-test.lan migrate
```

Thay tên file theo backup thực tế. Giữ encryption_key nguồn khi restore; không ghi đè
nguyên site_config nguồn vì db_name/db_password của site đích khác. Kiểm tra lại config
MQTT/hostname/station sau restore trước khi bật trạm. Xác minh dữ liệu và file đọc được.

Upgrade: backup đã restore thử → build tag ARM64 mới → chuyển/load archive → dừng app
đang ghi → sửa CUSTOM_IMAGE trong env → chạy Compose up -d để provision/migrate → kiểm tra.
Nếu migration đổi schema, rollback cần restore cả DB/files/config từ backup tương thích;
đổi ngược image đơn thuần không đảm bảo rollback schema.

## 5. Dừng và quay về

```bash
docker compose --env-file .env -p qy-jetson-test down
```

Không thêm `-v`. Đưa HOSPITAL_BASE_URL, broker/port và station ID của AC về bản cấu hình
production đã lưu trước khi đo thật. VPS/DNS không đổi. Chỉ xóa volume test sau khi
xác minh đúng project và đã backup hoặc quyết định bỏ dữ liệu.
