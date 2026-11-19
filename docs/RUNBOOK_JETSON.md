# Jetson — triển khai, cấu hình và xử lý sự cố

Phạm vi: luồng native hiện tại từ [`start_station.sh`](../deploy/jetson/start_station.sh). Đọc [tổng quan](../README.md) trước; các lệnh bên dưới là hướng dẫn vận hành, không phải xác nhận đã chạy trên thiết bị trong lần viết docs.

## 1. Cần mang những thư mục nào sang Jetson?

| Đường dẫn | Có cần? | Lý do |
|---|---|---|
| `services/assistant_controller/` | Bắt buộc | Python AC, chart, tablet, config, DMN, audio |
| `services/smarteyes/` | Bắt buộc khi `readiness=smarteyes` | Camera/CV; giữ `src`, `configs`, model mà config tham chiếu |
| `services/sloan_stt/` | Bắt buộc khi `stt=sloan` | Runtime, checkpoint encoder/classifier/labels/temperature; AC vẫn khởi tạo bridge dù mặc định tablet |
| `services/hospital/hospital_api/aiface_bs.py` | Bắt buộc cho live event AiFace | Script trạm gọi trực tiếp file này |
| `deploy/jetson/`, `deploy/env/lab.env` | Bắt buộc cho đường khởi động chuẩn | Service, script, endpoint và credential tại địa điểm |
| `data/journals/` bên trong AC | Dữ liệu phát sinh cần giữ | JSONL, results JSON, WAV; không nằm trong Git |
| `services/hospital/smart-hospital/`, Media/QR/VectorDB server | Không cần chạy trên Jetson | Đặt ở VPS; có thể giữ source để phát triển |
| Dataset huấn luyện, `outputs/`, `tmp/`, backup DB VPS | Không cần cho suy luận chính | Không sao chép vào bản trạm tối giản |

Nên giữ quan hệ sibling giữa AC, SmartEyes và Sloan vì `cfg.resolve()` lấy thư mục AC làm gốc. Ví dụ `../smarteyes` không được resolve từ shell cwd. `.venv` phải tạo trên đúng máy/kiến trúc; không sao chép venv x86 sang Jetson ARM.

## 2. Chuỗi khởi động thật

```text
systemd --user: clinic-station.service
  → start_station.sh
    → source deploy/env/lab.env, thiếu thì source lab.env.example
    → dựng biến VPS/MQTT/Face/Media; chọn Pulse microphone và loa USB
    → chạy aiface_bs.py nếu 7788 chưa có listener
    → exec .venv/bin/python -m ac.main --config .../clinic.yaml --mqtt-optional
      → load_config → dựng bridges / model / audio / clients
      → Display FastAPI + Uvicorn trên thread, cổng 8088
      → MQTT, TodayFaceSyncLoop, FaceWalkInLoop
      → Orchestrator chạy khi nhận session
```

Sloan clinic đang tạo `Recognizer(enabled_heads=("sloan",))` **trong tiến trình AC** tại `readiness_bridge.py`. `stt_process.py` có implementation worker riêng nhưng chưa được import/cắm vào đường này. Camera có reader thread lấy frame mới nhất; STT có callback giảm cạnh tranh với CV. Không cần chạy `sloan_stt/app.py` như HTTP service riêng để AC nhận giọng nói.

## 3. Chuẩn bị môi trường

1. Xác định Python/JetPack/CUDA đang có, camera `/dev/video*`, audio qua PulseAudio/PortAudio và quyền truy cập thiết bị của user chạy service.
2. Tạo venv nếu chưa có. Các requirements chỉ là ràng buộc dependency, chưa là lockfile tái lập đầy đủ cho Jetson.

```bash
python3 -m venv services/assistant_controller/.venv
services/assistant_controller/.venv/bin/python -m pip install -r services/assistant_controller/requirements.txt
```

