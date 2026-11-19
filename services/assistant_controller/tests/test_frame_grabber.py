"""Camera processing must wait for new frames instead of reusing one frame."""

import queue
import threading
from types import SimpleNamespace

from ac.readiness_bridge import RealtimeFrameGrabber, SmartEyesReadinessBridge


def test_read_latest_returns_each_camera_frame_once() -> None:
    class Capture:
        def __init__(self) -> None:
            self.frames = queue.Queue()

        def read(self):
            try:
                return True, self.frames.get(timeout=0.02)
            except queue.Empty:
                return False, None

        def release(self) -> None:
            pass

    cap = Capture()
    grabber = RealtimeFrameGrabber(cap)
    try:
        first = SimpleNamespace(size=1)
        cap.frames.put(first)
        assert grabber.read_latest(timeout=0.2) == (True, first)
        assert grabber.read_latest(timeout=0.04) == (False, None)
        second = SimpleNamespace(size=1)
        cap.frames.put(second)
        assert grabber.read_latest(timeout=0.2) == (True, second)
    finally:
        grabber.release()


def test_preview_encodes_native_frame_without_resize() -> None:
    frame = SimpleNamespace(shape=(720, 1280, 3))
    encoded = []

    class FakeCv2:
        IMWRITE_JPEG_QUALITY = 1

        def imencode(self, ext, value, options):
            encoded.append((ext, value, options))
            return True, SimpleNamespace(tobytes=lambda: b"jpeg")

    bridge = object.__new__(SmartEyesReadinessBridge)
    bridge._cv2 = FakeCv2()
    bridge._lock = threading.Lock()
    bridge._jpeg = None
    bridge._jpeg_seq = 0
    bridge._publish_jpeg(frame)

    assert encoded == [(".jpg", frame, [1, 85])]
    assert bridge.latest_jpeg_seq() == (b"jpeg", 1)
