# Checklist tích hợp HIS XML với QY

Tài liệu này mô tả luồng hiện có trong source QY và phần mỗi bên cần chuẩn bị trước khi chạy thật. “Bên HIS” là đơn vị xuất dữ liệu bệnh nhân; “bên QY” là nhóm vận hành Frappe, hàng chờ đo và trạm đo. Máy chạy connector có thể do bệnh viện hoặc một trong hai bên quản lý, nhưng phải được thống nhất rõ.

## 1. Luồng tổng thể

```text
HIS xuất XML chứa dữ liệu bệnh nhân theo contract đã chốt
  → đặt file vào thư mục chia sẻ
  → máy connector đọc file ổn định
  → connector POST XML qua HTTPS lên API QY
  → QY kiểm tra XML và tra Patient theo mã HIS
  → QY tự tạo QY Measurement Request (Chờ đo) cho mã HIS chưa có trong hàng chờ
  → nhân viên xem yêu cầu trong Hàng chờ đo
  → nhân viên bấm Bắt đầu đo
  → QY tạo Vision Measurement và gửi MQTT đến trạm
  → trạm đo, gửi Visual Acuity về Frappe
  → yêu cầu chuyển Hoàn tất
```

XML là chiều **HIS → QY**. Kết quả đo hiện được lưu trong Frappe QY; source hiện tại chưa có luồng tự xuất kết quả ngược thành XML/API về HIS.

## 2. Phân công chuẩn bị

### Bên HIS

- Chọn cách chuyển file: thư mục mạng SMB dùng chung là cách connector hiện có hỗ trợ.
- Cấp đường dẫn UNC đọc được từ máy connector, ví dụ `\\HIS-SERVER\Share\QY\XML`.
- Tạo XML chỉ chứa dữ liệu bệnh nhân theo contract đã chốt. Không cần thêm trường yêu cầu đo, trạng thái đo, hoặc lệnh bắt đầu đo; QY tự đưa bệnh nhân được nhập vào hàng chờ.
- Ghi file tạm rồi rename thành `.xml` sau khi ghi xong để connector không đọc file đang ghi dở.
- Dùng UTF-8 (có hoặc không BOM đều được), không thêm namespace vào XML.
- Cung cấp mã HIS ổn định để QY nhận diện bệnh nhân giữa các lần nhập.
- Cấp cho tài khoản Windows chạy connector quyền đọc thư mục và thư mục con.
- Cung cấp file test không chứa dữ liệu thật hoặc đã được cho phép dùng kiểm thử.
- Xác nhận file XML là nguồn dữ liệu bệnh nhân mà QY sẽ đọc; mọi bệnh nhân mới được nhận từ file sẽ được QY đưa vào hàng chờ tự động.

### Bên QY / nhóm triển khai ứng dụng

- Deploy phiên bản QY có endpoint `qy_vision_hospital.api.xml_intake.import_patient_xml` và DocType `QY Measurement Request`.
- Cung cấp URL QY HTTPS truy cập được từ máy connector, ví dụ `https://qdymd.vision.primetek.ai` (xác nhận domain thật trước khi cài).
- Tạo integration user riêng trên Frappe, gán role được code chấp nhận (`Nursing User`, `Physician`, `Healthcare Administrator` hoặc `System Manager`), tạo API Key/Secret và chuyển qua kênh bảo mật.
- Cấu hình/vận hành hàng chờ đo, MQTT và trạm QY. Trạm Quân y phải dùng `AC_CONFIG=/app/configs/qy_vision_hospital.yaml` để chạy direct-patient flow, không bật Face ID.
- Chỉ định người theo dõi lỗi nhập XML và xử lý yêu cầu trùng, yêu cầu bị kẹt hoặc đo lại.
- Nếu HIS cần nhận kết quả đo tự động, thiết kế thêm chiều xuất dữ liệu và thống nhất contract; hiện chưa có phần này trong code.

### Bên quản lý máy connector (có thể là bệnh viện hoặc bên triển khai)

