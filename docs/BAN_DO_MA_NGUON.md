# Bản đồ thư mục, từng file và nơi chỉnh sửa

Danh mục được lập từ file đang được Git theo dõi **và còn tồn tại** trong working tree ngày 07/10/2026, cộng hai tài liệu mới. Các docs đã bị xóa trước khi bắt đầu công việc không được dựng lại. File binary/model/dataset được phân loại theo vai trò, tham chiếu và hash khi cần; không tuyên bố đã xác minh nội dung mô hình hoặc chất lượng từng ảnh. Không đưa dữ liệu bệnh nhân/credential bên trong backup vào tài liệu.

## 1. Cây chức năng và nơi chạy

```text
mvp_platform/
├── configs/                       tham khảo topology lab, không entrypoint
├── deploy/
│   ├── env/                       biến deployment; bản thật ngoài Git
│   ├── jetson/                    chạy trạm native/systemd, mạng, chẩn đoán
│   └── vps/                       Compose core, SSH deploy, network proxy
│       └── frappe/                build/overlay Frappe, nginx, backup cũ
├── docs/                          runbook, bản đồ, đánh giá, sơ đồ lịch sử
├── services/
│   ├── assistant_controller/      JETSON: điều phối, chart, tablet, config
│   │   ├── src/ac/                logic Python
│   │   ├── configs/               profile clinic/default/demo
│   │   ├── contracts/             JSON Schema/OpenAPI tích hợp
│   │   ├── dmn/                   bảng quyết định action
│   │   ├── display/               HTML/JS/CSS và tài nguyên chart/preview
│   │   ├── control/               HTML/JS/CSS tablet, gồm phiên bản cũ
│   │   ├── scenarios/vi/          manifest và WAV giọng nam/nữ
│   │   ├── scripts/               CLI demo/sync
│   │   ├── tests/                 test logic/mocks
│   │   └── data/                  journal/WAV/log phát sinh, ngoài Git
│   ├── smarteyes/                 JETSON: CV; máy dev: demo/train
│   │   ├── src/                   detection/pose/zone/eyes/rules
│   │   ├── configs/               CV profile và sidecar vùng đứng
│   │   ├── weights/               detector tai nghe
│   │   ├── scripts/               chẩn đoán, thu data, train/export
│   │   ├── datasets/headphones/   dữ liệu cách ly, không runtime
│   │   └── outputs/               ảnh debug/probe, không runtime
│   ├── sloan_stt/                 JETSON: import runtime; web/CLI là demo
│   │   └── checkpoint/            encoder/head/labels/temperature thực dùng
│   ├── hospital/
│   │   ├── hospital_api/          main.py: VPS legacy; aiface_bs.py: JETSON
│   │   └── smart-hospital/        VPS: app Frappe
│   │       └── smart_hospital/    package Python app
│   │           ├── api/          nghiệp vụ/API clinic
│   │           ├── service/      client GDU bên ngoài
│   │           ├── overrides/    hook override Patient/Sales Order
│   │           ├── patches/      migration dữ liệu/quyền
│   │           ├── public/js/    JS quầy, MediaPipe vendor
│   │           └── smart_hospital/ module Frappe: doctype/page/workspace
│   ├── media_server/             VPS: lưu bytes trên đĩa + MQTT metadata
│   ├── face_vectordb/            VPS: SQLite gallery, chưa vector search
│   └── qr_decode/                VPS: giải mã QR CCCD
└── tmp/                           artifact local/backup giọng, ngoài Git
```

Một folder có thể chứa phần server, browser, test và tài nguyên; “chạy trên VPS” nghĩa là server/build/serve từ VPS, còn JS trang quầy thực thi trong browser. Hai lớp `smart_hospital/smart_hospital` là cấu trúc app/package/module của Frappe, không phải bản copy thừa. Folder `__init__.py`, `.frappe`, JSON DocType/Page/Workspace có ý nghĩa với framework dù ít hoặc không có logic.

## 2. Tra nơi sửa theo yêu cầu

| Muốn sửa | Bắt đầu ở đâu | Kiểm tra kèm |
|---|---|---|
| IP, endpoint, audio/camera thiết bị | AC `configs/clinic.yaml`, `config.py`, `deploy/env/lab.env`, `start_station.sh` | Settings UI có ghi env không; thứ tự VPS_HOST override |
| Trang/route/operator settings | `display_client.py`, `display/preview.html` | Auth và restart/hot-reload |
| Chart/kích thước/font | `display/chart.js`, `chart.css`, `index.html`, `display.*` | Thước thực, fullscreen, browser metrics |
| Tablet/bàn phím/input mode | `control/real.html`, `real-integration.js`, `DisplayHub`, `UiSttBridge` | window_id/deadline, mode exclusive |
| Đổi quy trình các bước | `orchestrator.py`, `dmn/acuity_flow.dmn`, `dmn_engine.py` | DMN không chứa mọi logic; kiểm session/cancel |
| Điểm, mức bắt đầu/search | `scoring.py`, `age_va.py`, `ProtocolConfig`, nhánh RECORD | Range không được thành kết quả cuối |
| Ngưỡng giọng/VAD | `readiness_bridge.py`, `sloan_stt/runtime.py`, clinic YAML | Waveform/labels/margin và classifier checkpoint |
| Bắt camera/vùng đứng/che mắt | `smarteyes/src/`, `configs/clinic_jetson.yaml`, `stand_zone.json` | Mirror, ánh sáng, gate AC có forced/timeout |
| Nhận diện và đồng bộ panel | `face_client.py`, `face_sync.py`, `face_gallery_loop.py`, `aiface_bs.py` | Callback LAN, ID Patient, prune/wipe |
| Patient/đặt lịch/đơn kính | Frappe `api/clinic_desk.py`, `face_identity.py`, `smart_hospital/page`, DocTypes | Quyền, hooks, migration và worker |
| GDU face registration | `api/face_service_api.py`, `service/face_service.py`, Connection Settings | ffmpeg, token, URL service ngoài repo |
| Callback và lưu kết quả | `http_callback.py`, `_submit`, Frappe `api/vision.py` | Unique session_id đã migrate, raw data/ACK |
| Lưu ảnh/âm thanh | `media_server/app`, AC `media_client.py`, `letter_clip.py` | URL client truy cập được, token, retention |
| QR CCCD | `qr_decode/app/main.py`, AC `cccd_qr.py`, Frappe `clinic_desk.py`, browser scanner | Nhánh upload URL/browser và input validation |
| Dependency/image/khởi động | `requirements*`, `pyproject`, Dockerfiles, `deploy/` | Wheel Jetson và version toàn backend/worker |

## 3. Thư mục sinh tự động hoặc ngoài danh mục Git

- `.git/`: lịch sử/index/objects của Git, không triển khai như ứng dụng.
- `.venv/`, `node_modules/`: dependency theo môi trường; không phải source tự viết. Giữ bản ghi version/wheel trước khi dựng lại Jetson.
- `__pycache__/`, `.pytest_cache/`: cache tái tạo được, không phải logic.
- `services/assistant_controller/data/`: journal, kết quả, clip và log thực; dù ignored vẫn là dữ liệu quan trọng.
- `services/media_server/data/`, `face_vectordb/data/`, `hospital_api/data/` nếu chạy native: tương đương data root local; Docker thường dùng volume `/data` hoặc `/app/data`.
- `tmp/face_preview/`: ảnh preview local; `tmp/voice_backup_pre_v2_*/`: backup giọng cũ. Không liệt kê danh tính/giá trị dữ liệu vào docs.
- `deploy/env/lab.env`, `.env`, `deploy/vps/mosquitto_passwd`: config/secret thật nếu được tạo; không có đầy đủ trong checkout hiện tại.
- `deploy/vps/frappe/.frappe_docker/`: clone upstream do build script tạo, không phải app Smart Hospital tự viết.
- Weight CLIP bị ignore trong `.gitignore`: tài nguyên cho backend thử nghiệm nếu có cài; profile clinic hiện tắt headphones.

## 4. Danh mục từng file

Các bảng dưới ghi **mọi file tracked hiện hữu** và hai docs mới, nhóm theo folder; tên file là link tới source. Dataset/clip/vendor có nhiều file cùng cơ chế nên mô tả theo stem/vai trò, không đánh đồng với code nghiệp vụ. Tiêu đề folder trong mỗi nhóm cho biết đường dẫn đầy đủ. Xem [đánh giá legacy/dọn dẹp](THUAT_TOAN_VA_DANH_GIA.md) trước khi xóa bất kỳ nhóm nào.

Tổng danh mục: **978 file** (không tính file ignored, Git internals hoặc docs đã bị xóa trước công việc).

<details>
<summary>. — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [.gitignore](../.gitignore) | Quy tắc bỏ qua venv, data, cache, env thật, tmp và một số model lớn; không tự bỏ file đã tracked. |
| [README.md](../README.md) | Tài liệu chính số 1: tổng quan, thiết bị, kết nối, luồng nghiệp vụ và trạng thái kiểm chứng. |
| [yolov8n.pt](../yolov8n.pt) | Weight YOLOv8n dò người; trùng bytes với bản trong assistant_controller, lưu ý cwd khi load. |

</details>

<details>
<summary>configs — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [lab.yaml](../configs/lab.yaml) | Topology/endpoint tham khảo lab; không được main AC tự nạp thay clinic.yaml. |

</details>

<details>
<summary>deploy/env — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [connection_settings.local.json](../deploy/env/connection_settings.local.json) | Cấu hình Connection Settings triển khai đã tracked; có thể chứa credential, không sao chép giá trị vào docs. |
| [lab.env.example](../deploy/env/lab.env.example) | Mẫu biến triển khai; start_station và nhiều script fallback vào đây nếu thiếu env thật. |
| [lab.env.tailscale.example](../deploy/env/lab.env.tailscale.example) | Mẫu endpoint tailnet/Funnel; không phải env production tự động được nạp. |

</details>

<details>
<summary>deploy/jetson — 10 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [advertise_clinic_lan.sh](../deploy/jetson/advertise_clinic_lan.sh) | Bật forwarding và quảng bá subnet LAN qua Jetson; có hardcoded cách gọi sudo cần sửa trước dùng. |
| [camera_preview.py](../deploy/jetson/camera_preview.py) | MJPEG camera preview tối giản độc lập, mặc định 8090; dùng chẩn đoán, tránh tranh camera AC. |
| [clinic-station.service](../deploy/jetson/clinic-station.service) | systemd user unit, restart luôn, đường dẫn tuyệt đối cần đổi theo máy. |
| [docker-compose.yml](../deploy/jetson/docker-compose.yml) | Đường Docker trạm phụ, host networking; chưa tương đương runtime native clinic. |
| [enable_bluetooth_audio.sh](../deploy/jetson/enable_bluetooth_audio.sh) | Cấu hình Bluetooth audio Jetson; thao tác hệ điều hành, không phải dependency mặc định của USB dongle. |
| [install_autostart.sh](../deploy/jetson/install_autostart.sh) | Cài user unit/linger và thêm cron reboot; cần tránh chạy chồng hai cơ chế. |
| [join_tailscale.sh](../deploy/jetson/join_tailscale.sh) | Cài/join Tailscale trên Jetson; ví dụ IP/log cuối script có thể cũ. |
| [start_station.sh](../deploy/jetson/start_station.sh) | Entrypoint native: nạp env, chọn audio, mở BS rồi exec AC profile clinic. |
| [sync_faces.sh](../deploy/jetson/sync_faces.sh) | Nạp env và gọi script đồng bộ gallery VectorDB xuống panel; là thao tác ghi thiết bị. |
| [tailscale_chart_funnel.sh](../deploy/jetson/tailscale_chart_funnel.sh) | Expose origin chart qua Funnel HTTPS; gồm cả API cùng origin, cần xét quyền truy cập. |

</details>

<details>
<summary>deploy/vps — 10 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [check_smart_hospital_deploy.sh](../deploy/vps/check_smart_hospital_deploy.sh) | Kiểm file hook/API/page/asset cần thiết tồn tại local/remote; không so version hay test nghiệp vụ. |
| [deploy_smart_hospital.sh](../deploy/vps/deploy_smart_hospital.sh) | Hot-copy app backend và JS frontend qua SSH; chưa đồng bộ toàn worker/schema. |
| [docker-compose.yml](../deploy/vps/docker-compose.yml) | Core MQTT/Media/Face DB/QR và profile legacy hospital; ghép Frappe overlay khi dùng bệnh viện thật. |
| [jetson_socks_proxy.py](../deploy/vps/jetson_socks_proxy.py) | TCP bridge host 18088 qua tailscaled SOCKS5 1055 tới IPv4 Jetson:8088. |
| [mac_lan_bridge.sh](../deploy/vps/mac_lan_bridge.sh) | Chạy trên Mac/máy điều hành để SSH-forward cổng VPS ra LAN; đường lab cũ. |
| [mosquitto.conf](../deploy/vps/mosquitto.conf) | Listener/auth/persistence Mosquitto; yêu cầu file password host bên ngoài Git. |
| [remote_up.sh](../deploy/vps/remote_up.sh) | Máy quản trị SSH/sync source rồi up VPS, có nhánh FRAPPE/LEGACY_HOSPITAL; kiểm path/host trước chạy. |
| [set_site_clinic_config.sh](../deploy/vps/set_site_clinic_config.sh) | Ghi các endpoint vào Frappe site config; default có IP gateway/mic Mac lịch sử. |
| [start_jetson_proxy.sh](../deploy/vps/start_jetson_proxy.sh) | Khởi động proxy bằng nohup, ghi PID/log vào /tmp; chưa có supervisor trong repo. |
| [tailscale_clinic_up.sh](../deploy/vps/tailscale_clinic_up.sh) | Setup Funnel VPS và smoke; còn chạm nhánh POLAR-AD ngoài dự án, cần tách trước dùng. |

</details>

<details>
<summary>deploy/vps/frappe — 7 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [.gitignore](../deploy/vps/frappe/.gitignore) | Bỏ clone/build artifact cục bộ của Frappe deployment. |
| [Dockerfile.smart](../deploy/vps/frappe/Dockerfile.smart) | Layer Smart Hospital và dependency paho/ffmpeg lên base ERPNext+Healthcare+Solvronix. |
| [README.md](../deploy/vps/frappe/README.md) | Hướng dẫn triển khai lịch sử; có endpoint, password mặc định và đường dẫn cũ, ưu tiên runbook chính. |
| [apps.json](../deploy/vps/frappe/apps.json) | Danh sách repo/branch ERPNext, Healthcare, Solvronix Desk để build base image. |
| [build_image.sh](../deploy/vps/frappe/build_image.sh) | Clone frappe_docker, build base/custom image bằng BuildKit apps_json secret, kiểm imports. |
| [compose.yml](../deploy/vps/frappe/compose.yml) | Overlay Frappe gồm MariaDB/Redis/jobs/backend/workers/scheduler/websocket/frontend và volumes. |
| [up_frappe.sh](../deploy/vps/frappe/up_frappe.sh) | Dừng legacy hospital, up core+Frappe, tạo/migrate site và smoke health. |

</details>

<details>
<summary>deploy/vps/frappe/backup — 4 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [20260911_230839-frontend-database.sql.gz](../deploy/vps/frappe/backup/20260911_230839-frontend-database.sql.gz) | Backup database SQL nén; không giải nén/chia sẻ làm fixture. |
| [20260911_230839-frontend-files.tar](../deploy/vps/frappe/backup/20260911_230839-frontend-files.tar) | Backup file Frappe public/private theo hậu tố tên; dữ liệu cần bảo vệ. |
| [20260911_230839-frontend-private-files.tar](../deploy/vps/frappe/backup/20260911_230839-frontend-private-files.tar) | Backup file Frappe public/private theo hậu tố tên; dữ liệu cần bảo vệ. |
| [20260911_230839-frontend-site_config_backup.json](../deploy/vps/frappe/backup/20260911_230839-frontend-site_config_backup.json) | Backup site config, có thể chứa thông tin bí mật; không đưa giá trị vào docs. |

</details>

<details>
<summary>deploy/vps/frappe/nginx — 2 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [fix_mjs_mime.sh](../deploy/vps/frappe/nginx/fix_mjs_mime.sh) | Sửa MIME .mjs và thư mục buffering trong frontend đang chạy; thay đổi container tạm thời. |
| [frappe.conf](../deploy/vps/frappe/nginx/frappe.conf) | Mẫu nginx site/proxy/static; chưa được mount tường minh bởi Compose overlay hiện tại. |

</details>

