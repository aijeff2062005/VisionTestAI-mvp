# SLOAN STT

Ứng dụng nhận diện giọng nói theo bộ lớp đóng của bảng chữ cái Sloan. Model chạy local bằng ONNX Runtime, không cần tải model từ Internet khi khởi động.

Các lớp model gồm:

```text
C D H K N O R S V Z X
```

`X` là lớp đặc biệt: không hiển thị trong chuỗi kết quả. Khi hệ thống nhận diện `X`, bảng chữ cái mới sẽ được tạo.

## Yêu cầu

- Windows, Python 3.11 hoặc tương thích
- `uv`
- Microphone nếu sử dụng giao diện realtime

## Cài đặt bằng uv

Mở PowerShell tại thư mục `sloan-stt_v2`:

```powershell
uv venv
```

Kích hoạt môi trường theo hệ điều hành:

Windows PowerShell:

```powershell
.venv\Scripts\activate
```

Windows CMD:

```bat
.venv\Scripts\activate
```

Linux / macOS:

```bash
source .venv/bin/activate
```

Cài dependencies:

```bash
uv pip install -r requirements.txt
```

Nếu PowerShell không cho phép activate script, có thể chạy trực tiếp bằng Python trong môi trường ảo:

```powershell
uvicorn app:app --host localhost --port 7273
```

## Chạy ứng dụng

Sau khi activate môi trường:

```powershell
uvicorn app:app --host localhost --port 7273
```

Mở trình duyệt tại:

```text
http://localhost:7273
```

Cho phép trình duyệt truy cập microphone, sau đó bấm `Bật mic`. Bấm `Đổi bảng` để tạo một chuỗi mục tiêu mới gồm 5 chữ cái.

## Cách nhận diện

Giao diện thực hiện các bước sau:

1. Lấy âm thanh từ microphone.
2. Lọc nhiễu tần số thấp trước khi tính VAD.
3. Phát hiện đoạn người dùng bắt đầu và kết thúc nói.
4. Gửi từng đoạn âm thanh lên `/api/classify`.
5. Hiển thị kết quả và top-k.

Một đoạn được chốt sau khoảng `140 ms` im lặng. Âm thanh phải dài tối thiểu `160 ms` và có đủ số chunk có tiếng để được gửi nhận diện.

Khi model không đủ chắc chắn, backend trả về:

```json
{
  "prediction": "[UNK]",
  "reliable": false,
  "topk": []
}
```

UI hiển thị kết quả này là `[UNC]`. Có thể bấm vào `[UNC]` để xem top-k của đúng token đó.

## API

Endpoint nhận file WAV:

```text
POST /api/classify
```

Tham số `head` chọn classifier chạy trên cùng một embedding encoder:

- `sloan` (mặc định): nhận dạng C, D, H, K, N, O, R, S, V, Z, X;
- `three_labels`: trả về TRUE, SKIP hoặc FALSE và kèm nhãn chi tiết;
- `both`: chạy song song cả hai head, encoder chỉ chạy một lần.

Ví dụ: `POST /api/classify?head=both`.

Tham số tùy chọn:

- `min_confidence`: ngưỡng confidence, mặc định `0.55`
- `min_margin`: khoảng cách giữa top-1 và top-2, mặc định `0.05`

Ví dụ gọi bằng Python:

```python
import requests

with open("sample.wav", "rb") as audio:
    response = requests.post(
        "http://localhost:7273/api/classify",
        files={"audio": ("sample.wav", audio, "audio/wav")},
    )

print(response.json())
```

## Cấu trúc model

Các file model phải nằm trực tiếp trong thư mục này:

```text
sloan-stt_v2/
├── checkpoint/
│   ├── encoder.int8.onnx
│   ├── classifier.onnx
│   ├── classifier_sloan.onnx
│   ├── classifier_3labels.onnx
│   ├── labels.txt
│   ├── labels_sloan.txt
│   ├── labels_3labels.txt
│   ├── tokens.txt
│   └── temperature.txt
├── runtime.py
├── app.py
└── web/
    └── index.html
```

- `checkpoint/encoder.int8.onnx`: encoder đã quantize INT8.
- `checkpoint/classifier.onnx`: classifier các lớp Sloan.
- `checkpoint/labels.txt`: thứ tự nhãn tương ứng với output classifier.
- `checkpoint/temperature.txt`: hệ số calibration xác suất.

Không xóa hoặc đổi thứ tự các nhãn trong `checkpoint/labels.txt` nếu chưa export lại classifier.

## Lưu ý microphone

- Chạy bằng `localhost` để trình duyệt cho phép microphone.
- Nếu đổi microphone, kiểm tra thiết bị mặc định của Windows trước khi chạy.
- Nếu UI không nhận âm thanh, xem biểu tượng microphone trên thanh địa chỉ và cấp lại quyền cho `localhost`.
- Không mở đồng thời nhiều tab đang sử dụng microphone.
- Nếu thay đổi code frontend, hãy refresh mạnh bằng `Ctrl+F5`.

## Dừng ứng dụng

Trong cửa sổ PowerShell đang chạy server, nhấn:

```text
Ctrl+C
```