- Cấp một PC/VM Windows luôn bật, cài Python 3.10+, truy cập được cả thư mục HIS và URL QY.
- Chạy connector dưới một tài khoản Windows ổn định có quyền đọc UNC share kể cả khi chạy nền lúc startup.
- Cài script, cấu hình biến môi trường, đặt Task Scheduler chạy lúc khởi động và restart khi lỗi.
- Bảo vệ API Secret, file SQLite state và log; chỉ người cần thiết được đọc.
- Không dùng ổ đĩa map kiểu `Z:\` cho task chạy nền; dùng UNC path vì drive map thường không tồn tại trong session Task Scheduler.

## 3. Contract XML hiện tại

Một file có root `<patients>`, bên trong là một hoặc nhiều `<patient>`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<patients>
  <patient>
    <his_patient_id>BN123456</his_patient_id>
    <full_name>Nguyen Van A</full_name>
    <cccd_last4>1234</cccd_last4>
  </patient>
</patients>
```

Quy tắc parser hiện tại:

- Bắt buộc `his_patient_id`, `full_name`, `cccd_last4`.
- `cccd_last4` phải đúng 4 chữ số. Không gửi toàn bộ CCCD theo contract này.
- Tối đa 2 MB và 500 bệnh nhân mỗi file.
- Không lặp `his_patient_id` trong cùng file; không có `DOCTYPE`/`ENTITY`.
- XML dùng tên tag chính xác như ví dụ; code hiện không xử lý namespace hoặc cấu trúc XML tùy biến.

Khi nhận file, QY tìm Patient theo `custom_his_patient_id`. QY tạo hoặc cập nhật Patient theo mã HIS, sau đó chỉ tạo `QY Measurement Request` trạng thái `Chờ đo` nếu mã HIS chưa có request. Nếu HIS gửi lại cùng mã nhưng thông tin bệnh nhân đã đổi, QY cập nhật hồ sơ Patient và không tạo lượt đo trùng. XML chỉ chuyển dữ liệu bệnh nhân, không có lệnh/flag yêu cầu đo. Gửi lại cùng dữ liệu không thay đổi được nhận diện là retry/trùng.

## 4. API nhập XML

```text
POST {QY_SITE_URL}/api/method/qy_vision_hospital.api.xml_intake.import_patient_xml
Content-Type: application/json
Authorization: token <api_key>:<api_secret>
```

Body connector gửi:

```json
{
  "xml_content": "<patients>...</patients>",
  "source_file": "xml-<fingerprint>.xml",
  "source_key": "<fingerprint>"
}
```

API yêu cầu user đã đăng nhập và có role clinic được phép. Phản hồi thành công có `success`, `batch_id`, `received`, `queued`, `duplicates`, `patients_created`, `patients_synced`, `requests`. Connector chỉ đánh dấu bản file đã gửi sau khi nhận `success: true`.

Kiểm tra credential trước khi nạp dữ liệu:

```powershell
curl.exe `
  -H "Authorization: token $env:QY_API_KEY`:$env:QY_API_SECRET" `
  "$env:QY_SITE_URL/api/method/frappe.auth.get_logged_user"
```

Kết quả phải trả về integration user, không phải `Guest`.

## 5. Cài và cấu hình connector trên Windows

Đặt `connector.py` ở thư mục cố định, ví dụ `C:\ProgramData\QYXmlConnector\connector.py`. Connector chỉ dùng Python standard library, không có `requirements.txt` cần cài.

Đặt biến môi trường cho **đúng Windows account sẽ chạy Task Scheduler**:

```text
QY_XML_INBOX=\\HIS-SERVER\Share\QY\XML
QY_SITE_URL=https://qdymd.vision.primetek.ai
QY_API_KEY=<api-key>
QY_API_SECRET=<api-secret>
QY_XML_STATE=C:\ProgramData\QYXmlConnector\state.sqlite3
QY_XML_POLL_SECONDS=30
QY_XML_STABLE_SECONDS=1
```

Giá trị site URL là ví dụ; thay bằng domain production/staging đã xác nhận. `QY_XML_STATE` nên nằm ngoài thư mục source và được backup/bảo vệ; file này ghi nhận phiên bản file connector đã xử lý.

Chạy thử trong PowerShell dưới đúng account:

```powershell
Set-Location C:\ProgramData\QYXmlConnector
py -3.10 .\connector.py
```