<details>
<summary>docs — 5 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [BAN_DO_MA_NGUON.md](../docs/BAN_DO_MA_NGUON.md) | Tài liệu chính số 4: bản đồ folder, nơi sửa và danh mục từng file hiện hữu. |
| [RUNBOOK_JETSON.md](../docs/RUNBOOK_JETSON.md) | Tài liệu chính số 2: cài/chạy/sửa cấu hình trạm và cứu kết quả. |
| [RUNBOOK_VPS.md](../docs/RUNBOOK_VPS.md) | Tài liệu chính số 3: dịch vụ VPS, mạng, cập nhật, backup. |
| [THUAT_TOAN_VA_DANH_GIA.md](../docs/THUAT_TOAN_VA_DANH_GIA.md) | Tài liệu chính số 5: thuật toán thực tế, điểm yếu, legacy và kế hoạch kiểm chứng. |
| [network-flow.drawio](../docs/network-flow.drawio) | Sơ đồ mạng dạng diagrams.net từ tài liệu cũ; cần đối chiếu endpoint/luồng trong README mới. |

</details>

<details>
<summary>services/assistant_controller — 9 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [.env.example](../services/assistant_controller/.env.example) | Mẫu env riêng service AC; không thay thế quy trình lab.env của start_station. |
| [.gitignore](../services/assistant_controller/.gitignore) | Các file local của service cần bỏ qua. |
| [Dockerfile](../services/assistant_controller/Dockerfile) | Image AC cơ bản; CMD default.yaml và không đóng gói đủ sibling model/CV cho native clinic. |
| [README.md](../services/assistant_controller/README.md) | Hướng dẫn service lịch sử; đối chiếu lại clinic config và bộ docs chính. |
| [pyproject.toml](../services/assistant_controller/pyproject.toml) | Metadata package/build/test configuration cho AC. |
| [requirements-clinic.txt](../services/assistant_controller/requirements-clinic.txt) | Dependency CV clinic; chưa khóa một bộ wheel Jetson tái lập hoàn chỉnh. |
| [requirements.txt](../services/assistant_controller/requirements.txt) | Dependency core AC và pytest, phần hardware chỉ chú thích là tùy chọn. |
| [ung-dung-do-mat-tablet (1).html](../services/assistant_controller/ung-dung-do-mat-tablet%20%281%29.html) | Bản giao diện tablet tham khảo/cũ; không phải file hiện được route /control trả về. |
| [yolov8n.pt](../services/assistant_controller/yolov8n.pt) | Weight dò người theo cwd AC; cùng SHA-256 với weight root repo. |

</details>

<details>
<summary>services/assistant_controller/configs — 4 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [clinic.yaml](../services/assistant_controller/configs/clinic.yaml) | Profile trạm native hiện tại; có chỉnh sửa người dùng trước lần viết docs, được giữ nguyên. |
| [clinic_confirm.yaml](../services/assistant_controller/configs/clinic_confirm.yaml) | Profile phụ Model A-only mang tên cũ; có comment cách gọi chưa khớp AC_CONFIG. |
| [clinic_happy_path.yaml](../services/assistant_controller/configs/clinic_happy_path.yaml) | Profile mock readiness/STT/no-face để demo; script shell có thể override các giá trị. |
| [default.yaml](../services/assistant_controller/configs/default.yaml) | Profile default/demo của module và image; không mặc định tương đương clinic. |

</details>

<details>
<summary>services/assistant_controller/contracts — 5 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [openapi.yaml](../services/assistant_controller/contracts/openapi.yaml) | Hợp đồng API/protocol tham khảo; không phải router tự sinh của display FastAPI. |
| [results_callback.schema.json](../services/assistant_controller/contracts/results_callback.schema.json) | JSON Schema callback điểm và protocol; đối chiếu models.py khi thêm field. |
| [session_cancel.schema.json](../services/assistant_controller/contracts/session_cancel.schema.json) | JSON Schema message hủy phiên. |
| [session_start.schema.json](../services/assistant_controller/contracts/session_start.schema.json) | JSON Schema của message bắt đầu phiên. |
| [session_status.schema.json](../services/assistant_controller/contracts/session_status.schema.json) | JSON Schema trạng thái phiên trạm. |

</details>

<details>
<summary>services/assistant_controller/control — 7 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [bv_logo.jpg](../services/assistant_controller/control/bv_logo.jpg) | Logo dùng trong giao diện điều khiển. |
| [control-integration.js](../services/assistant_controller/control/control-integration.js) | Adapter WS cho index.html cũ. |
| [control.css](../services/assistant_controller/control/control.css) | Style tablet thế hệ cũ; kiểm HTML references trước bỏ. |
| [control.js](../services/assistant_controller/control/control.js) | Implementation điều khiển tablet cũ, cần tra caller trước dọn. |
| [index.html](../services/assistant_controller/control/index.html) | UI tablet thế hệ trước; không phải route /control hiện tại. |
| [real-integration.js](../services/assistant_controller/control/real-integration.js) | WebSocket tablet hiện tại: input mode, window/deadline, gửi đáp án và hiển thị trạng thái. |
| [real.html](../services/assistant_controller/control/real.html) | UI tablet hiện tại, được cả /control và /control-real phục vụ. |

</details>

<details>
<summary>services/assistant_controller/control/fonts — 2 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [OFL-Roboto.txt](../services/assistant_controller/control/fonts/OFL-Roboto.txt) | Giấy phép font Roboto, giữ khi phân phối font. |
| [Roboto-VF.ttf](../services/assistant_controller/control/fonts/Roboto-VF.ttf) | Font Roboto của tablet. |

</details>

<details>
<summary>services/assistant_controller/display — 7 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [chart.css](../services/assistant_controller/display/chart.css) | Style/layout chart, fullscreen, kết quả và thước hiệu chuẩn. |
| [chart.css.bak](../services/assistant_controller/display/chart.css.bak) | Bản backup CSS thủ công, ứng viên dọn sau diff. |
| [chart.js](../services/assistant_controller/display/chart.js) | Render glyph, kích thước vật lý/calibration, nhận command WS, scene/audio và browser mic tùy chọn. |
| [chart.js.bak](../services/assistant_controller/display/chart.js.bak) | Bản backup JavaScript thủ công, không phải script chính của chart. |
| [favicon.svg](../services/assistant_controller/display/favicon.svg) | Biểu tượng trình duyệt chart. |
| [index.html](../services/assistant_controller/display/index.html) | Trang chart chính được route / phục vụ. |
| [preview.html](../services/assistant_controller/display/preview.html) | Camera preview, vùng đứng, cấu hình pipeline/display và công cụ operator. |

</details>

<details>
<summary>services/assistant_controller/display/art — 9 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [OPTICIAN_SANS_LICENSE.md](../services/assistant_controller/display/art/OPTICIAN_SANS_LICENSE.md) | Thông tin giấy phép font Optician Sans. |
| [Optician-Sans.woff](../services/assistant_controller/display/art/Optician-Sans.woff) | Font Optician Sans để vẽ optotype; giữ cùng license và kiểm font loaded khi hiệu chuẩn. |
| [huongdanquetkhuonmat.jpg](../services/assistant_controller/display/art/huongdanquetkhuonmat.jpg) | Ảnh minh họa scene `huongdanquetkhuonmat` trên chart; bản optimized giảm dung lượng nếu có. |
| [huongdanquetkhuonmat_optimized.jpg](../services/assistant_controller/display/art/huongdanquetkhuonmat_optimized.jpg) | Ảnh minh họa scene `huongdanquetkhuonmat_optimized` trên chart; bản optimized giảm dung lượng nếu có. |
| [idle_person.webp](../services/assistant_controller/display/art/idle_person.webp) | Ảnh minh họa scene `idle_person` trên chart; bản optimized giảm dung lượng nếu có. |
| [stand_person.webp](../services/assistant_controller/display/art/stand_person.webp) | Ảnh minh họa scene `stand_person` trên chart; bản optimized giảm dung lượng nếu có. |
| [unclear_person.webp](../services/assistant_controller/display/art/unclear_person.webp) | Ảnh minh họa scene `unclear_person` trên chart; bản optimized giảm dung lượng nếu có. |
| [vitringoi.jpg](../services/assistant_controller/display/art/vitringoi.jpg) | Ảnh minh họa scene `vitringoi` trên chart; bản optimized giảm dung lượng nếu có. |
| [vitringoi_optimized.jpg](../services/assistant_controller/display/art/vitringoi_optimized.jpg) | Ảnh minh họa scene `vitringoi_optimized` trên chart; bản optimized giảm dung lượng nếu có. |

</details>

<details>
<summary>services/assistant_controller/display/prompts/vi — 28 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [cover_left_eye.wav](../services/assistant_controller/display/prompts/vi/cover_left_eye.wav) | Clip hướng dẫn tiếng Việt `cover_left_eye`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [cover_right_eye.wav](../services/assistant_controller/display/prompts/vi/cover_right_eye.wav) | Clip hướng dẫn tiếng Việt `cover_right_eye`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [explain_rules.wav](../services/assistant_controller/display/prompts/vi/explain_rules.wav) | Clip hướng dẫn tiếng Việt `explain_rules`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [input_mode_choose.wav](../services/assistant_controller/display/prompts/vi/input_mode_choose.wav) | Clip hướng dẫn tiếng Việt `input_mode_choose`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [input_mode_speak.wav](../services/assistant_controller/display/prompts/vi/input_mode_speak.wav) | Clip hướng dẫn tiếng Việt `input_mode_speak`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [input_mode_tablet.wav](../services/assistant_controller/display/prompts/vi/input_mode_tablet.wav) | Clip hướng dẫn tiếng Việt `input_mode_tablet`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [left_eye_complete.wav](../services/assistant_controller/display/prompts/vi/left_eye_complete.wav) | Clip hướng dẫn tiếng Việt `left_eye_complete`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [letter_C.wav](../services/assistant_controller/display/prompts/vi/letter_C.wav) | Clip hướng dẫn tiếng Việt `letter_C`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [letter_D.wav](../services/assistant_controller/display/prompts/vi/letter_D.wav) | Clip hướng dẫn tiếng Việt `letter_D`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [letter_H.wav](../services/assistant_controller/display/prompts/vi/letter_H.wav) | Clip hướng dẫn tiếng Việt `letter_H`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [letter_K.wav](../services/assistant_controller/display/prompts/vi/letter_K.wav) | Clip hướng dẫn tiếng Việt `letter_K`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [letter_N.wav](../services/assistant_controller/display/prompts/vi/letter_N.wav) | Clip hướng dẫn tiếng Việt `letter_N`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [letter_O.wav](../services/assistant_controller/display/prompts/vi/letter_O.wav) | Clip hướng dẫn tiếng Việt `letter_O`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [letter_R.wav](../services/assistant_controller/display/prompts/vi/letter_R.wav) | Clip hướng dẫn tiếng Việt `letter_R`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [letter_S.wav](../services/assistant_controller/display/prompts/vi/letter_S.wav) | Clip hướng dẫn tiếng Việt `letter_S`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [letter_V.wav](../services/assistant_controller/display/prompts/vi/letter_V.wav) | Clip hướng dẫn tiếng Việt `letter_V`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [letter_Z.wav](../services/assistant_controller/display/prompts/vi/letter_Z.wav) | Clip hướng dẫn tiếng Việt `letter_Z`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [metadata.csv](../services/assistant_controller/display/prompts/vi/metadata.csv) | Metadata nội dung/audio của bộ prompt trong folder; hỗ trợ tra cứu/chỉnh giọng, không chứa logic đo. |
| [metadata.json](../services/assistant_controller/display/prompts/vi/metadata.json) | Metadata nội dung/audio của bộ prompt trong folder; hỗ trợ tra cứu/chỉnh giọng, không chứa logic đo. |
| [open_both_eyes.wav](../services/assistant_controller/display/prompts/vi/open_both_eyes.wav) | Clip hướng dẫn tiếng Việt `open_both_eyes`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [position_stable.wav](../services/assistant_controller/display/prompts/vi/position_stable.wav) | Clip hướng dẫn tiếng Việt `position_stable`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [return_waiting.wav](../services/assistant_controller/display/prompts/vi/return_waiting.wav) | Clip hướng dẫn tiếng Việt `return_waiting`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [right_eye_complete.wav](../services/assistant_controller/display/prompts/vi/right_eye_complete.wav) | Clip hướng dẫn tiếng Việt `right_eye_complete`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [start_both_eyes.wav](../services/assistant_controller/display/prompts/vi/start_both_eyes.wav) | Clip hướng dẫn tiếng Việt `start_both_eyes`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [start_left_eye.wav](../services/assistant_controller/display/prompts/vi/start_left_eye.wav) | Clip hướng dẫn tiếng Việt `start_left_eye`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [start_right_eye.wav](../services/assistant_controller/display/prompts/vi/start_right_eye.wav) | Clip hướng dẫn tiếng Việt `start_right_eye`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [test_complete.wav](../services/assistant_controller/display/prompts/vi/test_complete.wav) | Clip hướng dẫn tiếng Việt `test_complete`; prompt fallback cho browser/audio. Một số tên là bước legacy. |
| [welcome_ready.wav](../services/assistant_controller/display/prompts/vi/welcome_ready.wav) | Clip hướng dẫn tiếng Việt `welcome_ready`; prompt fallback cho browser/audio. Một số tên là bước legacy. |

</details>

<details>
<summary>services/assistant_controller/dmn — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [acuity_flow.dmn](../services/assistant_controller/dmn/acuity_flow.dmn) | Bảng FIRST quyết định action từ state/facts; cần phối hợp logic Python. |

</details>

<details>
<summary>services/assistant_controller/docs — 8 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [DEMO.md](../services/assistant_controller/docs/DEMO.md) | Tài liệu tham khảo demo service; đối chiếu code và bộ docs chính, không là bằng chứng validation. |
| [contracts.md](../services/assistant_controller/docs/contracts.md) | Tài liệu tham khảo hợp đồng tích hợp; đối chiếu code và bộ docs chính, không là bằng chứng validation. |
| [demo_flow.md](../services/assistant_controller/docs/demo_flow.md) | Tài liệu tham khảo flow demo; đối chiếu code và bộ docs chính, không là bằng chứng validation. |
| [face_devices.md](../services/assistant_controller/docs/face_devices.md) | Tài liệu tham khảo thiết bị face/two-panel định hướng; đối chiếu code và bộ docs chính, không là bằng chứng validation. |
| [face_vectordb.md](../services/assistant_controller/docs/face_vectordb.md) | Tài liệu tham khảo gallery sync; đối chiếu code và bộ docs chính, không là bằng chứng validation. |
| [lux_calibration.md](../services/assistant_controller/docs/lux_calibration.md) | Tài liệu tham khảo đo/hiệu chuẩn ánh sáng; đối chiếu code và bộ docs chính, không là bằng chứng validation. |
| [occluder_diy.md](../services/assistant_controller/docs/occluder_diy.md) | Tài liệu tham khảo miếng che mắt; đối chiếu code và bộ docs chính, không là bằng chứng validation. |
| [vn_standard_compliance.md](../services/assistant_controller/docs/vn_standard_compliance.md) | Tài liệu tham khảo đối chiếu quy trình/tiêu chuẩn theo tài liệu cũ; đối chiếu code và bộ docs chính, không là bằng chứng validation. |

</details>

<details>
<summary>services/assistant_controller/scenarios/vi — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [manifest.yaml](../services/assistant_controller/scenarios/vi/manifest.yaml) | Mapping step→message/audio cho hướng dẫn tiếng Việt và luồng cũ tương thích. |

</details>

