# QY Vision Hospital Frappe app

App riêng cho trang điều dưỡng, đăng ký bệnh nhân, đặt lịch và duyệt kết quả của flow demo Quân y. Các route clinic và kiểm tra flow thuộc `qy_vision_hospital.api`; chúng dùng dịch vụ lưu trữ phiên đo, callback kết quả và MQTT chung trong `smart_hospital`.

App phụ thuộc `smart_hospital` cho DocType và các dịch vụ nghiệp vụ dùng chung. Không tự tạo tài khoản demo hoặc đặt lại mật khẩu trong migration.