Phần hardware/model cần thêm dependency trong `requirements-clinic.txt` và `services/sloan_stt/requirements.txt`. Chọn bộ torch/torchaudio/torchvision/ONNX Runtime tương thích JetPack đang cài trước khi áp dụng các file này; không thay wheel GPU đang hoạt động bằng một lần `pip install -U` không kiểm soát. Repo không cung cấp một bộ wheel Jetson cố định. `opencv-python-headless` của clinic phù hợp khi không dùng cửa sổ OpenCV.

```bash
services/assistant_controller/.venv/bin/python -c 'import torch, onnxruntime as ort; print("torch", torch.__version__, "CUDA", torch.cuda.is_available()); print("ORT", ort.get_available_providers())'
services/assistant_controller/.venv/bin/python -c 'import cv2, mediapipe, sounddevice, soundfile, librosa, torchaudio; print("imports OK")'
```

`device=auto` và provider preference không chứng minh đang chạy GPU. Hãy xem provider/log thực tế. Thiếu model/dependency Sloan có thể fallback mock ở nhánh hiện tại; xem [đánh giá](THUAT_TOAN_VA_DANH_GIA.md).

3. Nếu chưa có file môi trường, sao chép mẫu rồi thay endpoint/credential. Lệnh dưới không ghi đè file đã có:

```bash
test -f deploy/env/lab.env || cp deploy/env/lab.env.example deploy/env/lab.env
```

Mẫu có giá trị lab/cũ; phải sửa trước khi chạy. Không chép mật khẩu thực vào docs/Git. Các biến quan trọng:

| Biến trong `lab.env` | Tác dụng thực tế |
|---|---|
| `VPS_TAILNET_HOST`, `VPS_HOST` | Script ưu tiên tailnet; dựng endpoint mặc định |
| `HOSPITAL_BASE_URL` | Hostname site Frappe bệnh viện, ví dụ `https://trungvuong.vision.primetek.ai` hoặc `https://qdymd.vision.primetek.ai` |
| `MEDIA_BASE_URL`, `FACE_VECTORDB_BASE_URL` | URL dịch vụ VPS từ Jetson |
| `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD` | Script chuyển username/password thành `MQTT_USER`/`MQTT_PASS` |
| `AIFACE_PANEL_IP`, `AIFACE_PANEL_PORT` | Script xuất thành `FACE_HOST`/`FACE_PORT` |
| `JETSON_LAN_IP`, `AIFACE_CALLBACK_PORT` | IP/cổng mà panel kết nối ngược về Jetson |
| `FACE_PASSWORD` | Mật khẩu API panel qua EnvOverrides |
| `FACE_VDB_API_KEY` | Script chuyển thành `FACE_VECTORDB_API_KEY` |
| `AC_CONFIG` | Chọn profile AC; tên đúng là `AC_CONFIG`, không phải `CONFIG` |
| `USB_MIC_SOURCE`, `YEALINK_SINK` | Ghi đè lựa chọn source/sink Pulse trong script |

Dùng `configs/clinic.yaml` cho flow Face ID Trưng Vương. Dùng `AC_CONFIG="${AC}/configs/qy_vision_hospital.yaml"` cho Quân y; profile này kế thừa clinic config nhưng tắt Face ID, CCCD-after-face và đồng bộ VectorDB. Docker Compose nhận cùng lựa chọn qua `AC_CONFIG=/app/configs/qy_vision_hospital.yaml`.

**Giới hạn mapping:** `config.load_config()` không tự nạp mọi biến trong mẫu. Ví dụ `MEDIA_TOKEN`, `HOSPITAL_API_KEY`, `HOSPITAL_API_SECRET` không có mapping tương ứng trong loader AC hiện tại; cần cấu hình `media.token` và `hospital.api_key/api_secret` trong YAML nếu sử dụng. Docker Media đọc `MEDIA_TOKEN` là một đường khác. Cũng không có mapping `SLOAN_AUDIO_URL` trong loader; script chủ động unset tên này.

## 4. Thứ tự ưu tiên cấu hình