<details>
<summary>services/assistant_controller/scenarios/vi/female — 37 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [b10_confirm.wav](../services/assistant_controller/scenarios/vi/female/b10_confirm.wav) | Clip hướng dẫn tiếng Việt `b10_confirm`; giọng female. Một số tên là bước legacy. |
| [b3_stand.wav](../services/assistant_controller/scenarios/vi/female/b3_stand.wav) | Clip hướng dẫn tiếng Việt `b3_stand`; giọng female. Một số tên là bước legacy. |
| [b4_cover_left.wav](../services/assistant_controller/scenarios/vi/female/b4_cover_left.wav) | Clip hướng dẫn tiếng Việt `b4_cover_left`; giọng female. Một số tên là bước legacy. |
| [b4_cover_right.wav](../services/assistant_controller/scenarios/vi/female/b4_cover_right.wav) | Clip hướng dẫn tiếng Việt `b4_cover_right`; giọng female. Một số tên là bước legacy. |
| [b5_look_chart.wav](../services/assistant_controller/scenarios/vi/female/b5_look_chart.wav) | Clip hướng dẫn tiếng Việt `b5_look_chart`; giọng female. Một số tên là bước legacy. |
| [b6_read_row.wav](../services/assistant_controller/scenarios/vi/female/b6_read_row.wav) | Clip hướng dẫn tiếng Việt `b6_read_row`; giọng female. Một số tên là bước legacy. |
| [cover_left_eye.wav](../services/assistant_controller/scenarios/vi/female/cover_left_eye.wav) | Clip hướng dẫn tiếng Việt `cover_left_eye`; giọng female. Một số tên là bước legacy. |
| [cover_right_eye.wav](../services/assistant_controller/scenarios/vi/female/cover_right_eye.wav) | Clip hướng dẫn tiếng Việt `cover_right_eye`; giọng female. Một số tên là bước legacy. |
| [error_retry.wav](../services/assistant_controller/scenarios/vi/female/error_retry.wav) | Clip hướng dẫn tiếng Việt `error_retry`; giọng female. Một số tên là bước legacy. |
| [explain_rules.wav](../services/assistant_controller/scenarios/vi/female/explain_rules.wav) | Clip hướng dẫn tiếng Việt `explain_rules`; giọng female. Một số tên là bước legacy. |
| [left_eye_complete.wav](../services/assistant_controller/scenarios/vi/female/left_eye_complete.wav) | Clip hướng dẫn tiếng Việt `left_eye_complete`; giọng female. Một số tên là bước legacy. |
| [letter_C.wav](../services/assistant_controller/scenarios/vi/female/letter_C.wav) | Clip hướng dẫn tiếng Việt `letter_C`; giọng female. Một số tên là bước legacy. |
| [letter_D.wav](../services/assistant_controller/scenarios/vi/female/letter_D.wav) | Clip hướng dẫn tiếng Việt `letter_D`; giọng female. Một số tên là bước legacy. |
| [letter_H.wav](../services/assistant_controller/scenarios/vi/female/letter_H.wav) | Clip hướng dẫn tiếng Việt `letter_H`; giọng female. Một số tên là bước legacy. |
| [letter_K.wav](../services/assistant_controller/scenarios/vi/female/letter_K.wav) | Clip hướng dẫn tiếng Việt `letter_K`; giọng female. Một số tên là bước legacy. |
| [letter_N.wav](../services/assistant_controller/scenarios/vi/female/letter_N.wav) | Clip hướng dẫn tiếng Việt `letter_N`; giọng female. Một số tên là bước legacy. |
| [letter_O.wav](../services/assistant_controller/scenarios/vi/female/letter_O.wav) | Clip hướng dẫn tiếng Việt `letter_O`; giọng female. Một số tên là bước legacy. |
| [letter_R.wav](../services/assistant_controller/scenarios/vi/female/letter_R.wav) | Clip hướng dẫn tiếng Việt `letter_R`; giọng female. Một số tên là bước legacy. |
| [letter_S.wav](../services/assistant_controller/scenarios/vi/female/letter_S.wav) | Clip hướng dẫn tiếng Việt `letter_S`; giọng female. Một số tên là bước legacy. |
| [letter_V.wav](../services/assistant_controller/scenarios/vi/female/letter_V.wav) | Clip hướng dẫn tiếng Việt `letter_V`; giọng female. Một số tên là bước legacy. |
| [letter_Z.wav](../services/assistant_controller/scenarios/vi/female/letter_Z.wav) | Clip hướng dẫn tiếng Việt `letter_Z`; giọng female. Một số tên là bước legacy. |
| [letter_confirm_ask.wav](../services/assistant_controller/scenarios/vi/female/letter_confirm_ask.wav) | Clip hướng dẫn tiếng Việt `letter_confirm_ask`; giọng female. Một số tên là bước legacy. |
| [metadata.csv](../services/assistant_controller/scenarios/vi/female/metadata.csv) | Metadata nội dung/audio của bộ prompt trong folder; hỗ trợ tra cứu/chỉnh giọng, không chứa logic đo. |
| [metadata.json](../services/assistant_controller/scenarios/vi/female/metadata.json) | Metadata nội dung/audio của bộ prompt trong folder; hỗ trợ tra cứu/chỉnh giọng, không chứa logic đo. |
| [next_letter.wav](../services/assistant_controller/scenarios/vi/female/next_letter.wav) | Clip hướng dẫn tiếng Việt `next_letter`; giọng female. Một số tên là bước legacy. |
| [open_both_eyes.wav](../services/assistant_controller/scenarios/vi/female/open_both_eyes.wav) | Clip hướng dẫn tiếng Việt `open_both_eyes`; giọng female. Một số tên là bước legacy. |
| [position_stable.wav](../services/assistant_controller/scenarios/vi/female/position_stable.wav) | Clip hướng dẫn tiếng Việt `position_stable`; giọng female. Một số tên là bước legacy. |
| [queue_announce.wav](../services/assistant_controller/scenarios/vi/female/queue_announce.wav) | Clip hướng dẫn tiếng Việt `queue_announce`; giọng female. Một số tên là bước legacy. |
| [read_letter_again.wav](../services/assistant_controller/scenarios/vi/female/read_letter_again.wav) | Clip hướng dẫn tiếng Việt `read_letter_again`; giọng female. Một số tên là bước legacy. |
| [return_waiting.wav](../services/assistant_controller/scenarios/vi/female/return_waiting.wav) | Clip hướng dẫn tiếng Việt `return_waiting`; giọng female. Một số tên là bước legacy. |
| [right_eye_complete.wav](../services/assistant_controller/scenarios/vi/female/right_eye_complete.wav) | Clip hướng dẫn tiếng Việt `right_eye_complete`; giọng female. Một số tên là bước legacy. |
| [start_both_eyes.wav](../services/assistant_controller/scenarios/vi/female/start_both_eyes.wav) | Clip hướng dẫn tiếng Việt `start_both_eyes`; giọng female. Một số tên là bước legacy. |
| [start_left_eye.wav](../services/assistant_controller/scenarios/vi/female/start_left_eye.wav) | Clip hướng dẫn tiếng Việt `start_left_eye`; giọng female. Một số tên là bước legacy. |
| [start_right_eye.wav](../services/assistant_controller/scenarios/vi/female/start_right_eye.wav) | Clip hướng dẫn tiếng Việt `start_right_eye`; giọng female. Một số tên là bước legacy. |
| [switch_eye.wav](../services/assistant_controller/scenarios/vi/female/switch_eye.wav) | Clip hướng dẫn tiếng Việt `switch_eye`; giọng female. Một số tên là bước legacy. |
| [test_complete.wav](../services/assistant_controller/scenarios/vi/female/test_complete.wav) | Clip hướng dẫn tiếng Việt `test_complete`; giọng female. Một số tên là bước legacy. |
| [welcome_ready.wav](../services/assistant_controller/scenarios/vi/female/welcome_ready.wav) | Clip hướng dẫn tiếng Việt `welcome_ready`; giọng female. Một số tên là bước legacy. |

</details>

<details>
<summary>services/assistant_controller/scenarios/vi/male — 37 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [b10_confirm.wav](../services/assistant_controller/scenarios/vi/male/b10_confirm.wav) | Clip hướng dẫn tiếng Việt `b10_confirm`; giọng male. Một số tên là bước legacy. |
| [b3_stand.wav](../services/assistant_controller/scenarios/vi/male/b3_stand.wav) | Clip hướng dẫn tiếng Việt `b3_stand`; giọng male. Một số tên là bước legacy. |
| [b4_cover_left.wav](../services/assistant_controller/scenarios/vi/male/b4_cover_left.wav) | Clip hướng dẫn tiếng Việt `b4_cover_left`; giọng male. Một số tên là bước legacy. |
| [b4_cover_right.wav](../services/assistant_controller/scenarios/vi/male/b4_cover_right.wav) | Clip hướng dẫn tiếng Việt `b4_cover_right`; giọng male. Một số tên là bước legacy. |
| [b5_look_chart.wav](../services/assistant_controller/scenarios/vi/male/b5_look_chart.wav) | Clip hướng dẫn tiếng Việt `b5_look_chart`; giọng male. Một số tên là bước legacy. |
| [b6_read_row.wav](../services/assistant_controller/scenarios/vi/male/b6_read_row.wav) | Clip hướng dẫn tiếng Việt `b6_read_row`; giọng male. Một số tên là bước legacy. |
| [cover_left_eye.wav](../services/assistant_controller/scenarios/vi/male/cover_left_eye.wav) | Clip hướng dẫn tiếng Việt `cover_left_eye`; giọng male. Một số tên là bước legacy. |
| [cover_right_eye.wav](../services/assistant_controller/scenarios/vi/male/cover_right_eye.wav) | Clip hướng dẫn tiếng Việt `cover_right_eye`; giọng male. Một số tên là bước legacy. |
| [error_retry.wav](../services/assistant_controller/scenarios/vi/male/error_retry.wav) | Clip hướng dẫn tiếng Việt `error_retry`; giọng male. Một số tên là bước legacy. |
| [explain_rules.wav](../services/assistant_controller/scenarios/vi/male/explain_rules.wav) | Clip hướng dẫn tiếng Việt `explain_rules`; giọng male. Một số tên là bước legacy. |
| [left_eye_complete.wav](../services/assistant_controller/scenarios/vi/male/left_eye_complete.wav) | Clip hướng dẫn tiếng Việt `left_eye_complete`; giọng male. Một số tên là bước legacy. |
| [letter_C.wav](../services/assistant_controller/scenarios/vi/male/letter_C.wav) | Clip hướng dẫn tiếng Việt `letter_C`; giọng male. Một số tên là bước legacy. |
| [letter_D.wav](../services/assistant_controller/scenarios/vi/male/letter_D.wav) | Clip hướng dẫn tiếng Việt `letter_D`; giọng male. Một số tên là bước legacy. |
| [letter_H.wav](../services/assistant_controller/scenarios/vi/male/letter_H.wav) | Clip hướng dẫn tiếng Việt `letter_H`; giọng male. Một số tên là bước legacy. |
| [letter_K.wav](../services/assistant_controller/scenarios/vi/male/letter_K.wav) | Clip hướng dẫn tiếng Việt `letter_K`; giọng male. Một số tên là bước legacy. |
| [letter_N.wav](../services/assistant_controller/scenarios/vi/male/letter_N.wav) | Clip hướng dẫn tiếng Việt `letter_N`; giọng male. Một số tên là bước legacy. |
| [letter_O.wav](../services/assistant_controller/scenarios/vi/male/letter_O.wav) | Clip hướng dẫn tiếng Việt `letter_O`; giọng male. Một số tên là bước legacy. |
| [letter_R.wav](../services/assistant_controller/scenarios/vi/male/letter_R.wav) | Clip hướng dẫn tiếng Việt `letter_R`; giọng male. Một số tên là bước legacy. |
| [letter_S.wav](../services/assistant_controller/scenarios/vi/male/letter_S.wav) | Clip hướng dẫn tiếng Việt `letter_S`; giọng male. Một số tên là bước legacy. |
| [letter_V.wav](../services/assistant_controller/scenarios/vi/male/letter_V.wav) | Clip hướng dẫn tiếng Việt `letter_V`; giọng male. Một số tên là bước legacy. |
| [letter_Z.wav](../services/assistant_controller/scenarios/vi/male/letter_Z.wav) | Clip hướng dẫn tiếng Việt `letter_Z`; giọng male. Một số tên là bước legacy. |
| [letter_confirm_ask.wav](../services/assistant_controller/scenarios/vi/male/letter_confirm_ask.wav) | Clip hướng dẫn tiếng Việt `letter_confirm_ask`; giọng male. Một số tên là bước legacy. |
| [metadata.csv](../services/assistant_controller/scenarios/vi/male/metadata.csv) | Metadata nội dung/audio của bộ prompt trong folder; hỗ trợ tra cứu/chỉnh giọng, không chứa logic đo. |
| [metadata.json](../services/assistant_controller/scenarios/vi/male/metadata.json) | Metadata nội dung/audio của bộ prompt trong folder; hỗ trợ tra cứu/chỉnh giọng, không chứa logic đo. |
| [next_letter.wav](../services/assistant_controller/scenarios/vi/male/next_letter.wav) | Clip hướng dẫn tiếng Việt `next_letter`; giọng male. Một số tên là bước legacy. |
| [open_both_eyes.wav](../services/assistant_controller/scenarios/vi/male/open_both_eyes.wav) | Clip hướng dẫn tiếng Việt `open_both_eyes`; giọng male. Một số tên là bước legacy. |
| [position_stable.wav](../services/assistant_controller/scenarios/vi/male/position_stable.wav) | Clip hướng dẫn tiếng Việt `position_stable`; giọng male. Một số tên là bước legacy. |
| [queue_announce.wav](../services/assistant_controller/scenarios/vi/male/queue_announce.wav) | Clip hướng dẫn tiếng Việt `queue_announce`; giọng male. Một số tên là bước legacy. |
| [read_letter_again.wav](../services/assistant_controller/scenarios/vi/male/read_letter_again.wav) | Clip hướng dẫn tiếng Việt `read_letter_again`; giọng male. Một số tên là bước legacy. |
| [return_waiting.wav](../services/assistant_controller/scenarios/vi/male/return_waiting.wav) | Clip hướng dẫn tiếng Việt `return_waiting`; giọng male. Một số tên là bước legacy. |
| [right_eye_complete.wav](../services/assistant_controller/scenarios/vi/male/right_eye_complete.wav) | Clip hướng dẫn tiếng Việt `right_eye_complete`; giọng male. Một số tên là bước legacy. |
| [start_both_eyes.wav](../services/assistant_controller/scenarios/vi/male/start_both_eyes.wav) | Clip hướng dẫn tiếng Việt `start_both_eyes`; giọng male. Một số tên là bước legacy. |
| [start_left_eye.wav](../services/assistant_controller/scenarios/vi/male/start_left_eye.wav) | Clip hướng dẫn tiếng Việt `start_left_eye`; giọng male. Một số tên là bước legacy. |
| [start_right_eye.wav](../services/assistant_controller/scenarios/vi/male/start_right_eye.wav) | Clip hướng dẫn tiếng Việt `start_right_eye`; giọng male. Một số tên là bước legacy. |
| [switch_eye.wav](../services/assistant_controller/scenarios/vi/male/switch_eye.wav) | Clip hướng dẫn tiếng Việt `switch_eye`; giọng male. Một số tên là bước legacy. |
| [test_complete.wav](../services/assistant_controller/scenarios/vi/male/test_complete.wav) | Clip hướng dẫn tiếng Việt `test_complete`; giọng male. Một số tên là bước legacy. |
| [welcome_ready.wav](../services/assistant_controller/scenarios/vi/male/welcome_ready.wav) | Clip hướng dẫn tiếng Việt `welcome_ready`; giọng male. Một số tên là bước legacy. |

</details>

<details>
<summary>services/assistant_controller/scripts — 5 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [demo_face_wait.py](../services/assistant_controller/scripts/demo_face_wait.py) | CLI chờ một event nhận diện panel để smoke/debug. |
| [demo_start_session.py](../services/assistant_controller/scripts/demo_start_session.py) | Publish MQTT start thử nghiệm; có thể kích hoạt phiên thật nếu dùng broker/station thật. |
| [push_device_faces_to_vdb.py](../services/assistant_controller/scripts/push_device_faces_to_vdb.py) | CLI xuất khuôn mặt panel lên gallery và Media; chiều ngược sync thường ngày. |
| [results_sink.py](../services/assistant_controller/scripts/results_sink.py) | HTTP sink local nhận/list callback khi test; không phải Frappe production. |
| [sync_faces_to_device.py](../services/assistant_controller/scripts/sync_faces_to_device.py) | CLI kéo gallery VectorDB xuống panel; ghi/xóa theo tùy chọn sync. |

</details>

