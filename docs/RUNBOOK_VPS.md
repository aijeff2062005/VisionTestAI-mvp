# VPS — triển khai, dữ liệu và kết nối tới Jetson

Nguồn chính: [`deploy/vps/docker-compose.yml`](../deploy/vps/docker-compose.yml), [Frappe overlay](../deploy/vps/frappe/compose.yml), script build/up và app Smart Hospital. Đọc [tổng quan và ma trận kết nối](../README.md) để phân biệt địa chỉ Docker, tailnet và URL browser.

## 1. Phần chạy trên VPS

Cần `deploy/vps/`, `deploy/env/` và source của `services/hospital/smart-hospital`, `services/media_server`, `services/face_vectordb`, `services/qr_decode`. `services/hospital/hospital_api/main.py` chỉ cần nếu chạy profile bệnh viện giả lập. `aiface_bs.py` cùng folder lại chạy tại Jetson.

Compose project là **`visiontestai`**. Với Frappe phải ghép hai file Compose; chỉ chạy file gốc sẽ không có Frappe. Không khởi động đồng thời Frappe frontend và legacy hospital trên host port 8000.

| Service Compose | Chức năng | Lưu bền |
|---|---|---|
| `mqtt` | Mosquitto cổng 1883, password file | `visiontestai-mqtt-data`, file host `mosquitto_passwd` |
| `media` | API 9010, file store | `visiontestai-media-data:/data` |
| `face_vectordb` | API 8100, SQLite `faces.db`, `images/` | `visiontestai-face-vdb-data:/data` |
| `qr_decode` | API 9020, QR giải mã theo request | Không có DB/volume nghiệp vụ riêng |
| `hospital` | FastAPI/SQLite dự phòng, profile `legacy-hospital` | `visiontestai-hospital-data:/app/data` |
| `frappe-db` | MariaDB 10.6 theo Compose | `visiontestai-frappe-db:/var/lib/mysql` |
| `frappe-redis-cache` | Cache Frappe | Không có volume bền trong Compose |
| `frappe-redis-queue` | Hàng đợi, dùng cho socketio config | `visiontestai-frappe-redis-queue:/data` |
| `frappe-configurator` | Job ghi common site config | Dùng volume sites chung |
| `frappe-create-site` | Provision/migrate Trưng Vương (`frontend`) và Quân y (site theo hostname) | Dùng DB/sites; job một lần, có side effect khi chạy lại |
| `frappe-backend` | Python Frappe/Gunicorn | Volume sites/logs chung |
| `frappe-websocket` | Node socketio | Volume sites/logs chung |
| `frappe-queue-short`, `frappe-queue-long` | Worker background job | Volume sites/logs chung |
| `frappe-scheduler` | Lập lịch, gồm nightly wipe | Volume sites/logs chung |
| `frappe-frontend` | nginx host 8000 → container 8080 | Volume sites/logs chung, static assets từ image/runtime |

Tên ở bảng là **key volume trong YAML**; tên thật Docker có thể thêm prefix project. Dùng `docker volume ls`/`docker inspect` để xác nhận, không đoán tên khi backup/restore. `sites` và `logs` có key `visiontestai-frappe-sites`, `visiontestai-frappe-logs`.

Image Frappe được build theo nhánh `version-16` với ERPNext, Healthcare, Solvronix Desk và Smart Hospital. Các repo phụ thuộc không nằm đầy đủ trong checkout này; `.frappe_docker` được script clone lúc build. Branch và nhiều Python dependency chưa khóa commit/version tuyệt đối.

## 2. Triển khai mới

Thực hiện ở checkout trên VPS, trong lịch triển khai phù hợp. Đây là hướng dẫn, không phải tác vụ đã chạy trong lần rà soát.

### Chuẩn bị env và Mosquitto

```bash
test -f deploy/env/lab.env || cp deploy/env/lab.env.example deploy/env/lab.env
```