1. Default Pydantic trong `src/ac/config.py`.
2. YAML được chọn bởi `--config`; script lấy `AC_CONFIG` hoặc `configs/clinic.yaml`, thiếu thì `configs/default.yaml`.
3. Các biến `EnvOverrides` và một số `os.getenv`. `.env` chỉ áp dụng cho field thuộc `EnvOverrides`, theo cwd lúc tạo settings.
4. **Sau phần MQTT env, `VPS_HOST` lại ghi đè `mqtt.host`, `hospital.base_url`, `media.base_url`, `face_vectordb.base_url`.** Vì vậy không đúng nếu nói đơn giản “MQTT_HOST luôn cao nhất”.
5. Cuối loader, `HOSPITAL_BASE_URL`, `MEDIA_BASE_URL`, `FACE_VECTORDB_BASE_URL` ghi đè URL vừa dựng. MQTT host không có bước ghi đè cuối tương tự.

Với Frappe multi-site, không đặt `HOSPITAL_BASE_URL` thành IP/cổng trực tiếp: Frappe dùng HTTP Host để chọn site. DNS phải phân giải hostname bệnh viện đến ingress; nếu dùng LAN bridge, cấu hình DNS nội bộ/hosts để hostname vẫn giữ nguyên khi trỏ đến bridge.

Trước loader, `start_station.sh` source env file rồi export endpoint và thông tin panel. Script để Face ID/VectorDB theo YAML profile; các biến `FACE_MODE` và `FACE_VECTORDB_ENABLED` chỉ ghi đè khi được khai báo rõ trong environment.

**Settings UI:** `/preview` → phần cấu hình gọi `PUT /api/settings`, lưu YAML bằng file tạm rồi replace, cập nhật một số client tại chỗ. Đổi kết nối sẽ cập nhật `lab.env` **nếu file đó đã tồn tại** (hoặc file do `AC_LAB_ENV_FILE` chỉ định). Đổi endpoint VPS có thể gửi SIGTERM để supervisor khởi động lại; khi chạy tay không có supervisor, phải tự chạy lại. Không sửa endpoint/camera giữa phiên đo; input mode đã có check bận, các thiết lập khác cần thận trọng.

## 5. Chạy thủ công và tự khởi động

Chạy một instance, từ repository root:

```bash
bash deploy/jetson/start_station.sh
```

Nếu đang chạy systemd thì dùng service để restart, tránh dựng thêm instance. `REPLACE_AC=1` của script có thể `pkill` theo chuỗi `ac.main --config`; không dùng khi có nhiều trạm thử nghiệm trên cùng host.

```bash
systemctl --user status clinic-station.service
journalctl --user -u clinic-station.service -n 100 --no-pager
systemctl --user restart clinic-station.service
```

Trước khi cài autostart, sửa `WorkingDirectory` và `ExecStart` trong `deploy/jetson/clinic-station.service` cho đúng checkout/user trên máy mới: unit đang chứa đường dẫn tuyệt đối `/home/ivision/ImesPro/VisionTestAI/mvp_platform`.

```bash
bash deploy/jetson/install_autostart.sh
```

Script copy unit tới `~/.config/systemd/user/`, enable/restart, thử bật linger, đồng thời thêm cron `@reboot`. **Nó thêm cron ngay cả khi systemd đã được dùng**, có nguy cơ hai đường khởi động tranh cổng. Chọn một cơ chế sau khi kiểm tra:

```bash
systemctl --user is-enabled clinic-station.service
loginctl show-user "$USER" -p Linger
crontab -l
```

`After=tailscaled.service` trong user unit không bảo đảm đã đợi system service/network online thực sự; sleep 8 giây chỉ là đệm. Trạng thái broker/model/thiết bị vẫn cần kiểm tra sau boot.

**Docker Jetson là đường phụ chưa tương đương native:** image AC chỉ copy service AC, CMD dùng `default.yaml`, config mount read-only, chưa mount sibling SmartEyes/Sloan, camera và audio như native. Không dùng Compose đó để kết luận đã triển khai đủ trạm clinic.

## 6. Kiểm tra sau khi mở trạm

