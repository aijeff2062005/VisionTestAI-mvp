# Môi trường build đã cài trong workspace

- Docker Engine 29.1.3 (gói Ubuntu docker.io)
- Buildx 0.30.1; Compose 2.40.3
- qemu-user-static 8.2; binfmt qemu-aarch64 đã đăng ký với fix-binary
- Builder `qy-arm64`: docker-container, BuildKit v0.34.2, native snapshotter
- Docker storage `vfs`, data root `/var/lib/docker-qy-vfs`
- Docker chỉ mở Unix socket, không mở TCP daemon.

Đã kiểm tra RUN ARM64 trong build và chạy container trả `aarch64`;
Compose QY-only kiểm tra config thành công với password giả dùng riêng cho syntax check.
Image visiontestai/frappe:qy-arm64-test1 đã build đầy đủ và PASS kiểm tra
code, asset, native import, version, kiến trúc ARM64. Chưa nghiệm thu Jetson thật.

Workspace không chạy systemd làm PID 1. Daemon đang chạy nền, log tại
`/tmp/qy-dockerd.log`. Nếu daemon dừng, từ môi trường ngoài sandbox có sudo:

```bash
sudo sh -c 'nohup dockerd --storage-driver=vfs --feature containerd-snapshotter=false --data-root=/var/lib/docker-qy-vfs > /tmp/qy-dockerd.log 2>&1 < /dev/null &'
sudo docker info
sudo docker buildx inspect qy-arm64 --bootstrap
sudo docker run --rm --platform linux/arm64 qy-arm64-smoke:local
```

Chỉ khởi động nếu chưa có daemon hoạt động. Nếu workspace bị tạo lại toàn bộ thì
các gói cài hệ thống có thể không còn. Vfs/native dùng nhiều disk hơn overlay.

Sau khi chốt source refs và tạo .env theo README, build trong phiên có quyền quản trị:

```bash
sudo --preserve-env=FRAPPE_REF,ERPNEXT_REF,HEALTHCARE_REF,DESK_REF,FRAPPE_DOCKER_COMMIT,CUSTOM_IMAGE ./build.sh
```

Không cần đổi quyền socket hoặc thêm user vào nhóm docker. Trong phiên Codex,
các lệnh Docker cần chạy ngoài sandbox. Image smoke test giữ lại với tag
`qy-arm64-smoke:local` để kiểm tra nhanh môi trường.