Sửa ít nhất `MQTT_USERNAME`, `MQTT_PASSWORD`, `MEDIA_TOKEN`, `FACE_VDB_API_KEY`, `MEDIA_PUBLIC_BASE`, `STATION_ID`, `FRAPPE_ADMIN_PASSWORD`, `FRAPPE_DB_ROOT_PASSWORD`. Đặt `TRUNG_VUONG_SITE_HOST=trungvuong.vision.primetek.ai` và `QUAN_Y_SITE_HOST=qdymd.vision.primetek.ai`; DNS của cả hai cần trỏ tới ingress Frappe, nơi TLS kết thúc. Có thể đặt `TRUNG_VUONG_STATION_ID` và `QUAN_Y_STATION_ID` riêng nếu mỗi site dùng trạm khác. Đặt `FACE_VDB_SEED_DEMO=0` cho dữ liệu thật; Compose mặc định seed demo nếu không override.

`MEDIA_PUBLIC_BASE` là base dùng để cấp URL cho client upload/download. `http://media:9010` dùng được giữa container, nhưng Jetson/browser thường không resolve được `media`. Chọn địa chỉ mà các client nhận grant truy cập được. URL public và URL nội bộ Frappe có thể khác nhau.

`deploy/vps/mosquitto.conf` yêu cầu password file. Biến MQTT trong Compose **không tự tạo password database** cho Mosquitto. Ví dụ dùng `mosquitto_passwd` đã cài trên host:

```bash
# Chỉ dùng -c khi tạo file lần đầu; công cụ sẽ hỏi mật khẩu.
mosquitto_passwd -c deploy/vps/mosquitto_passwd YOUR_MQTT_USERNAME
```

Đảm bảo user của container đọc được file; không commit file này. Username/password phải khớp ở broker, Frappe, Media và Jetson. Cấu hình broker hiện không có TLS listener hoặc ACL theo station trong file được cung cấp.

### Build image và mở stack

```bash
bash deploy/vps/frappe/build_image.sh
ENV_FILE="$PWD/deploy/env/lab.env" bash deploy/vps/frappe/up_frappe.sh
```

Script up sẽ dừng/xóa container legacy `hospital` nếu có, rồi up core + Frappe và chạy smoke. Nó mặc định dùng `lab.env.example` nếu không truyền `ENV_FILE`; truyền đường tuyệt đối như trên tránh nhầm.

Các bước quan trọng của job provision:

- Giữ site/database `frontend` hiện có làm Trưng Vương và tạo alias hostname đến site đó; tạo site/database `qdymd.vision.primetek.ai` riêng cho Quân y.
- Mỗi site chỉ được cài app bệnh viện tương ứng. Provision dừng nếu phát hiện app workflow đối diện đã nằm trên site.
- Ghi hostname chuẩn, MQTT/Media/QR/station URL vào site config của từng site. Station ID có thể cấu hình riêng.
- `frappe-configurator`/`frappe-create-site` kết thúc exit 0 là bình thường, không phải daemon phải luôn `Up`.

Trước lần provision đầu tiên, xác nhận hai bản ghi DNS và TLS hoạt động. Không đổi tên/xóa site `frontend`; dữ liệu Trưng Vương hiện tại nằm trong site/database đó.

Sau khi site Quân y mới được tạo, hoàn tất ERPNext Setup Wizard và tạo/chọn Company hợp lệ cho bệnh viện trước khi tạo lịch. Provision không tự tạo pháp nhân vì cần tên đăng ký, quốc gia, tiền tệ và chart of accounts chính xác.

Trên VPS Coder đã có ghi chú lịch sử về lỗi Docker overlay `function not implemented` khi recreate container. Chưa kiểm chứng lỗi đó ở host hiện tại. Với hệ thống đang phục vụ, kiểm tra backup và khả năng restart/recreate trước khi cập nhật; không áp lệnh triển khai mới một cách máy móc.

## 3. Kiểm tra dịch vụ và cấu hình site

```bash
docker compose -p visiontestai --env-file deploy/env/lab.env \
  -f deploy/vps/docker-compose.yml -f deploy/vps/frappe/compose.yml ps
curl --fail -H 'Host: trungvuong.vision.primetek.ai' http://127.0.0.1:8000/api/method/frappe.ping
curl --fail http://127.0.0.1:9010/health
curl --fail http://127.0.0.1:8100/health
curl --fail http://127.0.0.1:9020/health
docker logs --tail 100 visiontestai-frappe-backend
docker logs --tail 100 visiontestai-frappe-create-site
```