<details>
<summary>services/assistant_controller/src/ac — 27 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/assistant_controller/src/ac/__init__.py) | Khởi tạo package AC và metadata package. |
| [age_va.py](../services/assistant_controller/src/ac/age_va.py) | Parse DOB, tuổi→mức khởi đầu, BinarySearchState và SmartRangeSearchState. |
| [audio_device.py](../services/assistant_controller/src/ac/audio_device.py) | Resolve thiết bị sounddevice theo index/tên và phân loại input/output. |
| [audio_player.py](../services/assistant_controller/src/ac/audio_player.py) | Nạp manifest, chọn giọng/câu WAV, phát qua sounddevice/browser và fallback prompts. |
| [cccd_qr.py](../services/assistant_controller/src/ac/cccd_qr.py) | Lấy JPEG panel, upload Media và nhờ Frappe áp dụng kết quả QR CCCD. |
| [config.py](../services/assistant_controller/src/ac/config.py) | Pydantic config/default/validation và mapping env; ROOT cố định thư mục service AC. |
| [display_client.py](../services/assistant_controller/src/ac/display_client.py) | FastAPI HTTP/WS chart/tablet/preview/settings/face; DisplayHub queue và client gửi lệnh hiển thị. |
| [dmn_engine.py](../services/assistant_controller/src/ac/dmn_engine.py) | Parse/evaluate tập con DMN XML/FEEL và trả ActionName; không là DMN engine tổng quát. |
| [face_client.py](../services/assistant_controller/src/ac/face_client.py) | Protocol AiFace HTTP, enroll/export/gallery, server callback, log/events và chờ nhận diện. |
| [face_gallery_loop.py](../services/assistant_controller/src/ac/face_gallery_loop.py) | Thread pull lịch hôm nay theo signature, audit, wipe ban đêm theo giờ máy trạm. |
| [face_sync.py](../services/assistant_controller/src/ac/face_sync.py) | Đồng bộ gallery tổng/hôm nay, template/JPEG, prune/wipe panel và kết quả sync. |
| [hospital_client.py](../services/assistant_controller/src/ac/hospital_client.py) | HTTP Frappe/legacy adapters, lookup/register/measurement/gallery/check-in/CCCD và auth token tùy config. |
| [http_callback.py](../services/assistant_controller/src/ac/http_callback.py) | POST kết quả, correlation header, retry lỗi chọn lọc; chưa có durable outbox/auth callback. |
| [letter_clip.py](../services/assistant_controller/src/ac/letter_clip.py) | Ghi WAV từng lượt chữ từ shared mic hoặc parec/sounddevice; docstring còn nhắc xác nhận cũ. |
| [main.py](../services/assistant_controller/src/ac/main.py) | Wiring toàn trạm: load config, dựng clients/bridges, display server, MQTT, gallery/walk-in loops, shutdown. |
| [media_client.py](../services/assistant_controller/src/ac/media_client.py) | Client grant/upload/download Media, object metadata và token header. |
| [microphone_stream.py](../services/assistant_controller/src/ac/microphone_stream.py) | Stream microphone dùng chung, cursor và buffer samples để STT/clip dùng cùng timeline. |
| [models.py](../services/assistant_controller/src/ac/models.py) | Runtime contract session/start/cancel/status/results, enum action/state và dữ liệu điểm mắt. |
| [mqtt_gateway.py](../services/assistant_controller/src/ac/mqtt_gateway.py) | MQTT async reconnect/backoff, subscribe start/cancel, validate Pydantic, publish status theo station ID. |
| [orchestrator.py](../services/assistant_controller/src/ac/orchestrator.py) | State machine phiên đo, face gate, input, readiness, search, phát hướng dẫn, chấm, journal/callback. |
| [readiness_bridge.py](../services/assistant_controller/src/ac/readiness_bridge.py) | Adapter SmartEyes, frame reader, mock/UI/Sloan STT, chọn input, VAD và chọn ký tự. |
| [scoring.py](../services/assistant_controller/src/ac/scoring.py) | Chuyển logMAR/decimal/Snellen/x/10, chọn mức đạt; loại range khỏi điểm chính thức. |
| [session_manager.py](../services/assistant_controller/src/ac/session_manager.py) | Một phiên active/trạm với lock, dữ liệu trial/session và append JSONL. |
| [stt_bridge.py](../services/assistant_controller/src/ac/stt_bridge.py) | Re-export các class/hàm STT từ readiness_bridge; shim cấu trúc API. |
| [stt_process.py](../services/assistant_controller/src/ac/stt_process.py) | Implementation STT worker multiprocessing, hiện chưa nối vào đường khởi tạo chính. |
| [vector_face_client.py](../services/assistant_controller/src/ac/vector_face_client.py) | Client gallery HTTP/mock/off; chuẩn hóa record, ảnh và template. |
| [walk_in.py](../services/assistant_controller/src/ac/walk_in.py) | Khi idle chờ event face mới, lookup hồ sơ, tạo SessionStart và chống dùng lại event trong RAM. |

</details>

<details>
<summary>services/assistant_controller/tests — 21 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [test_age_va.py](../services/assistant_controller/tests/test_age_va.py) | Test DOB/tuổi và seed mức đo; 3 hàm test trong file. |
| [test_audio_player.py](../services/assistant_controller/tests/test_audio_player.py) | Test chọn/phát prompt và giọng; 8 hàm test trong file. |
| [test_contracts.py](../services/assistant_controller/tests/test_contracts.py) | Test runtime payload so với JSON Schema; 4 hàm test trong file. |
| [test_demo_integration.py](../services/assistant_controller/tests/test_demo_integration.py) | Test flow demo với fake dependency; 3 hàm test trong file. |
| [test_display_calibration.py](../services/assistant_controller/tests/test_display_calibration.py) | Test kích thước/hiệu chuẩn màn hình; 3 hàm test trong file. |
| [test_dmn.py](../services/assistant_controller/tests/test_dmn.py) | Test quyết định action theo facts; 6 hàm test trong file. |
| [test_face_client.py](../services/assistant_controller/tests/test_face_client.py) | Test protocol và nhận diện AiFace; 10 hàm test trong file. |
| [test_face_sync.py](../services/assistant_controller/tests/test_face_sync.py) | Test gallery sync/prune/wipe; 9 hàm test trong file. |
| [test_frame_grabber.py](../services/assistant_controller/tests/test_frame_grabber.py) | Test frame mới nhất và capture thread; 2 hàm test trong file. |
| [test_frappe_face_booking.py](../services/assistant_controller/tests/test_frappe_face_booking.py) | Test tích hợp gallery/lịch Frappe ở mức mock; 2 hàm test trong file. |
| [test_http_callback.py](../services/assistant_controller/tests/test_http_callback.py) | Test callback và điều kiện retry; 4 hàm test trong file. |
| [test_input_modes.py](../services/assistant_controller/tests/test_input_modes.py) | Test speak/tablet, cửa sổ trả lời; 6 hàm test trong file. |
| [test_letter_history.py](../services/assistant_controller/tests/test_letter_history.py) | Test chọn/thay chữ tránh lặp gần; 5 hàm test trong file. |
| [test_microphone_stream.py](../services/assistant_controller/tests/test_microphone_stream.py) | Test timeline/buffer microphone chung; 10 hàm test trong file. |
| [test_mqtt_gateway.py](../services/assistant_controller/tests/test_mqtt_gateway.py) | Test topic và validate message; 1 hàm test trong file. |
| [test_network_settings.py](../services/assistant_controller/tests/test_network_settings.py) | Test lưu/hot-update YAML/env kết nối; 12 hàm test trong file. |
| [test_orchestrator.py](../services/assistant_controller/tests/test_orchestrator.py) | Test state machine và hành vi đo; 3 hàm test trong file. |
| [test_scoring.py](../services/assistant_controller/tests/test_scoring.py) | Test logMAR/x/10, pass/fail và loại range; 6 hàm test trong file. |
| [test_session_cancel.py](../services/assistant_controller/tests/test_session_cancel.py) | Test hủy đúng session và dừng tác vụ; 1 hàm test trong file. |
| [test_smart_range_strategy.py](../services/assistant_controller/tests/test_smart_range_strategy.py) | Test 2+1 range và 3/5 verify/fallback; 14 hàm test trong file. |
| [test_walk_in.py](../services/assistant_controller/tests/test_walk_in.py) | Test event face→session và chống lặp; 2 hàm test trong file. |

</details>

<details>
<summary>services/face_vectordb — 4 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [Dockerfile](../services/face_vectordb/Dockerfile) | Image gallery API cổng 8100. |
| [README.md](../services/face_vectordb/README.md) | Tài liệu endpoint/gallery prototype. |
| [app.py](../services/face_vectordb/app.py) | Gallery FastAPI + SQLite + images; list/get/upsert/delete theo enroll ID, không similarity search. |
| [requirements.txt](../services/face_vectordb/requirements.txt) | Dependency API gallery. |

</details>

<details>
<summary>services/hospital/hospital_api — 7 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [Dockerfile](../services/hospital/hospital_api/Dockerfile) | Image hospital FastAPI legacy trên VPS. |
| [Dockerfile.aiface_bs](../services/hospital/hospital_api/Dockerfile.aiface_bs) | Image riêng BS bridge trong Compose Jetson phụ. |
| [README.md](../services/hospital/hospital_api/README.md) | Hướng dẫn bệnh viện giả lập và tích hợp lab lịch sử. |
| [aiface_bs.py](../services/hospital/hospital_api/aiface_bs.py) | Bridge panel WebSocket 7788→HTTP events 7790 chạy trên Jetson, vẫn thuộc runtime chính. |
| [main.py](../services/hospital/hospital_api/main.py) | Bệnh viện giả lập FastAPI/SQLite, aliases tương thích Frappe; profile legacy, không triển khai nghiệp vụ đầy đủ. |
| [requirements.txt](../services/hospital/hospital_api/requirements.txt) | Dependency của bệnh viện giả lập. |
| [run.sh](../services/hospital/hospital_api/run.sh) | Tạo venv/chạy hospital API standalone trên máy lab. |

</details>