Khi thấy `Watching configured XML inbox`, connector đã vào vòng quét. Đưa một XML test mới vào inbox và kiểm tra hàng chờ QY. Dừng lần chạy thử bằng `Ctrl+C` trước khi tạo Task Scheduler để tránh chạy hai connector cùng lúc.

### Task Scheduler

Tạo task chạy dưới cùng Windows account đã cấu hình biến môi trường:

- Trigger: `At startup`.
- Action / Program: đường dẫn đầy đủ tới `python.exe` (lấy bằng `where.exe python` hoặc `py -3.10 -c "import sys; print(sys.executable)"`).
- Arguments: `C:\ProgramData\QYXmlConnector\connector.py`.
- Start in: `C:\ProgramData\QYXmlConnector`.
- Cấu hình restart task sau lỗi và lưu thông tin đăng nhập để task có thể đọc network share khi không có người đăng nhập.
- Kiểm thử bằng `Run` trong Task Scheduler rồi xem tab History và hàng chờ QY.

## 6. Chống trùng và giới hạn hiện tại — cần chốt trước go-live

- Connector giữ file tại chỗ và ghi file state cục bộ. Khi file đã được xác nhận thành công, cùng phiên bản file sẽ không gửi lại. Nếu mất/xóa file state, connector có thể quét lại file; API còn lớp nhận diện trùng.
- API fingerprint dữ liệu bệnh nhân (mã HIS, họ tên, 4 số cuối CCCD) trong lô. Gửi lại đúng payload được nhận diện là retry; nếu dữ liệu đổi, QY đồng bộ hồ sơ Patient theo mã HIS.
- Chính sách QY hiện chỉ xếp hàng một lần theo mã HIS. Nếu cùng bệnh nhân cần đo lại, xử lý bằng quy trình requeue tại QY hoặc thay đổi logic dedupe của QY; không yêu cầu HIS thêm cờ/lệnh yêu cầu đo vào XML đã chốt.
- Connector gửi `source_key`, nhưng API nhận diện retry bằng fingerprint nội dung bệnh nhân; `source_key` không phải khóa dedupe chính.
- Connector mặc định quét cả XML cũ trong inbox ngay lần đầu. Trước khi bật task, dùng inbox sạch hoặc chuyển file lịch sử ra ngoài inbox theo chính sách lưu trữ của HIS. Connector không tự archive.
- Code importer tạo/cập nhật Patient theo mã HIS. Chỉ mã chưa có `QY Measurement Request` mới được thêm vào hàng chờ; mã đã có request chỉ cập nhật hồ sơ, không tạo lượt đo mới. Code không gửi kết quả đo ngược sang HIS.
- Request được dedupe theo `his_patient_id` đã từng có trong `QY Measurement Request`: nhập lại mã HIS không tạo queue row khác. Tuy vậy, nếu thông tin trong XML thay đổi, QY vẫn đồng bộ tên và 4 số cuối CCCD vào Patient. Muốn đo lại cùng bệnh nhân cần một thao tác/luồng riêng, không gửi lại XML bệnh nhân.

## 7. Kiểm thử nghiệm thu

1. Credential gọi `get_logged_user` thành công và hiện đúng integration user.
2. Một XML hợp lệ tạo đúng Patient và một request `Chờ đo`.
3. Bản ghi xuất hiện ở Hàng chờ đo; mã HIS và 4 số cuối khớp.
4. Gửi lại cùng XML không tạo request thứ hai.
5. XML thiếu trường, sai 4 số cuối, sai root, quá kích thước hoặc lặp mã trong cùng file bị từ chối và có log lỗi.
6. Tắt mạng QY tạm thời: connector báo lỗi, giữ file chưa đánh dấu thành công và tự thử lại ở vòng tiếp theo.
7. Khởi động lại PC: Task Scheduler tự chạy lại, đọc share được và tiếp tục không tạo trùng.
8. Nhân viên bắt đầu một yêu cầu: trạm nhận đúng bệnh nhân, kết quả về Frappe và request chuyển `Hoàn tất`.

Không nghiệm thu bằng dữ liệu bệnh nhân thật cho tới khi đã thống nhất quyền truy cập, môi trường staging/test, chính sách lưu file XML và cách xử lý lượt đo lại.