```bash
ss -lntp
curl --fail http://127.0.0.1:8088/api/camera/status
curl --fail http://127.0.0.1:8088/api/audio/input
curl --fail http://127.0.0.1:8088/api/face/health
curl --fail http://127.0.0.1:7790/events
pactl list short sources
pactl list short sinks
```

- `/` là chart bệnh nhân; `/preview` là camera và settings; `/control` phục vụ `control/real.html`, `/control-real` là đường tương đương.
- `/api/face/health` có thể gọi kiểm tra thiết bị; HTTP 200 riêng lẻ chưa đủ, đọc trạng thái bên trong JSON.
- MQTT dùng `connect_async` và Paho tự retry với delay 1–30 giây, subscribe lại khi kết nối thành công. Chart lên trước broker là hành vi có chủ đích; kiểm log `MQTT subscribed` để xác nhận.
- Preview mặc định tắt để tiết kiệm tài nguyên; không có MJPEG lúc idle chưa phải lỗi camera. Phiên đo sẽ khởi động CV theo nhu cầu.
- Từ Jetson, thử Frappe ping và TCP broker theo IP **đã cấu hình**, không lấy các địa chỉ ví dụ lịch sử trong script:

```bash
curl --fail 'https://YOUR_FRAPPE_HOST/api/method/frappe.ping'
nc -vz YOUR_VPS_TAILNET_IP 1883
```

Thay placeholder trước khi chạy. Kiểm tra cả chiều panel → Jetson `7788`; Jetson curl được panel chưa chứng minh callback hoạt động. IP callback phải ở mạng panel có route tới, không tự dùng IP Tailscale cho panel.

## 7. Hiệu chuẩn và nơi sửa thường xuyên

| Muốn thay đổi | Vị trí chính | Ghi chú |
|---|---|---|
| Khoảng cách thực | `clinic.yaml: protocol.distance_m`, settings UI | Đo từ mắt tới mặt màn hình, không từ camera |
| Kích thước chart | `display.*`, `/api/display/config`, `display/chart.js` | Auto từ diagonal + screen metrics; manual bằng thước |
| Camera | `bridges.smarteyes_source`, `camera_utils.py` | Tên thiết bị ổn định hơn index khi cắm/rút USB |
| Vùng đứng và crop dò người | `smarteyes/configs/stand_zone.json`, `stand_zone.py`, `/api/stand-zone` | Polygon vị trí chân và track_box là hai vùng khác nhau |
| Ngưỡng che mắt/hold | SmartEyes `configs/clinic_jetson.yaml` | Sidecar zone ghi đè phần liên quan YAML |
| Tai nghe bằng CV | `checks.headphones`, `headphones.*` | Hiện false; âm thanh Yealink vẫn sử dụng bình thường |
| Microphone/loa | `audio.*`, Pulse source/sink của script | Mức âm, sample rate, nhầm mic camera là lỗi độc lập với model |
| Speak/tablet và thời gian | `ui.input_mode`, `protocol.letter_chunk_seconds/tablet_chunk_seconds` | Đổi khi trạm idle |
| Ngưỡng STT | `protocol.letter_uncertain_threshold/letter_accept_threshold`, `bridges.sloan_*` | Low/high của clinic hiện 0.4/0.7 |
| Câu hướng dẫn/giọng | `scenarios/vi/{male,female}`, `manifest.yaml`, `audio_player.py` | Có fallback `display/prompts/vi`; `auto` phụ thuộc Patient.sex/cấu hình bệnh viện |
| Luồng và chấm điểm | `orchestrator.py`, `age_va.py`, `scoring.py`, DMN | Cần chạy test và thử thiết bị sau khi sửa |