<details>
<summary>services/hospital/smart-hospital — 10 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [.editorconfig](../services/hospital/smart-hospital/.editorconfig) | Quy ước whitespace/encoding cho editor. |
| [.eslintrc](../services/hospital/smart-hospital/.eslintrc) | Quy tắc lint JavaScript. |
| [.gitignore](../services/hospital/smart-hospital/.gitignore) | Quy tắc bỏ qua cache, môi trường và artifact local của service; không bỏ file đã tracked. |
| [.pre-commit-config.yaml](../services/hospital/smart-hospital/.pre-commit-config.yaml) | Hook lint/format khi phát triển app. |
| [README.md](../services/hospital/smart-hospital/README.md) | README template app Frappe, không tài liệu đầy đủ hệ thống. |
| [build.json](../services/hospital/smart-hospital/build.json) | Cấu hình build assets app. |
| [license.txt](../services/hospital/smart-hospital/license.txt) | Giấy phép mã nguồn app. |
| [package-lock.json](../services/hospital/smart-hospital/package-lock.json) | Lock dependency npm của app. |
| [package.json](../services/hospital/smart-hospital/package.json) | Metadata/dependency/tool JS của app. |
| [pyproject.toml](../services/hospital/smart-hospital/pyproject.toml) | Metadata Python package và cấu hình tool/build Frappe. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital — 4 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/__init__.py) | Khởi tạo/đánh dấu Python package smart_hospital; chứa metadata hoặc logic khởi tạo package, giữ import path của framework. |
| [hooks.py](../services/hospital/smart-hospital/smart_hospital/hooks.py) | Khai báo JS toàn app, overrides Patient/Sales Order/delete, role home, migrate hooks và cron wipe. |
| [modules.txt](../services/hospital/smart-hospital/smart_hospital/modules.txt) | Đăng ký module Smart Hospital với Frappe. |
| [patches.txt](../services/hospital/smart-hospital/smart_hospital/patches.txt) | Danh sách patch migration có thứ tự của app. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/api — 14 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/api/__init__.py) | Khởi tạo/đánh dấu Python package api; không có logic trong file hiện tại. |
| [clinic_constants.py](../services/hospital/smart-hospital/smart_hospital/api/clinic_constants.py) | Hằng role/nhóm người dùng clinic dùng chung. |
| [clinic_desk.py](../services/hospital/smart-hospital/smart_hospital/api/clinic_desk.py) | Lịch hẹn, check-in/out, queue, review/đơn kính, CCCD và gallery/push/wipe; có hai remove_appointment. |
| [clinic_roles.py](../services/hospital/smart-hospital/smart_hospital/api/clinic_roles.py) | Tạo/cập nhật role permission và cấu hình Desk cho nhóm clinic. |
| [clinic_shell.py](../services/hospital/smart-hospital/smart_hospital/api/clinic_shell.py) | Boot session/home/route theo role và cấu hình shell clinic. |
| [clinic_workspaces.py](../services/hospital/smart-hospital/smart_hospital/api/clinic_workspaces.py) | Tạo/sửa workspace, shortcut/navigation và dọn bố cục Desk clinic. |
| [createpatient.py](../services/hospital/smart-hospital/smart_hospital/api/createpatient.py) | API tạo Patient từ dữ liệu quầy/form và các liên kết nghiệp vụ. |
| [face_identity.py](../services/hospital/smart-hospital/smart_hospital/api/face_identity.py) | Custom fields Patient, sinh/map enroll ID, lookup/register avatar, voice setting, upload Media/gallery. |
| [face_service_api.py](../services/hospital/smart-hospital/smart_hospital/api/face_service_api.py) | Adapter upload video face register/verify tới GDU, chuyển WebM→MP4 bằng ffmpeg. |
| [patient.py](../services/hospital/smart-hospital/smart_hospital/api/patient.py) | API Patient bổ sung cho app/luồng quầy, giữ để các page/caller Frappe sử dụng. |
| [patient_wipe.py](../services/hospital/smart-hospital/smart_hospital/api/patient_wipe.py) | Preview/purge bệnh nhân và tài nguyên liên quan trong DB, Media, gallery/panel; có kiểm quyền wipe. |
| [receive_visual_acuity.py](../services/hospital/smart-hospital/smart_hospital/api/receive_visual_acuity.py) | Adapter tương thích callback cũ; có JSON acuity thì chuyển vision.receive_results. |
| [send_vision_measurement.py](../services/hospital/smart-hospital/smart_hospital/api/send_vision_measurement.py) | Publish MQTT start/cancel từ Frappe; HTTP fallback chỉ khi explicit station_http. |
| [vision.py](../services/hospital/smart-hospital/smart_hospital/api/vision.py) | Tạo Vision Measurement, callback kết quả, idempotent lookup session, child letter rows và checkout. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/config — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/config/__init__.py) | Khởi tạo/đánh dấu Python package config; không có logic trong file hiện tại. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/overrides — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/overrides/__init__.py) | Khởi tạo/đánh dấu Python package overrides; không có logic trong file hiện tại. |
| [patient.py](../services/hospital/smart-hospital/smart_hospital/overrides/patient.py) | Subclass Patient, enroll ID và cleanup liên kết khi xóa; override frappe.client.delete. |
| [sales_oder.py](../services/hospital/smart-hospital/smart_hospital/overrides/sales_oder.py) | Subclass Sales Order được hooks.py tham chiếu; tên file sai chính tả nhưng là đường import thật. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/patches — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/patches/__init__.py) | Khởi tạo/đánh dấu Python package patches; không có logic trong file hiện tại. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/patches/v1_0 — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/patches/v1_0/__init__.py) | Khởi tạo/đánh dấu Python package v1_0; không có logic trong file hiện tại. |
| [clinic_desk_cleanup.py](../services/hospital/smart-hospital/smart_hospital/patches/v1_0/clinic_desk_cleanup.py) | Migration cleanup bố cục/Desk clinic. |
| [set_clinic_desk_roles.py](../services/hospital/smart-hospital/smart_hospital/patches/v1_0/set_clinic_desk_roles.py) | Migration thiết lập role/quyền clinic. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/public — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [.gitkeep](../services/hospital/smart-hospital/smart_hospital/public/.gitkeep) | Giữ folder public trong Git khi cần; không mã runtime. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/public/js — 6 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [cccd_scanner.js](../services/hospital/smart-hospital/smart_hospital/public/js/cccd_scanner.js) | Luồng QR CCCD trên browser, camera/parse và trả dữ liệu quầy. |
| [clinic_shell.js](../services/hospital/smart-hospital/smart_hospital/public/js/clinic_shell.js) | Điều hướng/shell browser theo role và boot data từ backend. |
| [face_enroll.js](../services/hospital/smart-hospital/smart_hospital/public/js/face_enroll.js) | UI capture/avatar/video mặt, hướng dẫn pose và upload vào API Frappe. |
| [face_landmarker.js](../services/hospital/smart-hospital/smart_hospital/public/js/face_landmarker.js) | Nạp MediaPipe browser và cung cấp landmarks/pose để hướng dẫn chụp mặt; khác CV Jetson. |
| [patient_cccd.js](../services/hospital/smart-hospital/smart_hospital/public/js/patient_cccd.js) | Tích hợp trường CCCD/scan và thao tác Patient form. |
| [patient_list.js](../services/hospital/smart-hospital/smart_hospital/public/js/patient_list.js) | Tùy biến Patient list, thao tác clinic và xóa theo backend override. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [vision_bundle.js](../services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe/vision_bundle.js) | Asset vendor MediaPipe browser: loader/bundle JavaScript vision_bundle. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_bundle.mjs](../services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe/vision_bundle.mjs) | Asset vendor MediaPipe browser: loader/bundle JavaScript vision_bundle. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_bundle.mjs.map](../services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe/vision_bundle.mjs.map) | Asset vendor MediaPipe browser: source map debug bundle. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe/wasm — 6 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [vision_wasm_internal.js](../services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe/wasm/vision_wasm_internal.js) | Asset vendor MediaPipe browser: loader/bundle JavaScript vision_wasm_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_wasm_internal.wasm](../services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe/wasm/vision_wasm_internal.wasm) | Asset vendor MediaPipe browser: WebAssembly engine vision_wasm_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_wasm_module_internal.js](../services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe/wasm/vision_wasm_module_internal.js) | Asset vendor MediaPipe browser: loader/bundle JavaScript vision_wasm_module_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_wasm_module_internal.wasm](../services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe/wasm/vision_wasm_module_internal.wasm) | Asset vendor MediaPipe browser: WebAssembly engine vision_wasm_module_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_wasm_nosimd_internal.js](../services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe/wasm/vision_wasm_nosimd_internal.js) | Asset vendor MediaPipe browser: loader/bundle JavaScript vision_wasm_nosimd_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_wasm_nosimd_internal.wasm](../services/hospital/smart-hospital/smart_hospital/public/js/lib/mediapipe/wasm/vision_wasm_nosimd_internal.wasm) | Asset vendor MediaPipe browser: WebAssembly engine vision_wasm_nosimd_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/public/js/wasm — 6 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [vision_wasm_internal.js](../services/hospital/smart-hospital/smart_hospital/public/js/wasm/vision_wasm_internal.js) | Asset vendor MediaPipe browser: loader/bundle JavaScript vision_wasm_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_wasm_internal.wasm](../services/hospital/smart-hospital/smart_hospital/public/js/wasm/vision_wasm_internal.wasm) | Asset vendor MediaPipe browser: WebAssembly engine vision_wasm_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_wasm_module_internal.js](../services/hospital/smart-hospital/smart_hospital/public/js/wasm/vision_wasm_module_internal.js) | Asset vendor MediaPipe browser: loader/bundle JavaScript vision_wasm_module_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_wasm_module_internal.wasm](../services/hospital/smart-hospital/smart_hospital/public/js/wasm/vision_wasm_module_internal.wasm) | Asset vendor MediaPipe browser: WebAssembly engine vision_wasm_module_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_wasm_nosimd_internal.js](../services/hospital/smart-hospital/smart_hospital/public/js/wasm/vision_wasm_nosimd_internal.js) | Asset vendor MediaPipe browser: loader/bundle JavaScript vision_wasm_nosimd_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |
| [vision_wasm_nosimd_internal.wasm](../services/hospital/smart-hospital/smart_hospital/public/js/wasm/vision_wasm_nosimd_internal.wasm) | Asset vendor MediaPipe browser: WebAssembly engine vision_wasm_nosimd_internal. Không sửa logic app trực tiếp trong vendor; kiểm fileset URL trước dọn bản trùng. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/service — 2 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/service/__init__.py) | Khởi tạo/đánh dấu Python package service; không có logic trong file hiện tại. |
| [face_service.py](../services/hospital/smart-hospital/smart_hospital/service/face_service.py) | Client GDU token/register/status/verify, đọc Connection Settings→site config→env. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital — 2 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [.frappe](../services/hospital/smart-hospital/smart_hospital/smart_hospital/.frappe) | Marker framework cho module sinh bởi Frappe. |
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/__init__.py) | Khởi tạo/đánh dấu Python package smart_hospital; không có logic trong file hiện tại. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/dashboard_chart/number_of_patient — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [number_of_patient.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/dashboard_chart/number_of_patient/number_of_patient.json) | Metadata dashboard chart số lượng bệnh nhân, dữ liệu cấu hình Frappe. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/__init__.py) | Khởi tạo/đánh dấu Python package doctype; không có logic trong file hiện tại. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/connection_settings — 5 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/connection_settings/__init__.py) | Khởi tạo/đánh dấu Python package connection_settings; không có logic trong file hiện tại. |
| [connection_settings.js](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/connection_settings/connection_settings.js) | Cấu hình kết nối và credential GDU — client script form (có file scaffold). |
| [connection_settings.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/connection_settings/connection_settings.json) | Cấu hình kết nối và credential GDU — schema field/permission/layout cần migrate. |
| [connection_settings.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/connection_settings/connection_settings.py) | Cấu hình kết nối và credential GDU — Python DocType controller/validation (nhiều controller chỉ là scaffold). |
| [test_connection_settings.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/connection_settings/test_connection_settings.py) | Scaffold integration test Frappe cho Cấu hình kết nối và credential GDU; hiện chưa có hàm test cụ thể. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/eye_prescription — 5 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/eye_prescription/__init__.py) | Khởi tạo/đánh dấu Python package eye_prescription; không có logic trong file hiện tại. |
| [eye_prescription.js](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/eye_prescription/eye_prescription.js) | Đơn kính/đánh giá bác sĩ — client script form (có file scaffold). |
| [eye_prescription.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/eye_prescription/eye_prescription.json) | Đơn kính/đánh giá bác sĩ — schema field/permission/layout cần migrate. |
| [eye_prescription.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/eye_prescription/eye_prescription.py) | Đơn kính/đánh giá bác sĩ — Python DocType controller/validation (nhiều controller chỉ là scaffold). |
| [test_eye_prescription.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/eye_prescription/test_eye_prescription.py) | Scaffold integration test Frappe cho Đơn kính/đánh giá bác sĩ; hiện chưa có hàm test cụ thể. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/vision_measurement — 5 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/vision_measurement/__init__.py) | Khởi tạo/đánh dấu Python package vision_measurement; không có logic trong file hiện tại. |
| [test_vision_measurement.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/vision_measurement/test_vision_measurement.py) | Scaffold integration test Frappe cho Bản ghi lần đo liên kết Patient; hiện chưa có hàm test cụ thể. |
| [vision_measurement.js](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/vision_measurement/vision_measurement.js) | Bản ghi lần đo liên kết Patient — client script form (có file scaffold). |
| [vision_measurement.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/vision_measurement/vision_measurement.json) | Bản ghi lần đo liên kết Patient — schema field/permission/layout cần migrate. |
| [vision_measurement.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/vision_measurement/vision_measurement.py) | Bản ghi lần đo liên kết Patient — Python DocType controller/validation (nhiều controller chỉ là scaffold). |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/visual_acuity — 5 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/visual_acuity/__init__.py) | Khởi tạo/đánh dấu Python package visual_acuity; không có logic trong file hiện tại. |
| [test_visual_acuity.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/visual_acuity/test_visual_acuity.py) | Scaffold integration test Frappe cho Kết quả đo, unique session_id, điểm và raw payload; hiện chưa có hàm test cụ thể. |
| [visual_acuity.js](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/visual_acuity/visual_acuity.js) | Kết quả đo, unique session_id, điểm và raw payload — client script form (có file scaffold). |
| [visual_acuity.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/visual_acuity/visual_acuity.json) | Kết quả đo, unique session_id, điểm và raw payload — schema field/permission/layout cần migrate. |
| [visual_acuity.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/visual_acuity/visual_acuity.py) | Kết quả đo, unique session_id, điểm và raw payload — Python DocType controller/validation (nhiều controller chỉ là scaffold). |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/visual_acuity_letter — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/visual_acuity_letter/__init__.py) | Khởi tạo/đánh dấu Python package visual_acuity_letter; không có logic trong file hiện tại. |
| [visual_acuity_letter.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/visual_acuity_letter/visual_acuity_letter.json) | Child table từng chữ kỳ vọng/thực nhận/kết quả/voice URL — schema field/permission/layout cần migrate. |
| [visual_acuity_letter.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/doctype/visual_acuity_letter/visual_acuity_letter.py) | Child table từng chữ kỳ vọng/thực nhận/kết quả/voice URL — Python DocType controller/validation (nhiều controller chỉ là scaffold). |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/page — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/__init__.py) | Khởi tạo/đánh dấu Python package page; không có logic trong file hiện tại. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/page/doctor_review — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/doctor_review/__init__.py) | Khởi tạo/đánh dấu Python package doctor_review; chứa metadata hoặc logic khởi tạo package, giữ import path của framework. |
| [doctor_review.js](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/doctor_review/doctor_review.js) | Bác sĩ xem kết quả và lưu đơn kính — JavaScript giao diện và gọi API Frappe. |
| [doctor_review.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/doctor_review/doctor_review.json) | Bác sĩ xem kết quả và lưu đơn kính — metadata Page/route và role framework. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/page/face_service_test — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/face_service_test/__init__.py) | Khởi tạo/đánh dấu Python package face_service_test; không có logic trong file hiện tại. |
| [face_service_test.js](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/face_service_test/face_service_test.js) | Trang thử nghiệm GDU face service — JavaScript giao diện và gọi API Frappe. |
| [face_service_test.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/face_service_test/face_service_test.json) | Trang thử nghiệm GDU face service — metadata Page/route và role framework. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/page/nurse_station — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/nurse_station/__init__.py) | Khởi tạo/đánh dấu Python package nurse_station; chứa metadata hoặc logic khởi tạo package, giữ import path của framework. |
| [nurse_station.js](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/nurse_station/nurse_station.js) | Điều dưỡng xem lịch/arrival và start/cancel phiên — JavaScript giao diện và gọi API Frappe. |
| [nurse_station.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/nurse_station/nurse_station.json) | Điều dưỡng xem lịch/arrival và start/cancel phiên — metadata Page/route và role framework. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/page/patient_registration — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/patient_registration/__init__.py) | Khởi tạo/đánh dấu Python package patient_registration; không có logic trong file hiện tại. |
| [patient_registration.js](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/patient_registration/patient_registration.js) | Quầy tạo/cập nhật Patient, mặt và CCCD — JavaScript giao diện và gọi API Frappe. |
| [patient_registration.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/patient_registration/patient_registration.json) | Quầy tạo/cập nhật Patient, mặt và CCCD — metadata Page/route và role framework. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/page/patient_vision_booking — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/patient_vision_booking/__init__.py) | Khởi tạo/đánh dấu Python package patient_vision_booking; chứa metadata hoặc logic khởi tạo package, giữ import path của framework. |
| [patient_vision_booking.js](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/patient_vision_booking/patient_vision_booking.js) | Đặt lịch Patient Appointment thị lực — JavaScript giao diện và gọi API Frappe. |
| [patient_vision_booking.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/page/patient_vision_booking/patient_vision_booking.json) | Đặt lịch Patient Appointment thị lực — metadata Page/route và role framework. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/workspace/clinic_admin — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [clinic_admin.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/workspace/clinic_admin/clinic_admin.json) | Workspace Frappe `clinic_admin`: bố cục/link/role navigation, dữ liệu chuẩn sync bởi framework. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/workspace/doctor — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [doctor.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/workspace/doctor/doctor.json) | Workspace Frappe `doctor`: bố cục/link/role navigation, dữ liệu chuẩn sync bởi framework. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/workspace/nurse — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [nurse.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/workspace/nurse/nurse.json) | Workspace Frappe `nurse`: bố cục/link/role navigation, dữ liệu chuẩn sync bởi framework. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/smart_hospital/workspace/smart_hospital — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [smart_hospital.json](../services/hospital/smart-hospital/smart_hospital/smart_hospital/workspace/smart_hospital/smart_hospital.json) | Workspace Frappe `smart_hospital`: bố cục/link/role navigation, dữ liệu chuẩn sync bởi framework. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/templates — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/templates/__init__.py) | Khởi tạo/đánh dấu Python package templates; không có logic trong file hiện tại. |

</details>

<details>
<summary>services/hospital/smart-hospital/smart_hospital/templates/pages — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/hospital/smart-hospital/smart_hospital/templates/pages/__init__.py) | Khởi tạo/đánh dấu Python package pages; không có logic trong file hiện tại. |

</details>

<details>
<summary>services/hospital/tests — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [test_acuity_score.py](../services/hospital/tests/test_acuity_score.py) | Test adapter kết quả fail và letter rows bệnh viện; 1 hàm test trong file. |

</details>

<details>
<summary>services/media_server — 7 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [.gitignore](../services/media_server/.gitignore) | Quy tắc bỏ qua cache, môi trường và artifact local của service; không bỏ file đã tracked. |
| [Dockerfile](../services/media_server/Dockerfile) | Image FastAPI Media Gateway cổng 9010. |
| [README.md](../services/media_server/README.md) | Tài liệu media service lịch sử; docstring còn nhắc Mac dù core Compose chạy VPS. |
| [docker-compose.yml](../services/media_server/docker-compose.yml) | Compose prototype Garage S3 riêng; không mở Media Gateway và không được core VPS Compose ghép vào. |
| [garage.toml](../services/media_server/garage.toml) | Prototype cấu hình Garage/S3; DiskStore hiện tại không gọi Garage. |
| [requirements.txt](../services/media_server/requirements.txt) | Dependency Media FastAPI/MQTT/settings. |
| [run.sh](../services/media_server/run.sh) | Runner standalone lab, không cần khi dùng core Docker VPS. |

</details>

<details>
<summary>services/media_server/app — 5 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/media_server/app/__init__.py) | Khởi tạo/đánh dấu Python package app; chứa metadata hoặc logic khởi tạo package, giữ import path của framework. |
| [config.py](../services/media_server/app/config.py) | Settings môi trường Media: root/public base/token/MQTT/stations/TTL. |
| [main.py](../services/media_server/app/main.py) | HTTP grants/object put/get/ready/delete/purge, token check và publish metadata. |
| [mqtt_bus.py](../services/media_server/app/mqtt_bus.py) | Subscribe qlbn/media/{station}/object/request, publish grant/ready; lỗi broker không chặn HTTP store. |
| [store.py](../services/media_server/app/store.py) | File store dưới MEDIA_ROOT, safe key, .meta content-type/size, delete object/session. |

</details>

<details>
<summary>services/qr_decode — 2 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [Dockerfile](../services/qr_decode/Dockerfile) | Image QR API cổng 9020, dependency hệ thống giải mã ảnh. |
| [requirements.txt](../services/qr_decode/requirements.txt) | Dependency FastAPI/PIL/pyzbar/httpx cho QR service. |

</details>

<details>
<summary>services/qr_decode/app — 2 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/qr_decode/app/__init__.py) | Khởi tạo/đánh dấu Python package app; chứa metadata hoặc logic khởi tạo package, giữ import path của framework. |
| [main.py](../services/qr_decode/app/main.py) | FastAPI upload/decode_url, pyzbar decode/resize và parse CCCD phân tách bằng dấu pipe. |

</details>

<details>
<summary>services/sloan_stt — 12 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [.gitignore](../services/sloan_stt/.gitignore) | Quy tắc bỏ qua cache, môi trường và artifact local của service; không bỏ file đã tracked. |
| [README.md](../services/sloan_stt/README.md) | Hướng dẫn recognizer/demo; đối chiếu nhánh Model A-only của AC. |
| [app.py](../services/sloan_stt/app.py) | FastAPI demo nhận file audio và classify; không cần mở để AC import runtime. |
| [classifier.onnx](../services/sloan_stt/classifier.onnx) | Bản classifier root trùng checkpoint/classifier_sloan.onnx; SmartEyes loader còn kiểm tồn tại. |
| [encoder.int8.onnx](../services/sloan_stt/encoder.int8.onnx) | Bản encoder root trùng checkpoint encoder; chưa xóa trước khi sửa loader SmartEyes. |
| [infer_sloan_realtime.py](../services/sloan_stt/infer_sloan_realtime.py) | CLI mic inference standalone, tùy head; không phải orchestrator bệnh nhân. |
| [labels.txt](../services/sloan_stt/labels.txt) | Label file root của bộ model cũ/compatibility; runtime chính đọc checkpoint/labels_sloan.txt. |
| [letter_mapping.py](../services/sloan_stt/letter_mapping.py) | Từ điển cách đọc ký tự tham khảo ở root, không thay weight classifier. |
| [requirements.txt](../services/sloan_stt/requirements.txt) | Dependency audio/torch/torchaudio/ONNX và web demo, phần lớn không pin version. |
| [runtime.py](../services/sloan_stt/runtime.py) | Fbank→encoder checkpoint→classifier heads, temperature/probability/margin và masking nhãn bỏ. |
| [temperature.txt](../services/sloan_stt/temperature.txt) | Temperature root legacy/compatibility, không phải file được HEAD_FILES chọn. |
| [tokens.txt](../services/sloan_stt/tokens.txt) | Vocabulary/token asset kèm model; đường classification hiện tại không decode transcript bằng file này. |