Health thành công chỉ chứng minh endpoint phản hồi. Cần kiểm tra thêm Frappe app/schema, quyền đăng nhập, MQTT auth và đường đi từ Jetson.

| Nơi cấu hình | Key tiêu biểu | Dùng cho |
|---|---|---|
| `frontend/site_config.json` / site Quân y qua `bench set-config` | `host_name` | URL callback do `frappe.utils.get_url()` sinh ra và URL browser |
| Site config | `visiontestai_mqtt_host/port/user/password`, `visiontestai_station_id` | Start/cancel đến đúng trạm |
| Site config | `visiontestai_aiface_station_url` | API AC mà **container Frappe** truy cập được |
| Site config | `visiontestai_media_base`, `visiontestai_media_token`, `visiontestai_media_public_base` | Upload ảnh nội bộ và URL mà trạm/browser dùng |
| Site config | `visiontestai_face_vectordb_url`, `visiontestai_face_vectordb_key` | Lưu gallery tổng |
| Site config | `visiontestai_qr_decode_url` | Decode CCCD; trong Docker thường `http://qr_decode:9020` |
| DocType **Connection Settings** | Face service URL, client ID/secret, project ID, access token | API GDU bên ngoài; khác settings pipeline của Jetson |
| `deploy/env/lab.env` | Các biến được Compose interpolate | Không tự đồng bộ mọi key vào site config sau khi đổi file |

Ví dụ sửa các URL không chứa secret:

```bash
docker exec visiontestai-frappe-backend bench --site frontend set-config host_name 'https://trungvuong.vision.primetek.ai'
docker exec visiontestai-frappe-backend bench --site qdymd.vision.primetek.ai set-config host_name 'https://qdymd.vision.primetek.ai'
docker exec visiontestai-frappe-backend bench --site frontend set-config visiontestai_aiface_station_url 'http://YOUR_JETSON_TAILNET_IP:8088'
docker exec visiontestai-frappe-backend bench --site frontend clear-cache
docker exec visiontestai-frappe-backend bench --site qdymd.vision.primetek.ai clear-cache
```

`set_site_clinic_config.sh` hỗ trợ nhiều key, nhưng default còn có mic Mac `8092` và gateway Docker `172.18.0.1:18088`. Chỉ dùng sau khi kiểm tra/ghi đè các giá trị. Connection Settings GDU ưu tiên dữ liệu DocType, rồi `frappe.conf`, rồi biến môi trường theo helper `service/face_service.py`; không phải chỉ sửa `lab.env` là GDU đổi cấu hình.

## 4. Kết nối VPS ↔ Jetson

### VPS có route tailnet bình thường

Jetson dùng IP tailnet VPS để tới MQTT/Media/gallery; dùng Frappe domain hoặc IP/cổng phù hợp cho API. Chiều ngược, Frappe container phải truy cập được IP Jetson:8088. Kiểm tra **từ container**, không chỉ curl trên host:

```bash
docker exec visiontestai-frappe-backend curl --fail --connect-timeout 5 \
  'http://YOUR_JETSON_TAILNET_IP:8088/api/face/health'
```

Đừng đặt `localhost:8088` trong Frappe để chỉ Jetson; đó là loopback của container.

### VPS dùng tailscaled userspace

Nếu host có SOCKS5 `127.0.0.1:1055` nhưng Docker không route được `100.x`, đường phụ trong repo là:

```text
Frappe container → IP gateway host:18088
  → deploy/vps/jetson_socks_proxy.py
  → SOCKS5 tailscaled 127.0.0.1:1055
  → Jetson tailnet IP:8088
```

```bash
JETSON_HOST=YOUR_JETSON_TAILNET_IP bash deploy/vps/start_jetson_proxy.sh
```

`JETSON_HOST` phải là IPv4 trong implementation hiện tại (`socket.inet_aton`). IP Jetson mặc định trong proxy là giá trị lịch sử. Lấy gateway bằng inspect mạng Docker đang dùng; không cố định `172.18.0.1` nếu topology khác.

