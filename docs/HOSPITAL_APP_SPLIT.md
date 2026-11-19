# Tách app cho Quân y và Trưng Vương

## Mục tiêu

Một nhánh và một image deploy chứa các app, nhưng mỗi Frappe site chỉ cài app của bệnh viện đó. Dữ liệu bệnh nhân, cấu hình trạm và kết nối Face ID/MQTT phải tách theo site.

```text
qy_vision_hospital ─────────────┐
                        ├── smart_hospital
tv_vision_hospital ─┘
```

## Ranh giới app

- `smart_hospital`: DocType dùng chung, contract kết quả đo, lưu kết quả, tích hợp thiết bị dùng chung. Không đặt menu, page, yêu cầu Face ID hoặc chính sách bắt buộc riêng của một bệnh viện ở đây.
- `qy_vision_hospital`: giao diện Frappe demo hiện có và flow không yêu cầu Face ID. Các yêu cầu riêng về CCCD, phân quyền và nút bắt đầu/dừng nằm trong app này.
- `tv_vision_hospital`: UI VisionCare mới, quy trình đăng ký/đồng bộ Face ID và các API/policy riêng cho Trưng Vương.

Hai app bệnh viện phụ thuộc `smart_hospital`; app chung không phụ thuộc ngược vào app bệnh viện. Giữ nguyên endpoint cũ trong giai đoạn chuyển đổi bằng wrapper tương thích, rồi bỏ wrapper sau khi hai site đã chuyển và xác nhận không còn client gọi.

## Cấu hình và cô lập

- Mỗi bệnh viện chạy trên một Frappe site/database riêng và chỉ cài `smart_hospital` cùng một app bệnh viện. Một bench duy nhất phục vụ cả hai hostname: `trungvuong.vision.primetek.ai` và `qdymd.vision.primetek.ai`.
- Site/database Trưng Vương hiện có tên `frontend` được giữ nguyên; provisioning tạo hostname alias về site đó. Site Quân y dùng hostname làm site name và database riêng.
- Frappe `site_config.json` giữ profile, station ID, URL/token tích hợp và các cờ bật tính năng theo site.
- Assistant Controller dùng cùng code/image nhưng chọn YAML profile theo station. `clinic.yaml` là flow Face ID Trưng Vương; `qy_vision_hospital.yaml` kế thừa cấu hình trạm chung và tắt Face ID, CCCD-after-face, VectorDB walk-in. Mỗi trạm chạy process riêng.
- MQTT station ID/topic, token media, gallery Face ID và tài khoản tích hợp phải riêng cho từng bệnh viện.
- Không dùng hostname/domain để suy ra quy trình. Chọn app/profile rõ ràng khi provision site.

## Chuyển đổi an toàn

1. Giữ các commit UI/app riêng làm mốc rollback.
2. Đưa hai app vào image; chỉ cài app của bệnh viện tương ứng lên từng site.
3. Đã chuyển page/API VisionCare, redirect/CSS và role cleanup sang `tv_vision_hospital`; API đặt lịch của UI mới cũng gọi namespace riêng.
4. Đã chuyển các page/API shell và clinic workflow của Quân y sang `qy_vision_hospital`; các route sở hữu riêng validate ngày/trạng thái lịch, reset khi dừng và kiểm tra kết quả duyệt. Chúng gọi dịch vụ tạo phiên đo/MQTT chung trong `smart_hospital`.
5. Đã chuyển hook bắt buộc ảnh Face ID sang app Trưng Vương và gỡ các patch cleanup clinic khỏi app chung.
6. Cấu hình DNS/TLS cho cả hai hostname cùng trỏ đến ingress Frappe, sau đó xác nhận bằng build/cài app và chạy luồng trên hai site trước khi mở cho người dùng.

## Các điểm phải xử lý khi chuyển code

- Hook `Patient Appointment` yêu cầu ảnh Face ID và xếp hàng đẩy ảnh lên station hiện chỉ được đăng ký bởi `tv_vision_hospital`.
- Nhánh demo tắt Face ID và VectorDB, còn flow hiện tại bật nhận diện và quét CCCD. Đây là profile vận hành khác nhau, không phải chỉ khác giao diện.
- Flow Face ID và direct-start được chọn theo cấu hình `bridges.face.mode`; direct-start giữ nguyên phiên đo do Desk tạo và không tạo bản ghi đo thứ hai. Cần tiếp tục rà kiểm tra lịch và quyền giữa hai adapter.
- `assistant_controller` phải giữ cả hai cách khởi tạo phiên: direct-start không Face ID và face-gate. Cấu hình theo station chọn flow tương ứng.
- Các API `allow_guest=True` cần được rà soát; callback thiết bị cần cơ chế xác thực riêng trước khi dùng chung cho nhiều site.

## Trạng thái

Các app đã được đóng gói và chuyển giao diện/hook/API theo phạm vi nêu trên trên nhánh `feature/hospital-app-split`. Cấu hình provision hai site chung một bench đã được bổ sung, nhưng chưa build image, chưa cài lên site và chưa xác nhận flow bằng staging. Không gộp hai app bệnh viện vào cùng một site; mỗi site chỉ cài app profile tương ứng.
