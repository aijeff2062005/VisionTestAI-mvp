# Nguyên nhân và kế hoạch sửa lỗi kiosk Jetson/TV

Ngày lập: 07/10/2026. Mốc source: `c018d68`, nhánh `workflow_v2`.

**Trạng thái:** tài liệu đề xuất, chưa triển khai các bản sửa bên dưới. File này được tạo sau khi push commit trên và được giữ local theo yêu cầu. Phạm vi: TV chậm hơn luồng đo/browser máy khác, mất ảnh, đôi khi hiện màn hình lạ hoặc giống code cũ.

## 1. Kết luận và giới hạn bằng chứng

Vấn đề quan trọng nhất là **backend chưa gắn thời điểm bắt đầu nhận câu trả lời với trạng thái sẵn sàng hiển thị của kiosk**. Vì vậy một browser chậm có thể làm người bệnh mất thời gian nhìn ký tự dù backend và browser máy khác vẫn chạy đúng nhịp riêng của chúng.

Ngoài ra đã xác nhận preview chạy nền, có swap và thiếu cơ chế thống nhất phiên bản frontend/backend. Chưa đủ bằng chứng kết luận GPU hỏng, Chrome kiosk dùng software rendering, ảnh không tồn tại, hoặc tab đang chạy JS cũ.

Người vận hành đang SSH từ xa; các output DP hiện disconnected. Đo nền và thử headless không thay thế việc tái hiện trên TV. Không restart dịch vụ, đổi power mode hoặc chạy khám giả vào hệ thống trong đợt điều tra.