Proxy đang chạy bằng `nohup` và pid/log trong `/tmp`, chưa có systemd unit trong repo. Mặc định bind `0.0.0.0:18088`, không có auth riêng; giới hạn phạm vi truy cập theo mạng triển khai. Khởi động thành công không có nghĩa sẽ tự sống lại sau reboot.

### Domain, HTTPS và Funnel

Repo có script Tailscale Funnel nhưng không có manifest reverse proxy đầy đủ cho domain `vision-demo.primetek.ai` đang xuất hiện trong YAML. Vì vậy không thể suy ra domain đó đang trỏ vào VPS nào từ source.

`tailscale_clinic_up.sh` còn xử lý port 8101/8443 của workload POLAR-AD ngoài phạm vi VisionTestAI. Không dùng script này nguyên trạng trên VPS dùng chung nếu chỉ muốn cấu hình Frappe. `tailscale_chart_funnel.sh` trên Jetson có thể công khai cả settings/face API cùng chart; cần xử lý quyền truy cập trước khi mở rộng phạm vi người dùng.

`mac_lan_bridge.sh` là đường SSH tunnel chạy **trên Mac/máy điều hành**, dù file ở `deploy/vps`; không phải service bắt buộc khi tailnet trực tiếp hoạt động.

## 5. Cập nhật source và schema

Đường tái lập là build image mới và triển khai có backup. Giữ mã ở backend, worker ngắn/dài, scheduler và static assets frontend cùng phiên bản. Sửa source trong container đơn lẻ là thay đổi tạm, mất khi recreate từ image cũ.

`deploy_smart_hospital.sh` là hot-deploy shared app từ máy có source/SSH:

- Copy toàn bộ app vào backend, một số JS cấp trên vào frontend rồi migrate/clear-cache cả hai site.
- Mặc định **không restart backend**; `RESTART_BACKEND=1` mới restart.
- Không cập nhật app cho tất cả worker/scheduler, không tự migrate DocType, không copy lại toàn bộ vendor assets.
- Lệnh tar có cờ cho macOS, cần kiểm tra khả năng chạy trên GNU tar/Linux.

Do đó đừng dùng thông báo “done” của script làm bằng chứng Python, background job và schema đều đã đồng bộ. `check_smart_hospital_deploy.sh --local/--remote/--both` kiểm tra **file tồn tại**, không so hash/nội dung và không thay thế migration test.

Sau khi đã triển khai đúng code vào toàn stack, với thay đổi schema/hooks:

```bash
docker exec visiontestai-frappe-backend bench --site frontend migrate
docker exec visiontestai-frappe-backend bench --site frontend clear-cache
docker exec visiontestai-frappe-backend bench --site qdymd.vision.primetek.ai migrate
docker exec visiontestai-frappe-backend bench --site qdymd.vision.primetek.ai clear-cache
```

Migration có thể tạo/đổi dữ liệu và chạy `after_migrate`, cần đưa vào lịch cập nhật. `fix_mjs_mime.sh` sửa MIME `.mjs`/thư mục buffer nginx của container đang chạy; thay đổi này cũng cần đưa vào image/config tái lập nếu tiếp tục cần sau rebuild. `nginx/frappe.conf` không được mount tường minh trong overlay hiện tại.

## 6. Dữ liệu, backup và khôi phục

| Dữ liệu | Nơi lưu | Phải giữ để làm gì |
|---|---|---|
| Patient, Appointment, Vision Measurement, Visual Acuity, đơn kính | MariaDB Frappe | Nghiệp vụ và liên kết bệnh nhân |
| File Frappe, site config, encryption key | Volume sites | Ảnh/files, cấu hình và khả năng giải mã credential |
| Ảnh/media | Volume Media `/data` | URL trong Patient/gallery cần object tương ứng |
| Gallery metadata/ảnh/template | Volume Face DB `/data` | Đồng bộ panel; không thay thế Patient DB |
| Results JSON/JSONL/WAV tại trạm | Jetson AC `data/journals` | Bản cứu callback lỗi và bằng chứng phiên |
| Gallery trên panel | Bộ nhớ AiFace | Bản sao nhận diện theo lịch; có prune/wipe |