Hiệu chuẩn manual: giữ độ phân giải/zoom/browser sẽ sử dụng, mở thước chuẩn hiển thị (target 100 mm mặc định), đo chiều dài thật rồi nhập giá trị đo. Hệ số mới về bản chất là `số pixel thanh / số mm đo được`. Kiểm tra lại sau fullscreen/đổi monitor. Không lấy `15.6 inch` trong YAML làm bằng chứng màn hình thật đúng kích thước đó. Source hiện chỉ nhận display metrics từ kết nối có Host localhost; browser remote thông thường không ghi đè metrics. Vẫn cần kiểm tra geometry của đúng kiosk sau khi đổi màn hình/EDID; xem điều tra thực tế trong mục 10 của THUAT_TOAN_VA_DANH_GIA.md.

## 8. Xử lý sự cố theo triệu chứng

| Triệu chứng | Kiểm tra trước | File liên quan |
|---|---|---|
| Chart không mở | Log unit, Python venv, cổng 8088 đang do ai giữ; model init trước server có thể làm boot chậm | `start_station.sh`, `main.py` |
| Chart mở nhưng Start Frappe không tới | Broker reachable/auth, station ID, log MQTT; `--mqtt-optional` cho phép AC sống khi broker hỏng | `mqtt_gateway.py`, `send_vision_measurement.py` |
| Panel nhận đúng người nhưng không tự đo | Callback IP/7788, BS event feed 7790, thời gian event, ID map ở Frappe, trạm có bận không | `aiface_bs.py`, `face_client.py`, `walk_in.py` |
| Bệnh nhân mới chưa vào panel | Appointment hôm nay, avatar hợp lệ, poll 60 s, lỗi `Today-face poll`, route VPS→Jetson nếu dùng push | `face_gallery_loop.py`, `face_sync.py` |
| Không thấy camera | Preview đang OFF? Camera bị process khác giữ? Kiểm tra source tên/C270, quyền USB và import CV | `readiness_bridge.py`, `camera_utils.py` |
| Có người nhưng không qua vùng đứng | So polygon chân với track_box, mắt cá có trong ảnh không, lighting và mirror | `stand_zone.py`, `pose_body.py` |
| Không nghe/không nhận lời | Đang tablet? Đúng source/sink Yealink? Mic C270 bị script mute? Có lỗi mock fallback? | `audio_device.py`, `microphone_stream.py`, `readiness_bridge.py` |
| GPU không được dùng/chậm | `torch.cuda.is_available`, ORT providers, preview render, dependency wheel | `device_utils.py`, `runtime.py` |
| Lưu settings xong bị thoát | Endpoint VPS thay đổi gây SIGTERM; cần supervisor hoặc chạy lại | `display_client.py` |
| YAML đúng mà endpoint vẫn sai | `lab.env`, `VPS_HOST` override, settings có ghi file env hay không | `config.py`, `start_station.sh` |
| Chart xong nhưng Frappe chưa có | `<session>_results.json`, log `HTTP callback failed`, URL/login redirect, callback body | `http_callback.py`, `vision.py` |

Không chạy thêm camera preview/network mic khi AC đang giữ cùng thiết bị nếu chưa xác định khả năng chia sẻ. Không giải quyết mất kết quả bằng cách xóa `data/journals`.

## 9. Cứu kết quả chưa đồng bộ

Tìm JSON kết quả đúng bệnh nhân/session trong `services/assistant_controller/data/journals/`, kiểm tra Frappe đã có `session_id` đó chưa, xác nhận callback URL trong journal/log. Adapter Frappe có lookup theo session và schema có unique session_id; cần xác nhận site đã migrate và kiểm tra xử lý concurrent duplicate trước khi dựa vào cơ chế này.

Chỉ khi đã đối chiếu, gửi lại **nguyên payload, giữ session_id**:

```bash
curl --fail-with-body -H 'Content-Type: application/json' \
  --data-binary @services/assistant_controller/data/journals/SESSION_ID_results.json \
  'https://YOUR_FRAPPE_HOST/api/method/smart_hospital.api.vision.receive_results'
```

Đọc JSON trả về `success`, `visual_acuity`, rồi kiểm tra trong Frappe. Nếu endpoint đã được bổ sung auth tại nơi triển khai, phải dùng credential của deployment đó. Repo hiện chưa có durable outbox hoặc lệnh replay tự động khi boot.