</details>

<details>
<summary>services/sloan_stt/checkpoint — 11 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [classifier_3labels.onnx](../services/sloan_stt/checkpoint/classifier_3labels.onnx) | Head xác nhận có TRUE/FALSE grouping; AC clinic không load head này. |
| [classifier_sloan.onnx](../services/sloan_stt/checkpoint/classifier_sloan.onnx) | Head Sloan của đường clinic; còn nhãn X trong output frozen, runtime mask. |
| [encoder.int8.onnx](../services/sloan_stt/checkpoint/encoder.int8.onnx) | Encoder ONNX int8 runtime thực sự load để lấy sequence embedding. |
| [groups_3labels.txt](../services/sloan_stt/checkpoint/groups_3labels.txt) | Mapping nhóm nhãn xác nhận tham khảo kèm checkpoint. |
| [labels_3labels.txt](../services/sloan_stt/checkpoint/labels_3labels.txt) | Thứ tự output head xác nhận; runtime mask BO_QUA thay vì xóa index. |
| [labels_sloan.txt](../services/sloan_stt/checkpoint/labels_sloan.txt) | Thứ tự output classifier Sloan; không xóa dòng X làm lệch index. |
| [letter_mapping.py](../services/sloan_stt/checkpoint/letter_mapping.py) | Mapping phát âm Sloan đi cùng checkpoint. |
| [letter_mapping_3_labels.py](../services/sloan_stt/checkpoint/letter_mapping_3_labels.py) | Mapping phát âm nhãn xác nhận đi cùng checkpoint. |
| [temperature_3labels.txt](../services/sloan_stt/checkpoint/temperature_3labels.txt) | Temperature softmax của head xác nhận standalone. |
| [temperature_sloan.txt](../services/sloan_stt/checkpoint/temperature_sloan.txt) | Temperature softmax của head Sloan. |
| [tokens.txt](../services/sloan_stt/checkpoint/tokens.txt) | Token asset đi cùng encoder; không có bước ASR transcript tự do trong classify hiện tại. |

</details>

<details>
<summary>services/sloan_stt/tests — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [test_removed_skip_classes.py](../services/sloan_stt/tests/test_removed_skip_classes.py) | Test mask X/BO_QUA và giữ đúng output index; 7 hàm test trong file. |

</details>

<details>
<summary>services/sloan_stt/web — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [index.html](../services/sloan_stt/web/index.html) | Giao diện demo STT standalone; không phải chart bệnh nhân. |

</details>

<details>
<summary>services/smarteyes — 7 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [.gitignore](../services/smarteyes/.gitignore) | Quy tắc bỏ qua cache, môi trường và artifact local của service; không bỏ file đã tracked. |
| [Makefile](../services/smarteyes/Makefile) | Các target tiện ích chạy/cài/smoke của SmartEyes; không entrypoint clinic chính. |
| [README.md](../services/smarteyes/README.md) | Hướng dẫn SmartEyes/demo; có phần lịch sử cần đối chiếu profile clinic. |
| [clinic_jetson.yaml](../services/smarteyes/clinic_jetson.yaml) | Bản profile ở root service, khác bản configs/; không được AC clinic hiện tại chọn. |
| [environment.yml](../services/smarteyes/environment.yml) | Môi trường conda cho phát triển/demo SmartEyes. |
| [requirements.txt](../services/smarteyes/requirements.txt) | Dependency demo CV/audio/model, chưa khóa đủ version. |
| [run_webcam.sh](../services/smarteyes/run_webcam.sh) | Chạy webcam demo qua conda environment. |

</details>

<details>
<summary>services/smarteyes/configs — 3 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [clinic_jetson.yaml](../services/smarteyes/configs/clinic_jetson.yaml) | Profile CV mà AC clinic chọn: fixed zone, stand/eyes bật, headphones/spell tắt. |
| [default.yaml](../services/smarteyes/configs/default.yaml) | Profile demo mặc định của build_pipeline/công cụ standalone. |
| [stand_zone.json](../services/smarteyes/configs/stand_zone.json) | Sidecar chỉnh tại preview: polygon và crop track_box; có ưu tiên khi merge config. |

</details>

<details>
<summary>services/smarteyes/datasets/headphones — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [README.md](../services/smarteyes/datasets/headphones/README.md) | Hướng dẫn dataset/train và cảnh báo teacher nhiễu; mô tả default backend có phần cũ. |

</details>

<details>
<summary>services/smarteyes/datasets/headphones/_hold/bootstrap/images_dl — 9 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [stock_01.jpg](../services/smarteyes/datasets/headphones/_hold/bootstrap/images_dl/stock_01.jpg) | Ảnh bootstrap tải về stock_01; dữ liệu huấn luyện cách ly, không runtime. |
| [stock_02.jpg](../services/smarteyes/datasets/headphones/_hold/bootstrap/images_dl/stock_02.jpg) | Ảnh bootstrap tải về stock_02; dữ liệu huấn luyện cách ly, không runtime. |
| [stock_03.jpg](../services/smarteyes/datasets/headphones/_hold/bootstrap/images_dl/stock_03.jpg) | Ảnh bootstrap tải về stock_03; dữ liệu huấn luyện cách ly, không runtime. |
| [stock_04.jpg](../services/smarteyes/datasets/headphones/_hold/bootstrap/images_dl/stock_04.jpg) | Ảnh bootstrap tải về stock_04; dữ liệu huấn luyện cách ly, không runtime. |
| [stock_06.jpg](../services/smarteyes/datasets/headphones/_hold/bootstrap/images_dl/stock_06.jpg) | Ảnh bootstrap tải về stock_06; dữ liệu huấn luyện cách ly, không runtime. |
| [stock_08.jpg](../services/smarteyes/datasets/headphones/_hold/bootstrap/images_dl/stock_08.jpg) | Ảnh bootstrap tải về stock_08; dữ liệu huấn luyện cách ly, không runtime. |
| [stock_09.jpg](../services/smarteyes/datasets/headphones/_hold/bootstrap/images_dl/stock_09.jpg) | Ảnh bootstrap tải về stock_09; dữ liệu huấn luyện cách ly, không runtime. |
| [stock_10.jpg](../services/smarteyes/datasets/headphones/_hold/bootstrap/images_dl/stock_10.jpg) | Ảnh bootstrap tải về stock_10; dữ liệu huấn luyện cách ly, không runtime. |
| [stock_11.jpg](../services/smarteyes/datasets/headphones/_hold/bootstrap/images_dl/stock_11.jpg) | Ảnh bootstrap tải về stock_11; dữ liệu huấn luyện cách ly, không runtime. |

</details>

<details>
<summary>services/smarteyes/datasets/headphones/_hold/clinic_labeled — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [data.yaml](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/data.yaml) | Manifest dataset YOLO cách ly: đường dẫn split/class, không cấu hình runtime trạm. |

</details>

<details>
<summary>services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images — 161 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [clinic_00000.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00000.jpg) | Ảnh clinic teacher clinic_00000; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00001.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00001.jpg) | Ảnh clinic teacher clinic_00001; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00002.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00002.jpg) | Ảnh clinic teacher clinic_00002; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00003.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00003.jpg) | Ảnh clinic teacher clinic_00003; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00004.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00004.jpg) | Ảnh clinic teacher clinic_00004; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00005.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00005.jpg) | Ảnh clinic teacher clinic_00005; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00006.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00006.jpg) | Ảnh clinic teacher clinic_00006; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00007.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00007.jpg) | Ảnh clinic teacher clinic_00007; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00008.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00008.jpg) | Ảnh clinic teacher clinic_00008; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00009.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00009.jpg) | Ảnh clinic teacher clinic_00009; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00010.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00010.jpg) | Ảnh clinic teacher clinic_00010; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00011.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00011.jpg) | Ảnh clinic teacher clinic_00011; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00012.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00012.jpg) | Ảnh clinic teacher clinic_00012; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00013.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00013.jpg) | Ảnh clinic teacher clinic_00013; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00014.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00014.jpg) | Ảnh clinic teacher clinic_00014; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00015.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00015.jpg) | Ảnh clinic teacher clinic_00015; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00016.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00016.jpg) | Ảnh clinic teacher clinic_00016; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00017.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00017.jpg) | Ảnh clinic teacher clinic_00017; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00018.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00018.jpg) | Ảnh clinic teacher clinic_00018; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00019.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00019.jpg) | Ảnh clinic teacher clinic_00019; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00020.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00020.jpg) | Ảnh clinic teacher clinic_00020; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00021.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00021.jpg) | Ảnh clinic teacher clinic_00021; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00022.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00022.jpg) | Ảnh clinic teacher clinic_00022; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00023.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00023.jpg) | Ảnh clinic teacher clinic_00023; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00024.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00024.jpg) | Ảnh clinic teacher clinic_00024; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00025.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00025.jpg) | Ảnh clinic teacher clinic_00025; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00026.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00026.jpg) | Ảnh clinic teacher clinic_00026; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00027.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00027.jpg) | Ảnh clinic teacher clinic_00027; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00028.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00028.jpg) | Ảnh clinic teacher clinic_00028; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00029.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00029.jpg) | Ảnh clinic teacher clinic_00029; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00030.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00030.jpg) | Ảnh clinic teacher clinic_00030; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00031.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00031.jpg) | Ảnh clinic teacher clinic_00031; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00032.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00032.jpg) | Ảnh clinic teacher clinic_00032; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00033.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00033.jpg) | Ảnh clinic teacher clinic_00033; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00034.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00034.jpg) | Ảnh clinic teacher clinic_00034; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00035.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00035.jpg) | Ảnh clinic teacher clinic_00035; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00036.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00036.jpg) | Ảnh clinic teacher clinic_00036; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00037.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00037.jpg) | Ảnh clinic teacher clinic_00037; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00038.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00038.jpg) | Ảnh clinic teacher clinic_00038; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00039.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00039.jpg) | Ảnh clinic teacher clinic_00039; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00040.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00040.jpg) | Ảnh clinic teacher clinic_00040; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00041.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00041.jpg) | Ảnh clinic teacher clinic_00041; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00042.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00042.jpg) | Ảnh clinic teacher clinic_00042; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00043.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00043.jpg) | Ảnh clinic teacher clinic_00043; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00044.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00044.jpg) | Ảnh clinic teacher clinic_00044; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00045.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00045.jpg) | Ảnh clinic teacher clinic_00045; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00046.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00046.jpg) | Ảnh clinic teacher clinic_00046; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00047.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00047.jpg) | Ảnh clinic teacher clinic_00047; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00048.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00048.jpg) | Ảnh clinic teacher clinic_00048; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00049.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00049.jpg) | Ảnh clinic teacher clinic_00049; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00050.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00050.jpg) | Ảnh clinic teacher clinic_00050; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00051.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00051.jpg) | Ảnh clinic teacher clinic_00051; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00052.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00052.jpg) | Ảnh clinic teacher clinic_00052; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00053.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00053.jpg) | Ảnh clinic teacher clinic_00053; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00054.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00054.jpg) | Ảnh clinic teacher clinic_00054; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00055.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00055.jpg) | Ảnh clinic teacher clinic_00055; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00056.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00056.jpg) | Ảnh clinic teacher clinic_00056; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00057.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00057.jpg) | Ảnh clinic teacher clinic_00057; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00058.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00058.jpg) | Ảnh clinic teacher clinic_00058; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00059.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00059.jpg) | Ảnh clinic teacher clinic_00059; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00060.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00060.jpg) | Ảnh clinic teacher clinic_00060; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00061.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00061.jpg) | Ảnh clinic teacher clinic_00061; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00062.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00062.jpg) | Ảnh clinic teacher clinic_00062; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00063.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00063.jpg) | Ảnh clinic teacher clinic_00063; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00064.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00064.jpg) | Ảnh clinic teacher clinic_00064; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00065.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00065.jpg) | Ảnh clinic teacher clinic_00065; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00066.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00066.jpg) | Ảnh clinic teacher clinic_00066; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00067.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00067.jpg) | Ảnh clinic teacher clinic_00067; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00068.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00068.jpg) | Ảnh clinic teacher clinic_00068; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00069.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00069.jpg) | Ảnh clinic teacher clinic_00069; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00070.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00070.jpg) | Ảnh clinic teacher clinic_00070; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00071.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00071.jpg) | Ảnh clinic teacher clinic_00071; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00072.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00072.jpg) | Ảnh clinic teacher clinic_00072; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00073.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00073.jpg) | Ảnh clinic teacher clinic_00073; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00074.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00074.jpg) | Ảnh clinic teacher clinic_00074; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00075.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00075.jpg) | Ảnh clinic teacher clinic_00075; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00076.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00076.jpg) | Ảnh clinic teacher clinic_00076; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00077.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00077.jpg) | Ảnh clinic teacher clinic_00077; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00078.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00078.jpg) | Ảnh clinic teacher clinic_00078; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00079.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00079.jpg) | Ảnh clinic teacher clinic_00079; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00080.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00080.jpg) | Ảnh clinic teacher clinic_00080; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00081.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00081.jpg) | Ảnh clinic teacher clinic_00081; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00082.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00082.jpg) | Ảnh clinic teacher clinic_00082; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00083.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00083.jpg) | Ảnh clinic teacher clinic_00083; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00084.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00084.jpg) | Ảnh clinic teacher clinic_00084; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00085.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00085.jpg) | Ảnh clinic teacher clinic_00085; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00086.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00086.jpg) | Ảnh clinic teacher clinic_00086; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00087.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00087.jpg) | Ảnh clinic teacher clinic_00087; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00088.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00088.jpg) | Ảnh clinic teacher clinic_00088; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00089.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00089.jpg) | Ảnh clinic teacher clinic_00089; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00090.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00090.jpg) | Ảnh clinic teacher clinic_00090; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00091.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00091.jpg) | Ảnh clinic teacher clinic_00091; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00092.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00092.jpg) | Ảnh clinic teacher clinic_00092; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00093.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00093.jpg) | Ảnh clinic teacher clinic_00093; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00094.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00094.jpg) | Ảnh clinic teacher clinic_00094; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00095.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00095.jpg) | Ảnh clinic teacher clinic_00095; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00096.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00096.jpg) | Ảnh clinic teacher clinic_00096; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00097.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00097.jpg) | Ảnh clinic teacher clinic_00097; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00098.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00098.jpg) | Ảnh clinic teacher clinic_00098; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00099.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00099.jpg) | Ảnh clinic teacher clinic_00099; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00100.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00100.jpg) | Ảnh clinic teacher clinic_00100; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00101.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00101.jpg) | Ảnh clinic teacher clinic_00101; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00102.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00102.jpg) | Ảnh clinic teacher clinic_00102; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00103.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00103.jpg) | Ảnh clinic teacher clinic_00103; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00104.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00104.jpg) | Ảnh clinic teacher clinic_00104; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00105.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00105.jpg) | Ảnh clinic teacher clinic_00105; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00106.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00106.jpg) | Ảnh clinic teacher clinic_00106; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00107.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00107.jpg) | Ảnh clinic teacher clinic_00107; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00108.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00108.jpg) | Ảnh clinic teacher clinic_00108; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00109.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00109.jpg) | Ảnh clinic teacher clinic_00109; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00110.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00110.jpg) | Ảnh clinic teacher clinic_00110; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00111.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00111.jpg) | Ảnh clinic teacher clinic_00111; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00112.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00112.jpg) | Ảnh clinic teacher clinic_00112; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00113.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00113.jpg) | Ảnh clinic teacher clinic_00113; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00114.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00114.jpg) | Ảnh clinic teacher clinic_00114; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00115.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00115.jpg) | Ảnh clinic teacher clinic_00115; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00116.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00116.jpg) | Ảnh clinic teacher clinic_00116; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00117.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00117.jpg) | Ảnh clinic teacher clinic_00117; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00118.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00118.jpg) | Ảnh clinic teacher clinic_00118; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00119.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00119.jpg) | Ảnh clinic teacher clinic_00119; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00120.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00120.jpg) | Ảnh clinic teacher clinic_00120; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00121.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00121.jpg) | Ảnh clinic teacher clinic_00121; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00122.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00122.jpg) | Ảnh clinic teacher clinic_00122; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00123.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00123.jpg) | Ảnh clinic teacher clinic_00123; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00124.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00124.jpg) | Ảnh clinic teacher clinic_00124; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00125.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00125.jpg) | Ảnh clinic teacher clinic_00125; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00126.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00126.jpg) | Ảnh clinic teacher clinic_00126; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00127.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00127.jpg) | Ảnh clinic teacher clinic_00127; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00128.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00128.jpg) | Ảnh clinic teacher clinic_00128; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00129.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00129.jpg) | Ảnh clinic teacher clinic_00129; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00130.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00130.jpg) | Ảnh clinic teacher clinic_00130; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00131.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00131.jpg) | Ảnh clinic teacher clinic_00131; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00132.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00132.jpg) | Ảnh clinic teacher clinic_00132; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00133.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00133.jpg) | Ảnh clinic teacher clinic_00133; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00134.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00134.jpg) | Ảnh clinic teacher clinic_00134; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00135.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00135.jpg) | Ảnh clinic teacher clinic_00135; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00136.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00136.jpg) | Ảnh clinic teacher clinic_00136; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00137.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00137.jpg) | Ảnh clinic teacher clinic_00137; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00138.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00138.jpg) | Ảnh clinic teacher clinic_00138; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00139.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00139.jpg) | Ảnh clinic teacher clinic_00139; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00140.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00140.jpg) | Ảnh clinic teacher clinic_00140; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00141.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00141.jpg) | Ảnh clinic teacher clinic_00141; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00142.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00142.jpg) | Ảnh clinic teacher clinic_00142; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00143.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00143.jpg) | Ảnh clinic teacher clinic_00143; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00144.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00144.jpg) | Ảnh clinic teacher clinic_00144; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00145.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00145.jpg) | Ảnh clinic teacher clinic_00145; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00146.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00146.jpg) | Ảnh clinic teacher clinic_00146; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00147.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00147.jpg) | Ảnh clinic teacher clinic_00147; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00148.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00148.jpg) | Ảnh clinic teacher clinic_00148; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00149.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00149.jpg) | Ảnh clinic teacher clinic_00149; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00150.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00150.jpg) | Ảnh clinic teacher clinic_00150; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00151.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00151.jpg) | Ảnh clinic teacher clinic_00151; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00152.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00152.jpg) | Ảnh clinic teacher clinic_00152; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00153.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00153.jpg) | Ảnh clinic teacher clinic_00153; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00154.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00154.jpg) | Ảnh clinic teacher clinic_00154; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00155.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00155.jpg) | Ảnh clinic teacher clinic_00155; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00156.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00156.jpg) | Ảnh clinic teacher clinic_00156; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00157.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00157.jpg) | Ảnh clinic teacher clinic_00157; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00158.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00158.jpg) | Ảnh clinic teacher clinic_00158; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00159.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00159.jpg) | Ảnh clinic teacher clinic_00159; dữ liệu huấn luyện cách ly, không runtime. |
| [clinic_00160.jpg](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/images/clinic_00160.jpg) | Ảnh clinic teacher clinic_00160; dữ liệu huấn luyện cách ly, không runtime. |

