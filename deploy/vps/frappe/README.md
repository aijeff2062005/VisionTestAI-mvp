# Frappe Docker overlay for VisionTestAI hospitals (project `visiontestai`)

Replaces FastAPI `hospital_api` on host **:8000** with a shared Frappe bench
(`erpnext` + `healthcare` + `smart_hospital`, **version-16**) serving two
isolated hospital sites.

## Build + up (on VPS)

```bash
cd mvp_platform/deploy/vps/frappe
chmod +x build_image.sh up_frappe.sh
./build_image.sh          # long: clones frappe_docker, builds custom image
./up_frappe.sh            # stops hospital_api, starts Frappe on :8000
```

## Isolated local preview

The local preview uses separate containers and named volumes, and listens on
port `8002`; it does not modify the existing `:8000` or `:8001` stacks.

```bash
cd mvp_platform
docker build --build-arg BASE_IMAGE=visiontestai/frappe:v16-hc \
  -f deploy/vps/frappe/Dockerfile.smart \
  -t visiontestai/frappe:local-hospital-split .
docker compose -p visioncare-local \
  -f deploy/vps/frappe/compose.local.yml up -d
```

Open `http://tv.localhost:8002/desk/visioncare` for Trưng Vương or
`http://qy.localhost:8002/desk/visioncare` for Quân y. Both use the local-only
`Administrator` password `local-preview-admin`. First startup provisions the
sites and can take several minutes. Stop the preview with:

```bash
docker compose -p visioncare-local \
  -f deploy/vps/frappe/compose.local.yml down
```

The preview uses placeholder device services; camera capture can be tested in
the browser, while MQTT, media storage, QR decoding, and FaceID require their
real services to be configured separately.

`build_image.sh` uses BuildKit `--secret id=apps_json` (required by current
frappe_docker `images/custom/Containerfile`).

From Mac: `FRAPPE=1 ./remote_up.sh`.

## Defaults

| Item | Value |
|------|--------|
| Trưng Vương site/database | Existing `frontend` (kept for data continuity) |
| Trưng Vương hostname | `trungvuong.vision.primetek.ai` |
| Quân y site/database | `qdymd.vision.primetek.ai` |
| Quân y hostname | `qdymd.vision.primetek.ai` |
| Admin | `Administrator` / `admin` |
| MQTT | host `mqtt`, user/pass from `lab.env` |
| Desk / Trưng Vương API URL | `https://trungvuong.vision.primetek.ai` |
| Quân y Desk / API URL | `https://qdymd.vision.primetek.ai` |
| Image tags | `visiontestai/frappe:v16-hc`, `visiontestai/frappe:clinic` |

`TRUNG_VUONG_SITE_HOST` và `QUAN_Y_SITE_HOST` chọn hostname/site name cho từng bệnh viện. Mặc định Trưng Vương dùng `trungvuong.vision.primetek.ai`; Quân y dùng `qdymd.vision.primetek.ai`. Tạo DNS records cho cả hai hostname trỏ đến cùng ingress đang phục vụ host port `8000`, sau đó cấp TLS tại ingress. Nginx trong Frappe định tuyến theo request hostname. Jetson phải gọi hostname bệnh viện thay vì URL IP trực tiếp, vì hostname quyết định Frappe site nhận API request.

Site `frontend` và database/files hiện có được giữ làm site Trưng Vương; provision tạo alias `sites/<TRUNG_VUONG_SITE_HOST>` trỏ vào `frontend`. Quân y có site/database riêng theo hostname. Mỗi site cài `smart_hospital` cùng đúng một app bệnh viện (`tv_vision_hospital` hoặc `qy_vision_hospital`); provision dừng nếu phát hiện workflow của bệnh viện kia đã cài trên site.

Nếu thay hostname, cập nhật biến môi trường và DNS cùng lúc. Đổi hostname Quân y sau khi site đã tạo cần chạy quy trình Frappe rename-site/backup riêng; không đổi tên thư mục site thủ công.

## CRITICAL: ffmpeg in the Frappe image

Desk face scan → GDU `/api/v2/face_registration/without_mask` → **Milvus / Attu**
requires **ffmpeg inside the clinic Frappe image** (`visiontestai/frappe:clinic`).
`smart_hospital.api.face_service_api.register` converts WebM → MP4, then POSTs
GDU. If ffmpeg is missing, Frappe logs `[Errno 2] No such file or directory: 'ffmpeg'`,
JS swallows it as “GDU Face Service skipped”, and Attu never gets the face.

This is not optional. `Dockerfile.smart` and `deploy/local/Dockerfile.clinic`
install ffmpeg; rebuild `visiontestai/frappe:clinic` to persist it.

**Coder VPS:** do not `docker restart` / recreate `visiontestai-frappe-backend`.
Overlay mounts fail (`function not implemented`). Install ffmpeg on the running
container that serves gunicorn `:8000`. Debian apt to `deb.debian.org` often
times out; a static `ffmpeg` at `/usr/local/bin/ffmpeg` is enough.

## Desk pages

- `/app/patient-registration` — face + CCCD fields
- `/app/patient-vision-booking` — book Patient Appointment (vision)
- `/app/nurse-station` — appointments / arrivals / start measurement
- `/app/doctor-review` — Visual Acuity + Eye Prescription

## Multi-site operations

- `deploy/vps/frappe/provision_sites.sh` provisions both sites and is safe to rerun for the configured hostnames.
- `deploy_smart_hospital.sh` migrates the shared app on both sites.
- Hospital-specific app changes must be installed/migrated only on that hospital's site.
- `TRUNG_VUONG_STATION_ID` and `QUAN_Y_STATION_ID` can override the shared `STATION_ID` independently.

## Legacy FastAPI

```bash
docker compose -p visiontestai --profile legacy-hospital up -d hospital
# (requires freeing :8000 from frappe-frontend first)
```