Báo cáo đầy đủ: [Đánh giá kỹ thuật, mục 10](THUAT_TOAN_VA_DANH_GIA.md#10-điều-tra-kiosktv-và-benchmark-trực-tiếp-ngày-07102026). Bằng chứng local: [tmp/perf_20261007](../tmp/perf_20261007/), bị Git ignore và không có trên remote.

| Phép đo | Kết quả | Ý nghĩa và giới hạn |
|---|---|---|
| CPU toàn máy, trung bình 6 lõi; 49 mẫu 1 giây | Trung bình 11,57%, đỉnh 18,17% | Chưa thấy bão hòa nền; chưa đo peak ca khám |
| GPU GR3D cùng cửa sổ | Trung bình 3,59%, đỉnh 39% | Không phải FPS hoặc feature status Chrome |
| RAM | Trung bình 5751/7607 MB | Khoảng 76% RAM đã dùng |
| AC RSS | Trung bình 1951 MiB | Chưa bao gồm mọi allocation GPU/shared/swap |
| Chrome RSS cộng gộp | Trung bình 803 MiB | Có thể đếm trùng shared pages; cần PSS để phân bổ |
| Swap trong khoảng 44 giây | 93,77 MiB ra, 0,82 MiB vào; 558 major faults | Toàn máy; chưa xác định process gây/chịu ảnh hưởng |
| HTTP localhost | 45/45 trả 200; median theo endpoint 3,10–6,41 ms, max 25,29 ms | HTML, JS, CSS, hai ảnh, font, config; không đo decode/paint |
| Chuyển cảnh headless, 90 lệnh/kích thước | Handler + layout median 2,55–2,70 ms; không exception | Software renderer của browser thử; không đại diện kiosk/TV |

TV 56 inch không tự làm tăng tải tính toán. Các yếu tố cần đo là số pixel, DPR, refresh, compositor, đường GPU và nội dung render.

## 2. Bản đồ nguyên nhân → cách sửa

| ID | Nguyên nhân | Mức bằng chứng | Ưu tiên | Nơi can thiệp |
|---|---|---|---|---|
| K01 | Bắt đầu nghe khi chỉ mới gửi lệnh, chưa biết kiosk đã sẵn sàng | Source xác nhận | P0 | `orchestrator.py`, `display_client.py`, `chart.js` |
| K02 | Countdown theo thời điểm nhận, reconnect replay, lệnh gửi muộn không hết hạn | Source xác nhận; chưa chứng minh đã xảy ra lúc lag | P0 | `DisplayHub`, `chart.js` |
| K03 | Launcher ngoài repo, thiếu readiness/watchdog trang/build handshake | Đã xác nhận | P1 | Kiosk launcher, deploy, backend và HTML/JS |
| K04 | RAM dùng cao và swap; có IDE/desktop/model cùng chạy | Đo được; quan hệ với lag chưa xác lập | P1 | Cấu hình vận hành, model/worker lifecycle |
| K05 | Preview còn bật khi idle, encode/render tiếp tục theo cờ runtime | Runtime và source xác nhận | P1 | `readiness_bridge.py`, API/UI preview |
| K06 | Nuốt lỗi JS; không chờ ảnh decode và không có fallback phù hợp | Source xác nhận; chưa tái hiện mất ảnh | P1 | `chart.js`, `index.html`, `chart.css` |
| K07 | Không biết màn hình lạ thuộc scene, release hay dialog desktop nào | Chưa xác định nguyên nhân cụ thể | P1 quan sát, P2 dọn legacy | Logging scene, kiosk, handler UI |
| K08 | Async endpoint settings gọi quét hardware đồng bộ, có thể chặn event loop | Source xác nhận; chưa đo thấy nghẽn | P2, tăng ưu tiên nếu trace xác nhận | `display_client.py` |

P0: ảnh hưởng tính đúng của lượt đo/hiển thị. P1: ổn định vận hành và khả năng xác định lỗi. P2: tối ưu hoặc dọn code dựa trên bằng chứng.

## 3. Thiết kế sửa K01–K02: đồng bộ phiên và hiển thị

### Hiện tại

`_listen_letter_model_a()` gửi `show_single_letter()`, gọi `_start_letter_clip()` rồi `listen_chunk(timeout=seconds)`. Socket send hoàn tất không có nghĩa browser đã xử lý command, layout, font và ảnh.

`startListenProgress()` dùng `Date.now() + duration` lúc nhận command. Reconnect gửi lại `last_command` nên có thể chạy lại duration. `DisplayHub.send()` đợi future tối đa 2 giây nhưng không hủy khi timeout; tác vụ có thể tiếp tục sau đó. Broadcast đã gửi đồng thời tới client với timeout 0,75 giây/client và có khóa thứ tự: không quy lỗi thành “gửi tuần tự vô hạn”.

### Luồng đề xuất

1. Browser đăng ký role: kiosk bệnh nhân, tablet điều khiển hoặc observer. Chỉ kiosk được ràng buộc đúng trạm mới có quyền ACK hiển thị; không tin một role tự khai để thay thế việc xác thực/ràng buộc kết nối.
2. Backend phát `prepare_stimulus` gồm `station_id`, `session_id`, `epoch`, `sequence`, `window_id`, `build_id` và thời hạn hiệu lực. Tên event/field là thiết kế mới, chưa có sẵn.
3. Kiosk kiểm tra phiên/thứ tự, cập nhật DOM, đợi font/ảnh cần thiết và lượt render rồi gửi `stimulus_ready` cùng ID. Không block scene không có ảnh vì một asset không liên quan.
4. Backend chỉ nhận ACK từ kiosk hiện hành, đúng phiên và đúng window, chưa hết hạn. Sau ACK, mở cửa sổ ghi/nhận đáp án và công bố deadline/thời gian còn lại. Đảm bảo bắt đầu clip và STT bám cùng mốc có ghi log.
5. UI hiển thị thời gian còn lại theo mapping clock/RTT; backend giữ quyền quyết định hết hạn bằng monotonic clock. Không trừ trực tiếp timestamp `performance.now()` của browser với clock backend.
6. Nếu ACK hết hạn, kiosk mất kết nối hoặc asset bắt buộc lỗi: pause/fail bước theo chính sách rõ ràng; không âm thầm chấm sai người bệnh. Chặn đáp án window trước/trong bước chưa bắt đầu.
7. Reconnect lấy snapshot phiên có sequence/window/deadline. Không restart timer và không replay kích thích đã hết hạn. Backend restart tạo epoch mới để ACK/lệnh phiên trước không còn hiệu lực.

ACK dựa trên render lifecycle là tín hiệu sẵn sàng của browser, **không chứng minh pixel đã xuất hiện vật lý trên TV**. `requestAnimationFrame` chạy trước repaint và có thể ngừng ở tab nền; cần timeout và trạng thái visibility. Khi cần định lượng độ trễ quang học, dùng phép đo TV riêng.

Hàng đợi cần giới hạn và có chính sách quá tải. Cho phép thay thế trạng thái thị giác đã lỗi thời, nhưng không gộp bừa audio/action có tác dụng riêng. Hủy future timeout là một phần; vẫn phải kiểm tra expiry/epoch ở đầu nhận vì cancel có thể đua với send. Không dùng tăng timeout hoặc thêm `sleep` cố định làm cách đồng bộ.

### Nơi sửa và kiểm thử

- [orchestrator.py](../services/assistant_controller/src/ac/orchestrator.py): `_listen_letter_model_a`, thứ tự chuẩn bị → ACK → ghi/nhận → hoàn tất; cancel và mất kết nối phải thoát được.
- [display_client.py](../services/assistant_controller/src/ac/display_client.py): `DisplayHub`, đăng ký client, ACK, snapshot, queue, expiry và timeout.
- [chart.js](../services/assistant_controller/display/chart.js): `connectAc`, `applyRemoteCommand`, `startListenProgress`, ACK và reconnect.
- Mở rộng test orchestrator/input/session-cancel; thêm test giao thức display với clock giả và browser integration cho render/error/reconnect.

Bắt buộc thử: delay browser 0,5–2 giây; ACK duplicate/sai window/sai role; observer chậm; mất mạng trước/sau ACK; backend restart; replay hết hạn; timeout lúc cancel; tablet bấm muộn. Chỉ có một cửa sổ nhận đáp án hợp lệ và không mở trước ACK hợp lệ.

## 4. Sửa K03 và K07: phiên bản, kiosk và màn hình lạ

Launcher thực tế: `~/.config/autostart/jetson-kiosk.desktop` → `/home/ivision/jetson-kiosk/start.sh` → Chrome với profile persistent và URL `http://127.0.0.1:8088`. Vòng lặp hiện chủ yếu theo dõi process thoát, không kiểm tra sức khỏe trang.

HTML `no-store` không khiến tab đang mở tự thực thi JS mới khi backend restart. Query version JS/CSS hiện cố định, không có build handshake. Source orchestrator có mtime sau khi AC khởi động; chưa biết chính xác source trong process khác trên đĩa thế nào. Mtime chart trước lúc Chrome khởi động nên chưa chứng minh chart hiện tại là bản cũ.

Kế hoạch:

- Đưa launcher và cấu hình mẫu vào repo, giữ profile runtime riêng. Duy trì một cơ chế quản lý launcher, tránh GNOME autostart và systemd cùng khởi động hai kiosk.
- Release gồm backend, frontend, protocol version và config schema; asset theo content hash. Thêm endpoint version/health và build ID trong log/trang chẩn đoán.
- Chờ HTTP ready trước load; retry có backoff và giới hạn. Watchdog kiểm tra heartbeat của đúng trang/kiosk, không chỉ PID Chrome tồn tại. Không coi trang tĩnh không có command mới là bị treo.
- Khi build không tương thích: ngừng nhận lượt mới, đưa phiên hiện tại về trạng thái có kiểm soát, reload lúc an toàn. Tránh reload giữa lượt đọc và vòng reload vô hạn khi server chưa sẵn sàng.
- Mỗi transition ghi scene ID, sequence, session/window và build. Khi báo màn hình lạ, đối chiếu screenshot có timestamp với log; phân biệt nội dung app, trang lỗi browser và popup desktop.
- Audit handler cũ như `letter_confirm`, welcome/register và setup/manual. Chỉ xóa sau khi xác định không được flow nào gọi; kiểm regression scene transitions. Cây cửa sổ có `apport-gtk` là một manh mối, chưa chứng minh nó là màn hình lạ người dùng đã thấy.

Nghiệm thu: cold boot khi backend lên chậm vẫn vào đúng trang; deploy lúc idle đưa cả hai phía về cùng release; disconnect/reconnect không hiện scene hết hạn; watchdog có backoff và không phá phiên khỏe. Có rollback cả backend và frontend về cùng release.

## 5. Sửa K04–K05: RAM, model và preview

Preview runtime bật dù không có lượt đo. Trong [readiness_bridge.py](../services/assistant_controller/src/ac/readiness_bridge.py), vòng lặp gọi `pipeline.process_frame`; khi preview bật sẽ render rồi encode JPEG. `set_preview_enabled(False)` hiện đã bảo vệ camera cần cho exam qua `exam_hold`; cần giữ hành vi này.

Các bước:

1. Đo lại PSS, swap theo process, thời gian inference, GR3D/EMC và event-loop lag trong cùng cửa sổ ca khám. Ghi cả trạng thái preview, người xem và model đang nạp.
2. Tách profile vận hành khỏi môi trường phát triển; tắt IDE/phần mềm không cần trong phép thử A/B có kiểm soát, không giết các dịch vụ không rõ vai trò.
3. Tách lifecycle inference phục vụ exam khỏi preview phục vụ người xem. Preview có lease/subscriber và grace period; hết người xem thì dừng encode/render, nhưng không dừng kiểm tra vị trí/che mắt đang cần cho phiên.
4. Giới hạn cadence/resolution/JPEG quality preview độc lập với cadence inference. Tránh tính/encode nhiều lần cùng frame cho nhiều subscriber; không giữ queue frame cũ không giới hạn.
5. Kiểm tra model nạp trùng, allocation/buffer dư và vòng đời worker. Chỉ áp dụng lazy load nếu có bước warm-up trước phiên và timeout; không chuyển độ trễ sang lượt đọc đầu tiên.
6. Chỉ tách CV/STT thành process riêng khi trace chứng minh cần cách ly; việc tách process tự nó không giảm RAM. Kiểm tra đường CUDA thực tế bằng profiling, không kết luận từ sự hiện diện của tên provider.

Nghiệm thu: so sánh trước/sau trong cùng điều kiện, có cold/warm run và nhiều lượt; tài nguyên giảm mà readiness/STT không suy giảm, camera vẫn phục vụ exam khi observer đóng preview. Không dùng tắt swap hoặc ép xung làm bản sửa mặc định.

## 6. Sửa K06: ảnh, font và lỗi frontend

Hai JPEG hiện có trên server và HTTP trả 200. HTML đã preload cả hai; không thêm preload trùng. Ảnh gốc tổng khoảng 530 KB theo byte, mỗi ảnh giải nén RGBA khoảng 6 MiB. Bản `.optimized.jpg` cùng độ phân giải giảm transfer nhưng không giảm tương ứng bộ nhớ ảnh decode.

Kế hoạch tại [chart.js](../services/assistant_controller/display/chart.js), [index.html](../services/assistant_controller/display/index.html), [chart.css](../services/assistant_controller/display/chart.css):

- Thay `catch` rỗng ở WebSocket bằng logging có rate limit: command type/sequence, scene/build, exception; không ghi thừa thông tin bệnh nhân.
- Thu `error`, `unhandledrejection`, `img.onerror`, decode duration, `naturalWidth`, trạng thái font và document visibility.
- Giữ DOM/ảnh ổn định khi phù hợp; đợi decode với timeout trước scene cần ảnh, có fallback và thông báo vận hành. Không im lặng bắt đầu bước đo nếu font optotype bắt buộc chưa sẵn sàng.
- Self-host font UI để hoạt động offline; font Optician Sans hiện đã local. Tách điều kiện font bắt buộc cho phép đo với font trang trí để không block không cần thiết.
- Đo thời gian decode ảnh, long task, layout và paint khi chuyển cảnh; tối ưu cập nhật DOM/CSS effect tại điểm nghẽn đã đo được.
- Thêm timeout hữu hạn cho `loadDisplayConfig()` trước `connectAc()` để fetch bị treo không chặn kết nối WebSocket vô hạn; báo lỗi và retry có backoff, giữ nguyên nội dung cấu hình do người vận hành thiết lập.

Nghiệm thu: cold cache, ảnh 404/timeout/decode lỗi, font offline, JS handler lỗi, resize và chuyển cảnh nhanh đều có kết quả rõ ràng; không giữ scene trước mà không báo lỗi. Kiểm thử ảnh bằng browser thật, không chỉ GET 200.

## 7. Sửa K08: event loop và endpoint quản trị

Async `get_pipeline_settings` trong [display_client.py](../services/assistant_controller/src/ac/display_client.py) gọi `_scan_hardware()` đồng bộ, chung server WebSocket/static. Đây là rủi ro blocking cần đo, chưa chứng minh đang gây nghẽn. Không quy tất cả face operation thành blocking: nhiều tác vụ dài đã dùng thread pool.

Thêm event-loop lag measurement; cache hardware discovery, chạy blocking IO trong worker có giới hạn concurrency/timeout. Tránh UI poll endpoint quét hardware liên tục. Timeout chờ thread không chắc dừng thao tác native đang chạy: phải tránh tạo thêm tác vụ vô hạn khi thiết bị treo. Kiểm thử device probe cố tình chậm trong khi chart vẫn nhận command và static asset.

## 8. Trình tự triển khai

| Bước | Nội dung | Điều kiện hoàn tất |
|---|---|---|
| 1 | Build ID, scene/command timeline, frontend error, event-loop và resource metrics | Xác định được phiên bản, scene và mốc trễ của đúng kiosk |
| 2 | K01–K02: ACK, window, epoch/sequence, deadline, reconnect | Đạt test delay/disconnect/observer/cancel, không bắt đầu nghe sớm |
| 3 | Kiosk readiness, version handshake, watchdog và release/rollback | Cold boot/deploy/reconnect ổn định, không reload giữa lượt |
| 4 | Preview/RAM/endpoint blocking và asset readiness | A/B cải thiện có số đo, không giảm tính đúng phép đo |
| 5 | Dọn handler/asset legacy đã chứng minh không dùng | Không còn caller hợp lệ; regression flow qua đầy đủ |

Có thể chuẩn bị code, đo tài nguyên và kiểm thử giao thức qua SSH. Nghiệm thu độ mượt và độ trễ hiển thị thực tế cần TV kết nối; không dùng kết quả headless để xác nhận đã hết lag trên TV.

## 9. Kịch bản nghiệm thu và rollback

Mỗi phiên nghiệm thu ghi cùng timeline: CPU từng lõi/process, PSS/swap, GR3D/EMC/nhiệt độ, inference, event-loop lag, enqueue/send/receive/render-ready, asset decode, bắt đầu STT và deadline. Đối chiếu clock đúng miền; timestamp ở hai browser không được trừ trực tiếp.

- TV và observer chạy đồng thời: xác định độ trễ từng phía, observer chậm không giữ cửa sổ nghe.
- Cold boot/cold cache và warm run: đúng build, font/ảnh tải thành công; ghi thời gian sẵn sàng và độ trễ chuyển cảnh.
- Delay render 0,5–2 giây: không mất thời gian trả lời trước khi kiosk-ready.
- Mất mạng/reconnect/backend restart: không tăng lại countdown, không replay window hết hạn, không nhận ACK cũ.
- Ảnh/font hỏng hoặc JS exception: có log/fallback; bước cần asset bắt buộc không tiếp tục âm thầm.
- Đóng preview khi exam đang cần camera: preview ngừng nhưng readiness vẫn hoạt động.
- Probe hardware chậm: event loop vẫn đáp ứng, worker/queue không tăng vô hạn.
- Reboot và mất/kết nối lại màn hình: kiosk phục hồi kết nối và scene hiện hành, không phát lại command hết hạn.

Mục tiêu ban đầu đề xuất: command send→render-ready p95 dưới 100 ms trong điều kiện vận hành đã chốt. Đây chưa phải số đo đạt được; không dùng RTT/RAF để thay phép đo scanout TV. Tiêu chí bắt buộc vẫn là không mở cửa sổ nghe sớm, không lệnh/ACK cũ và không lỗi UI bị giấu.

Trước triển khai lưu release/config hiện hành và cách khôi phục launcher. Chuyển phiên về idle rồi triển khai; nếu giao thức không tương thích, rollback backend/frontend cùng nhau. Không chỉ đổi riêng JS khi backend đã dùng contract ACK mới. Giữ bằng chứng trước/sau để phân biệt lỗi cũ, lỗi mới và thay đổi môi trường.