</details>

<details>
<summary>services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels — 161 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [clinic_00000.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00000.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00000; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00001.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00001.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00001; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00002.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00002.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00002; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00003.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00003.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00003; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00004.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00004.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00004; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00005.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00005.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00005; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00006.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00006.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00006; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00007.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00007.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00007; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00008.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00008.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00008; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00009.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00009.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00009; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00010.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00010.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00010; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00011.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00011.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00011; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00012.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00012.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00012; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00013.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00013.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00013; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00014.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00014.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00014; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00015.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00015.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00015; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00016.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00016.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00016; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00017.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00017.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00017; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00018.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00018.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00018; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00019.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00019.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00019; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00020.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00020.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00020; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00021.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00021.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00021; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00022.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00022.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00022; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00023.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00023.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00023; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00024.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00024.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00024; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00025.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00025.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00025; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00026.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00026.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00026; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00027.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00027.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00027; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00028.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00028.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00028; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00029.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00029.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00029; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00030.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00030.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00030; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00031.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00031.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00031; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00032.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00032.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00032; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00033.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00033.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00033; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00034.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00034.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00034; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00035.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00035.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00035; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00036.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00036.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00036; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00037.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00037.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00037; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00038.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00038.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00038; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00039.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00039.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00039; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00040.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00040.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00040; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00041.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00041.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00041; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00042.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00042.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00042; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00043.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00043.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00043; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00044.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00044.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00044; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00045.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00045.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00045; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00046.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00046.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00046; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00047.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00047.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00047; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00048.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00048.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00048; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00049.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00049.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00049; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00050.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00050.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00050; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00051.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00051.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00051; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00052.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00052.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00052; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00053.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00053.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00053; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00054.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00054.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00054; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00055.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00055.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00055; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00056.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00056.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00056; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00057.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00057.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00057; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00058.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00058.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00058; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00059.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00059.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00059; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00060.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00060.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00060; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00061.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00061.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00061; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00062.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00062.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00062; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00063.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00063.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00063; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00064.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00064.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00064; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00065.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00065.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00065; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00066.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00066.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00066; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00067.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00067.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00067; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00068.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00068.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00068; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00069.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00069.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00069; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00070.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00070.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00070; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00071.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00071.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00071; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00072.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00072.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00072; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00073.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00073.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00073; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00074.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00074.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00074; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00075.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00075.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00075; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00076.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00076.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00076; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00077.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00077.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00077; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00078.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00078.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00078; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00079.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00079.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00079; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00080.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00080.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00080; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00081.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00081.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00081; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00082.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00082.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00082; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00083.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00083.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00083; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00084.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00084.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00084; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00085.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00085.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00085; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00086.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00086.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00086; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00087.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00087.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00087; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00088.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00088.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00088; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00089.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00089.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00089; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00090.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00090.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00090; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00091.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00091.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00091; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00092.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00092.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00092; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00093.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00093.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00093; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00094.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00094.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00094; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00095.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00095.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00095; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00096.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00096.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00096; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00097.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00097.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00097; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00098.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00098.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00098; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00099.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00099.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00099; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00100.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00100.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00100; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00101.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00101.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00101; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00102.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00102.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00102; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00103.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00103.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00103; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00104.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00104.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00104; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00105.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00105.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00105; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00106.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00106.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00106; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00107.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00107.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00107; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00108.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00108.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00108; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00109.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00109.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00109; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00110.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00110.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00110; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00111.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00111.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00111; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00112.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00112.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00112; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00113.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00113.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00113; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00114.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00114.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00114; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00115.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00115.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00115; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00116.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00116.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00116; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00117.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00117.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00117; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00118.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00118.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00118; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00119.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00119.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00119; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00120.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00120.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00120; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00121.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00121.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00121; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00122.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00122.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00122; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00123.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00123.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00123; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00124.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00124.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00124; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00125.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00125.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00125; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00126.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00126.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00126; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00127.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00127.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00127; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00128.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00128.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00128; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00129.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00129.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00129; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00130.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00130.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00130; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00131.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00131.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00131; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00132.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00132.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00132; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00133.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00133.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00133; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00134.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00134.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00134; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00135.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00135.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00135; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00136.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00136.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00136; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00137.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00137.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00137; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00138.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00138.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00138; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00139.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00139.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00139; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00140.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00140.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00140; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00141.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00141.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00141; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00142.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00142.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00142; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00143.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00143.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00143; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00144.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00144.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00144; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00145.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00145.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00145; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00146.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00146.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00146; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00147.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00147.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00147; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00148.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00148.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00148; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00149.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00149.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00149; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00150.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00150.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00150; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00151.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00151.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00151; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00152.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00152.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00152; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00153.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00153.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00153; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00154.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00154.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00154; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00155.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00155.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00155; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00156.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00156.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00156; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00157.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00157.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00157; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00158.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00158.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00158; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00159.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00159.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00159; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [clinic_00160.txt](../services/smarteyes/datasets/headphones/_hold/clinic_labeled/train/labels/clinic_00160.txt) | Nhãn YOLO cho ảnh cùng stem clinic_00160; thuộc tập cách ly, có thể là nhãn rỗng/negative. |

</details>

<details>
<summary>services/smarteyes/datasets/headphones/_hold/synthetic_HOLD — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [data.yaml](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/data.yaml) | Manifest dataset YOLO cách ly: đường dẫn split/class, không cấu hình runtime trạm. |

</details>

<details>
<summary>services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images — 80 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [syn_0000.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0000.jpg) | Ảnh synthetic smoke syn_0000; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0001.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0001.jpg) | Ảnh synthetic smoke syn_0001; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0002.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0002.jpg) | Ảnh synthetic smoke syn_0002; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0003.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0003.jpg) | Ảnh synthetic smoke syn_0003; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0004.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0004.jpg) | Ảnh synthetic smoke syn_0004; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0005.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0005.jpg) | Ảnh synthetic smoke syn_0005; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0006.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0006.jpg) | Ảnh synthetic smoke syn_0006; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0007.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0007.jpg) | Ảnh synthetic smoke syn_0007; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0008.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0008.jpg) | Ảnh synthetic smoke syn_0008; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0009.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0009.jpg) | Ảnh synthetic smoke syn_0009; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0010.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0010.jpg) | Ảnh synthetic smoke syn_0010; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0011.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0011.jpg) | Ảnh synthetic smoke syn_0011; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0012.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0012.jpg) | Ảnh synthetic smoke syn_0012; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0013.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0013.jpg) | Ảnh synthetic smoke syn_0013; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0014.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0014.jpg) | Ảnh synthetic smoke syn_0014; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0015.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0015.jpg) | Ảnh synthetic smoke syn_0015; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0016.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0016.jpg) | Ảnh synthetic smoke syn_0016; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0017.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0017.jpg) | Ảnh synthetic smoke syn_0017; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0018.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0018.jpg) | Ảnh synthetic smoke syn_0018; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0019.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0019.jpg) | Ảnh synthetic smoke syn_0019; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0020.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0020.jpg) | Ảnh synthetic smoke syn_0020; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0021.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0021.jpg) | Ảnh synthetic smoke syn_0021; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0022.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0022.jpg) | Ảnh synthetic smoke syn_0022; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0023.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0023.jpg) | Ảnh synthetic smoke syn_0023; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0024.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0024.jpg) | Ảnh synthetic smoke syn_0024; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0025.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0025.jpg) | Ảnh synthetic smoke syn_0025; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0026.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0026.jpg) | Ảnh synthetic smoke syn_0026; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0027.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0027.jpg) | Ảnh synthetic smoke syn_0027; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0028.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0028.jpg) | Ảnh synthetic smoke syn_0028; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0029.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0029.jpg) | Ảnh synthetic smoke syn_0029; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0030.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0030.jpg) | Ảnh synthetic smoke syn_0030; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0031.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0031.jpg) | Ảnh synthetic smoke syn_0031; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0032.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0032.jpg) | Ảnh synthetic smoke syn_0032; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0033.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0033.jpg) | Ảnh synthetic smoke syn_0033; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0034.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0034.jpg) | Ảnh synthetic smoke syn_0034; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0035.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0035.jpg) | Ảnh synthetic smoke syn_0035; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0036.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0036.jpg) | Ảnh synthetic smoke syn_0036; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0037.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0037.jpg) | Ảnh synthetic smoke syn_0037; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0038.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0038.jpg) | Ảnh synthetic smoke syn_0038; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0039.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0039.jpg) | Ảnh synthetic smoke syn_0039; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0040.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0040.jpg) | Ảnh synthetic smoke syn_0040; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0041.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0041.jpg) | Ảnh synthetic smoke syn_0041; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0042.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0042.jpg) | Ảnh synthetic smoke syn_0042; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0043.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0043.jpg) | Ảnh synthetic smoke syn_0043; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0044.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0044.jpg) | Ảnh synthetic smoke syn_0044; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0045.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0045.jpg) | Ảnh synthetic smoke syn_0045; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0046.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0046.jpg) | Ảnh synthetic smoke syn_0046; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0047.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0047.jpg) | Ảnh synthetic smoke syn_0047; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0048.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0048.jpg) | Ảnh synthetic smoke syn_0048; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0049.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0049.jpg) | Ảnh synthetic smoke syn_0049; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0050.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0050.jpg) | Ảnh synthetic smoke syn_0050; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0051.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0051.jpg) | Ảnh synthetic smoke syn_0051; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0052.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0052.jpg) | Ảnh synthetic smoke syn_0052; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0053.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0053.jpg) | Ảnh synthetic smoke syn_0053; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0054.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0054.jpg) | Ảnh synthetic smoke syn_0054; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0055.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0055.jpg) | Ảnh synthetic smoke syn_0055; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0056.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0056.jpg) | Ảnh synthetic smoke syn_0056; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0057.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0057.jpg) | Ảnh synthetic smoke syn_0057; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0058.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0058.jpg) | Ảnh synthetic smoke syn_0058; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0059.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0059.jpg) | Ảnh synthetic smoke syn_0059; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0060.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0060.jpg) | Ảnh synthetic smoke syn_0060; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0061.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0061.jpg) | Ảnh synthetic smoke syn_0061; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0062.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0062.jpg) | Ảnh synthetic smoke syn_0062; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0063.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0063.jpg) | Ảnh synthetic smoke syn_0063; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0064.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0064.jpg) | Ảnh synthetic smoke syn_0064; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0065.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0065.jpg) | Ảnh synthetic smoke syn_0065; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0066.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0066.jpg) | Ảnh synthetic smoke syn_0066; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0067.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0067.jpg) | Ảnh synthetic smoke syn_0067; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0068.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0068.jpg) | Ảnh synthetic smoke syn_0068; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0069.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0069.jpg) | Ảnh synthetic smoke syn_0069; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0070.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0070.jpg) | Ảnh synthetic smoke syn_0070; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0071.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0071.jpg) | Ảnh synthetic smoke syn_0071; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0072.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0072.jpg) | Ảnh synthetic smoke syn_0072; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0073.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0073.jpg) | Ảnh synthetic smoke syn_0073; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0074.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0074.jpg) | Ảnh synthetic smoke syn_0074; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0075.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0075.jpg) | Ảnh synthetic smoke syn_0075; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0076.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0076.jpg) | Ảnh synthetic smoke syn_0076; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0077.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0077.jpg) | Ảnh synthetic smoke syn_0077; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0078.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0078.jpg) | Ảnh synthetic smoke syn_0078; dữ liệu huấn luyện cách ly, không runtime. |
| [syn_0079.jpg](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/images/syn_0079.jpg) | Ảnh synthetic smoke syn_0079; dữ liệu huấn luyện cách ly, không runtime. |

</details>