Backup Frappe điển hình trong container:

```bash
docker exec visiontestai-frappe-backend bench --site frontend backup --with-files
docker exec visiontestai-frappe-backend bench --site qdymd.vision.primetek.ai backup --with-files
```

Copy bộ backup và site config cần thiết ra kho backup có kiểm soát; backup Media và Face DB nhất quán ở cùng mốc. Với SQLite đang ghi, dùng phương pháp backup nhất quán hoặc dừng ghi có kế hoạch; không coi copy một file đang thay đổi là bản backup đã được xác minh. Backup DB mà bỏ Media sẽ để lại liên kết ảnh hỏng.

`deploy/vps/frappe/backup/` có sẵn dump SQL, public/private tar và site config cũ **đang tracked**. Không dùng chúng làm fixture công khai hoặc tự động restore khi triển khai mới; có khả năng chứa dữ liệu thật/credential. Lần rà soát chỉ ghi nhận loại file, không giải nén dữ liệu bệnh nhân vào docs.

Thứ tự phục hồi cần kiểm chứng trên môi trường riêng: image/app đúng phiên bản → DB/sites/files → Media/gallery → endpoint/config → migration nếu phù hợp → kiểm tra Patient và kết quả mẫu → cho Jetson sync lại gallery hôm nay. Không tự restore đè site đang dùng. Không chạy `docker compose down -v`, `docker system prune` hoặc thao tác toàn host để xử lý lỗi một service.

## 7. Chẩn đoán

| Lỗi | Kiểm tra |
|---|---|
| Frappe 502/không mở | frontend/backend, job create-site, MariaDB, Redis; DNS/TLS và Host header phải khớp site hostname |
| Vào nhầm bệnh viện | Hostname request, thư mục/alias site, `TRUNG_VUONG_SITE_HOST`, `QUAN_Y_SITE_HOST`; xem `bench list-sites` và `bench --site SITE list-apps` |
| Redirect sang host cũ/login khi callback | `host_name` của đúng site, URL từ `send_vision_measurement`, `HOSPITAL_BASE_URL` của Jetson; HTTP 3xx không được callback client coi là thành công |
| Không nhận lệnh Start | MQTT auth/password file, broker hostname trong Docker, `station_id`, AC subscription; tạo measurement chưa đồng nghĩa publish |
| Frappe báo đã gửi nhưng chart không đổi | Log broker/AC, trạng thái bận, log reconnect/backoff và `MQTT subscribed` của AC |
| Avatar đã lưu mà panel không có | Lịch hôm nay + ảnh, push job worker, Jetson pull loop, `visiontestai_aiface_station_url`, SOCKS proxy nếu cần |
| GDU đăng ký lỗi | Connection Settings, token/project, ffmpeg trong image, log `face_service_api`; GDU không phải face_vectordb:8100 |
| Media 401 | `X-Media-Token` của caller có khớp server không |
| URL ảnh không mở | Docker hostname bị trả ra client ngoài Docker; ảnh yêu cầu token header nhưng browser dùng URL trực tiếp |
| Không đọc được CCCD | QR có thật trong ảnh và đủ nét không; QR service libzbar; nhánh browser hay server đang dùng |
| Kết quả trùng/nhầm phiên | So `session_id`, `vision_measurement`, Patient ID, callback retry; không đổi session ID khi replay |
| JS mặt không load | `.mjs` MIME, static file có ở frontend, MediaPipe WASM/model tải được, HTTPS/camera permission |
| Web thay đổi nhưng background job còn hành vi cũ | Worker/scheduler chưa được cập nhật cùng backend |

## 8. Kiểm chứng end-to-end sau triển khai

Dùng hồ sơ thử nghiệm có kiểm soát: đăng ký Patient/avatar → đặt lịch hôm nay → gallery trên panel → nhận diện → chọn input → qua vị trí/che mắt → đo riêng hai mắt → journal → callback → Visual Acuity/letter rows → bác sĩ xem. Thử hủy đúng phiên, mất broker lúc boot, callback lỗi và gửi lại cùng ID. Đây là danh sách kiểm chứng còn cần thực hiện trên thiết bị; **133 test local không thay thế chuỗi này**.