<details>
<summary>services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels — 80 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [syn_0000.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0000.txt) | Nhãn YOLO cho ảnh cùng stem syn_0000; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0001.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0001.txt) | Nhãn YOLO cho ảnh cùng stem syn_0001; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0002.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0002.txt) | Nhãn YOLO cho ảnh cùng stem syn_0002; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0003.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0003.txt) | Nhãn YOLO cho ảnh cùng stem syn_0003; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0004.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0004.txt) | Nhãn YOLO cho ảnh cùng stem syn_0004; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0005.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0005.txt) | Nhãn YOLO cho ảnh cùng stem syn_0005; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0006.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0006.txt) | Nhãn YOLO cho ảnh cùng stem syn_0006; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0007.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0007.txt) | Nhãn YOLO cho ảnh cùng stem syn_0007; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0008.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0008.txt) | Nhãn YOLO cho ảnh cùng stem syn_0008; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0009.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0009.txt) | Nhãn YOLO cho ảnh cùng stem syn_0009; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0010.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0010.txt) | Nhãn YOLO cho ảnh cùng stem syn_0010; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0011.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0011.txt) | Nhãn YOLO cho ảnh cùng stem syn_0011; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0012.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0012.txt) | Nhãn YOLO cho ảnh cùng stem syn_0012; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0013.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0013.txt) | Nhãn YOLO cho ảnh cùng stem syn_0013; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0014.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0014.txt) | Nhãn YOLO cho ảnh cùng stem syn_0014; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0015.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0015.txt) | Nhãn YOLO cho ảnh cùng stem syn_0015; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0016.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0016.txt) | Nhãn YOLO cho ảnh cùng stem syn_0016; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0017.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0017.txt) | Nhãn YOLO cho ảnh cùng stem syn_0017; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0018.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0018.txt) | Nhãn YOLO cho ảnh cùng stem syn_0018; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0019.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0019.txt) | Nhãn YOLO cho ảnh cùng stem syn_0019; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0020.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0020.txt) | Nhãn YOLO cho ảnh cùng stem syn_0020; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0021.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0021.txt) | Nhãn YOLO cho ảnh cùng stem syn_0021; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0022.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0022.txt) | Nhãn YOLO cho ảnh cùng stem syn_0022; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0023.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0023.txt) | Nhãn YOLO cho ảnh cùng stem syn_0023; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0024.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0024.txt) | Nhãn YOLO cho ảnh cùng stem syn_0024; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0025.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0025.txt) | Nhãn YOLO cho ảnh cùng stem syn_0025; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0026.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0026.txt) | Nhãn YOLO cho ảnh cùng stem syn_0026; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0027.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0027.txt) | Nhãn YOLO cho ảnh cùng stem syn_0027; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0028.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0028.txt) | Nhãn YOLO cho ảnh cùng stem syn_0028; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0029.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0029.txt) | Nhãn YOLO cho ảnh cùng stem syn_0029; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0030.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0030.txt) | Nhãn YOLO cho ảnh cùng stem syn_0030; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0031.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0031.txt) | Nhãn YOLO cho ảnh cùng stem syn_0031; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0032.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0032.txt) | Nhãn YOLO cho ảnh cùng stem syn_0032; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0033.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0033.txt) | Nhãn YOLO cho ảnh cùng stem syn_0033; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0034.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0034.txt) | Nhãn YOLO cho ảnh cùng stem syn_0034; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0035.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0035.txt) | Nhãn YOLO cho ảnh cùng stem syn_0035; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0036.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0036.txt) | Nhãn YOLO cho ảnh cùng stem syn_0036; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0037.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0037.txt) | Nhãn YOLO cho ảnh cùng stem syn_0037; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0038.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0038.txt) | Nhãn YOLO cho ảnh cùng stem syn_0038; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0039.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0039.txt) | Nhãn YOLO cho ảnh cùng stem syn_0039; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0040.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0040.txt) | Nhãn YOLO cho ảnh cùng stem syn_0040; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0041.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0041.txt) | Nhãn YOLO cho ảnh cùng stem syn_0041; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0042.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0042.txt) | Nhãn YOLO cho ảnh cùng stem syn_0042; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0043.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0043.txt) | Nhãn YOLO cho ảnh cùng stem syn_0043; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0044.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0044.txt) | Nhãn YOLO cho ảnh cùng stem syn_0044; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0045.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0045.txt) | Nhãn YOLO cho ảnh cùng stem syn_0045; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0046.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0046.txt) | Nhãn YOLO cho ảnh cùng stem syn_0046; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0047.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0047.txt) | Nhãn YOLO cho ảnh cùng stem syn_0047; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0048.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0048.txt) | Nhãn YOLO cho ảnh cùng stem syn_0048; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0049.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0049.txt) | Nhãn YOLO cho ảnh cùng stem syn_0049; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0050.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0050.txt) | Nhãn YOLO cho ảnh cùng stem syn_0050; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0051.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0051.txt) | Nhãn YOLO cho ảnh cùng stem syn_0051; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0052.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0052.txt) | Nhãn YOLO cho ảnh cùng stem syn_0052; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0053.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0053.txt) | Nhãn YOLO cho ảnh cùng stem syn_0053; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0054.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0054.txt) | Nhãn YOLO cho ảnh cùng stem syn_0054; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0055.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0055.txt) | Nhãn YOLO cho ảnh cùng stem syn_0055; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0056.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0056.txt) | Nhãn YOLO cho ảnh cùng stem syn_0056; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0057.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0057.txt) | Nhãn YOLO cho ảnh cùng stem syn_0057; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0058.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0058.txt) | Nhãn YOLO cho ảnh cùng stem syn_0058; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0059.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0059.txt) | Nhãn YOLO cho ảnh cùng stem syn_0059; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0060.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0060.txt) | Nhãn YOLO cho ảnh cùng stem syn_0060; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0061.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0061.txt) | Nhãn YOLO cho ảnh cùng stem syn_0061; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0062.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0062.txt) | Nhãn YOLO cho ảnh cùng stem syn_0062; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0063.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0063.txt) | Nhãn YOLO cho ảnh cùng stem syn_0063; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0064.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0064.txt) | Nhãn YOLO cho ảnh cùng stem syn_0064; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0065.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0065.txt) | Nhãn YOLO cho ảnh cùng stem syn_0065; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0066.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0066.txt) | Nhãn YOLO cho ảnh cùng stem syn_0066; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0067.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0067.txt) | Nhãn YOLO cho ảnh cùng stem syn_0067; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0068.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0068.txt) | Nhãn YOLO cho ảnh cùng stem syn_0068; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0069.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0069.txt) | Nhãn YOLO cho ảnh cùng stem syn_0069; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0070.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0070.txt) | Nhãn YOLO cho ảnh cùng stem syn_0070; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0071.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0071.txt) | Nhãn YOLO cho ảnh cùng stem syn_0071; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0072.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0072.txt) | Nhãn YOLO cho ảnh cùng stem syn_0072; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0073.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0073.txt) | Nhãn YOLO cho ảnh cùng stem syn_0073; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0074.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0074.txt) | Nhãn YOLO cho ảnh cùng stem syn_0074; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0075.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0075.txt) | Nhãn YOLO cho ảnh cùng stem syn_0075; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0076.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0076.txt) | Nhãn YOLO cho ảnh cùng stem syn_0076; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0077.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0077.txt) | Nhãn YOLO cho ảnh cùng stem syn_0077; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0078.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0078.txt) | Nhãn YOLO cho ảnh cùng stem syn_0078; thuộc tập cách ly, có thể là nhãn rỗng/negative. |
| [syn_0079.txt](../services/smarteyes/datasets/headphones/_hold/synthetic_HOLD/train/labels/syn_0079.txt) | Nhãn YOLO cho ảnh cùng stem syn_0079; thuộc tập cách ly, có thể là nhãn rỗng/negative. |

</details>

<details>
<summary>services/smarteyes/docs — 1 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [FUTURE_EARBUDS.md](../services/smarteyes/docs/FUTURE_EARBUDS.md) | Ghi chú hướng phát triển phát hiện earbuds; chưa là chức năng đã tích hợp. |

</details>

<details>
<summary>services/smarteyes/outputs — 2 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [.gitkeep](../services/smarteyes/outputs/.gitkeep) | Ảnh output/probe .gitkeep dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [stand_zone_debug.png](../services/smarteyes/outputs/stand_zone_debug.png) | Ảnh output/probe stand_zone_debug dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |

</details>

<details>
<summary>services/smarteyes/outputs/cam_probe — 25 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [ANY_0_1280x720.jpg](../services/smarteyes/outputs/cam_probe/ANY_0_1280x720.jpg) | Ảnh output/probe ANY_0_1280x720 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [ANY_1_1920x1080.jpg](../services/smarteyes/outputs/cam_probe/ANY_1_1920x1080.jpg) | Ảnh output/probe ANY_1_1920x1080 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [ANY_2_1920x1080.jpg](../services/smarteyes/outputs/cam_probe/ANY_2_1920x1080.jpg) | Ảnh output/probe ANY_2_1920x1080 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [ANY_3_1920x1080.jpg](../services/smarteyes/outputs/cam_probe/ANY_3_1920x1080.jpg) | Ảnh output/probe ANY_3_1920x1080 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [AVFOUNDATION_0_1280x720.jpg](../services/smarteyes/outputs/cam_probe/AVFOUNDATION_0_1280x720.jpg) | Ảnh output/probe AVFOUNDATION_0_1280x720 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [AVFOUNDATION_1_1920x1080.jpg](../services/smarteyes/outputs/cam_probe/AVFOUNDATION_1_1920x1080.jpg) | Ảnh output/probe AVFOUNDATION_1_1920x1080 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [AVFOUNDATION_2_1920x1080.jpg](../services/smarteyes/outputs/cam_probe/AVFOUNDATION_2_1920x1080.jpg) | Ảnh output/probe AVFOUNDATION_2_1920x1080 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [AVFOUNDATION_3_1920x1080.jpg](../services/smarteyes/outputs/cam_probe/AVFOUNDATION_3_1920x1080.jpg) | Ảnh output/probe AVFOUNDATION_3_1920x1080 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [c270_v0.jpg](../services/smarteyes/outputs/cam_probe/c270_v0.jpg) | Ảnh output/probe c270_v0 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [c270_v1.jpg](../services/smarteyes/outputs/cam_probe/c270_v1.jpg) | Ảnh output/probe c270_v1 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [c270_v3.jpg](../services/smarteyes/outputs/cam_probe/c270_v3.jpg) | Ảnh output/probe c270_v3 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [c270_v4.jpg](../services/smarteyes/outputs/cam_probe/c270_v4.jpg) | Ảnh output/probe c270_v4 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [ffmpeg_0_FaceTime.jpg](../services/smarteyes/outputs/cam_probe/ffmpeg_0_FaceTime.jpg) | Ảnh output/probe ffmpeg_0_FaceTime dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [ffmpeg_2_C270.jpg](../services/smarteyes/outputs/cam_probe/ffmpeg_2_C270.jpg) | Ảnh output/probe ffmpeg_2_C270 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [ffmpeg_3_Kagami.jpg](../services/smarteyes/outputs/cam_probe/ffmpeg_3_Kagami.jpg) | Ảnh output/probe ffmpeg_3_Kagami dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [final_c270.jpg](../services/smarteyes/outputs/cam_probe/final_c270.jpg) | Ảnh output/probe final_c270 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [namegrab_C270_HD_WEBCAM.jpg](../services/smarteyes/outputs/cam_probe/namegrab_C270_HD_WEBCAM.jpg) | Ảnh output/probe namegrab_C270_HD_WEBCAM dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [namegrab_C270_HD_WEBCAM_none.jpg](../services/smarteyes/outputs/cam_probe/namegrab_C270_HD_WEBCAM_none.jpg) | Ảnh output/probe namegrab_C270_HD_WEBCAM_none dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [namegrab_Kagami_Rudo_Camera_none.jpg](../services/smarteyes/outputs/cam_probe/namegrab_Kagami_Rudo_Camera_none.jpg) | Ảnh output/probe namegrab_Kagami_Rudo_Camera_none dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [native_C270_HD_WEBCAM.jpg](../services/smarteyes/outputs/cam_probe/native_C270_HD_WEBCAM.jpg) | Ảnh output/probe native_C270_HD_WEBCAM dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [native_FaceTime_HD_Camera.jpg](../services/smarteyes/outputs/cam_probe/native_FaceTime_HD_Camera.jpg) | Ảnh output/probe native_FaceTime_HD_Camera dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [native_Kagami_Rudo_Camera.jpg](../services/smarteyes/outputs/cam_probe/native_Kagami_Rudo_Camera.jpg) | Ảnh output/probe native_Kagami_Rudo_Camera dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [pipe_c270.jpg](../services/smarteyes/outputs/cam_probe/pipe_c270.jpg) | Ảnh output/probe pipe_c270 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [verify_C270.jpg](../services/smarteyes/outputs/cam_probe/verify_C270.jpg) | Ảnh output/probe verify_C270 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |
| [warmed_c270.jpg](../services/smarteyes/outputs/cam_probe/warmed_c270.jpg) | Ảnh output/probe warmed_c270 dùng kiểm camera/vùng; artifact chẩn đoán, không mã hay weight. |

</details>

<details>
<summary>services/smarteyes/scripts — 14 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [bootstrap_headphones_world_labels.py](../services/smarteyes/scripts/bootstrap_headphones_world_labels.py) | YOLO-World teacher gán nhãn ảnh stock để bootstrap dataset. |
| [calibrate_line.py](../services/smarteyes/scripts/calibrate_line.py) | Công cụ click ảnh lấy HSV/polygon vùng đứng. |
| [camera_stream_server.py](../services/smarteyes/scripts/camera_stream_server.py) | MJPEG server cho camera nằm ở máy khác; không bắt buộc khi AC giữ USB trực tiếp. |
| [capture_headphones_frames.py](../services/smarteyes/scripts/capture_headphones_frames.py) | Thu frame để gán nhãn tai nghe tại phòng. |
| [clean_clinic_headphones_dataset.py](../services/smarteyes/scripts/clean_clinic_headphones_dataset.py) | Tạo nhãn trong crop đầu và hard negatives để giảm nhãn ghế/cả đầu sai. |
| [list_cameras.py](../services/smarteyes/scripts/list_cameras.py) | Liệt kê camera local theo camera_utils. |
| [make_smoke_video.py](../services/smarteyes/scripts/make_smoke_video.py) | Sinh video giả sàn/vùng/người để smoke, không dùng đánh giá độ chính xác thật. |
| [make_synthetic_over_ear_dataset.py](../services/smarteyes/scripts/make_synthetic_over_ear_dataset.py) | Sinh ảnh/nhãn tai nghe nhân tạo phục vụ smoke/packaging. |
| [mic_web_test.py](../services/smarteyes/scripts/mic_web_test.py) | Web level meter/record WAV microphone, default 8091. |
| [network_mic_server.py](../services/smarteyes/scripts/network_mic_server.py) | HTTP stream float32 mono PCM, thường dùng đường mic Mac/lab cũ. |
| [prepare_headphones_dataset.py](../services/smarteyes/scripts/prepare_headphones_dataset.py) | Gộp YOLO dataset một class over_ear; chọn/lọc nguồn dữ liệu. |
| [run_webcam_demo.py](../services/smarteyes/scripts/run_webcam_demo.py) | CLI demo toàn pipeline, cờ camera/check/backend/spelling, dùng phát triển/chẩn đoán. |
| [test_stand_zone_smoke.py](../services/smarteyes/scripts/test_stand_zone_smoke.py) | Test geometry/sidecar/track_box không cần chạy YOLO. |
| [train_headphones_yolo.py](../services/smarteyes/scripts/train_headphones_yolo.py) | Train YOLOv8n headphones và export ONNX; chạy trên máy huấn luyện phù hợp, không service clinic. |

</details>

<details>
<summary>services/smarteyes/src — 15 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [__init__.py](../services/smarteyes/src/__init__.py) | Marker package src; namespace khá chung, bridge phải quản lý import path. |
| [camera_utils.py](../services/smarteyes/src/camera_utils.py) | Dò camera Linux/macOS, resolve tên/index, OpenCV/FFmpeg capture và fallback. |
| [config_loader.py](../services/smarteyes/src/config_loader.py) | Đọc YAML và merge/seed/backfill sidecar stand_zone.json. |
| [detector.py](../services/smarteyes/src/detector.py) | Wrapper YOLO person, crop ROI rồi đổi tọa độ bbox về frame. |
| [device_utils.py](../services/smarteyes/src/device_utils.py) | Chọn thiết bị torch/ORT tự động hoặc explicit cho suy luận. |
| [eye_cover.py](../services/smarteyes/src/eye_cover.py) | Face Mesh, iris/EAR/skin/occluder và tracking vote/EMA cho trạng thái từng mắt. |
| [headphone_checker.py](../services/smarteyes/src/headphone_checker.py) | Backend tai nghe và hình học head/ear/wrist để phân biệt đeo với cầm; clinic tắt check. |
| [line_detector.py](../services/smarteyes/src/line_detector.py) | Dò vùng fixed/floor/tape, polygon/band và kiểm mắt cá nằm trong vùng. |
| [overlay.py](../services/smarteyes/src/overlay.py) | Vẽ bbox, pose, vùng, mắt, trạng thái/FPS và spelling HUD cho preview. |
| [pipeline.py](../services/smarteyes/src/pipeline.py) | Gộp YOLO→pose→zone/headphones/eyes→rules, cache kết quả xen frame, render hoặc capture loop standalone. |
| [pose_body.py](../services/smarteyes/src/pose_body.py) | MediaPipe Pose, landmark chân/tai/tay và head bbox từ person crop. |
| [readiness_rules.py](../services/smarteyes/src/readiness_rules.py) | Hold theo thời gian cho vùng/tai nghe/mắt, tạo ready/coaching. |
| [sloan_stt.py](../services/smarteyes/src/sloan_stt.py) | Wrapper microphone/STT cho demo SmartEyes standalone; vẫn kiểm model root cũ. |
| [spell_session.py](../services/smarteyes/src/spell_session.py) | State machine spelling standalone sau readiness; clinic spell.enabled=false. |
| [stand_zone.py](../services/smarteyes/src/stand_zone.py) | Normalize/lưu sidecar polygon và track_box, crop geometry, lọc/chọn người. |

</details>

<details>
<summary>services/smarteyes/weights — 2 file</summary>

| File | Ý nghĩa / vai trò |
|---|---|
| [headphones_over_ear.onnx](../services/smarteyes/weights/headphones_over_ear.onnx) | Bản export ONNX detector headphones; không phải chứng cứ đang được clinic load. |
| [headphones_over_ear.pt](../services/smarteyes/weights/headphones_over_ear.pt) | Weight YOLO headphones closed-set PyTorch; chỉ dùng khi bật backend/check tương ứng. |

</details>

