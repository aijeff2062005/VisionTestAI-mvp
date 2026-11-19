"""Network installation settings exposed by the preview page API."""

from __future__ import annotations

import asyncio
from io import BytesIO
import httpx
import yaml
from fastapi.testclient import TestClient
from PIL import Image

from ac.config import AppConfig
from ac.display_client import DisplayHub, create_display_app


def test_instruction_image_upload_persists_and_reset_uses_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AC_INSTRUCTION_IMAGE_DIR", str(tmp_path / "instruction-images"))
    hub = DisplayHub()
    client = TestClient(create_display_app(hub, cfg=AppConfig()))
    original = client.get("/api/instruction-images").json()["images"]
    assert original["cover_right"]["custom"] is False
    assert client.put("/api/instruction-images/cover_right", content=b"not an image").status_code == 400

    image = BytesIO()
    Image.new("RGB", (40, 30), "blue").save(image, format="PNG")
    with client.websocket_connect("/ws/display") as ws:
        ws.receive_json()  # input mode
        ws.receive_json()  # current display scene
        response = client.put("/api/instruction-images/cover_right", content=image.getvalue())
        update = ws.receive_json()
    assert response.status_code == 200
    custom = response.json()["images"]["cover_right"]
    assert update["type"] == "instruction_images"
    assert update["images"]["cover_right"] == custom
    assert custom["custom"] is True
    assert client.get(custom["url"]).headers["content-type"] == "image/webp"
    assert hub.last_command["type"] != "instruction_images"

    reloaded = TestClient(create_display_app(DisplayHub(), cfg=AppConfig()))
    assert reloaded.get("/api/instruction-images").json()["images"]["cover_right"] == custom
    reset = client.delete("/api/instruction-images/cover_right")
    assert reset.status_code == 200
    assert reset.json()["images"]["cover_right"] == original["cover_right"]


def test_results_checkpoint_survives_next_display_command() -> None:
    hub = DisplayHub()
    asyncio.run(hub.broadcast({"type": "results", "session_id": "exam-1"}))
    result = hub.last_result
    asyncio.run(hub.broadcast({"type": "clear"}))
    assert result is not None
    assert hub.last_result == result


def test_slow_display_client_is_closed_and_latest_scene_remains_available() -> None:
    class SlowSocket:
        client = "kiosk"

        def __init__(self) -> None:
            self.closed = False

        async def send_json(self, _command: dict) -> None:
            raise TimeoutError("stalled browser")

        async def close(self, *, code: int) -> None:
            assert code == 1011
            self.closed = True

    hub = DisplayHub()
    ws = SlowSocket()
    hub._clients.add(ws)
    asyncio.run(hub.broadcast({"type": "show_message", "scene": "cover_left"}))
    assert ws.closed
    assert ws not in hub._clients
    assert hub.last_command["scene"] == "cover_left"
    assert hub.last_command["_display_revision"] == 1


def test_kiosk_paint_ack_reports_current_scene() -> None:
    hub = DisplayHub()
    client = TestClient(create_display_app(hub, cfg=AppConfig()), client=("127.0.0.1", 50000))
    with client.websocket_connect("/ws/display", headers={"host": "127.0.0.1:8088"}) as ws:
        ws.receive_json()  # input mode
        ws.receive_json()  # initial scene
        assert client.post("/api/display/command", json={"type": "show_message", "scene": "cover_left"}).status_code == 200
        cmd = ws.receive_json()
        ws.send_json({
            "type": "display_applied",
            "boot_id": cmd["_display_boot_id"],
            "revision": cmd["_display_revision"],
            "scene": cmd["scene"],
            "image_ready": True,
        })
        health = client.get("/api/display/health").json()
        assert health["scene"] == "cover_left"
        assert health["last_kiosk_applied"]["revision"] == cmd["_display_revision"]
        assert health["last_kiosk_applied"]["scene"] == "cover_left"


def test_settings_expose_all_three_devices(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    cfg = AppConfig()
    cfg.mqtt.host = "100.113.176.38"
    cfg.mqtt.port = 1883
    cfg.hospital.base_url = "https://hospital.example.ts.net"
    cfg.media.base_url = "http://100.113.176.38:9010"
    cfg.face_vectordb.base_url = "http://100.113.176.38:8100"
    cfg.bridges.face.host = "192.168.1.18"
    cfg.bridges.face.port = 80
    cfg.bridges.face.callback_host = "192.168.1.125"
    cfg.bridges.face.callback_port = 7788
    monkeypatch.setenv("JETSON_TAILNET_HOST", "100.64.238.95")
    monkeypatch.setenv("JETSON_PUBLIC_URL", "https://jetson.example.ts.net")

    config_path = tmp_path / "clinic.yaml"
    config_path.write_text("station_id: test\n", encoding="utf-8")
    app = create_display_app(DisplayHub(), cfg=cfg, config_path=config_path)
    data = TestClient(app).get("/api/settings").json()["settings"]

    assert data["vps_ip"] == "100.113.176.38"
    assert data["frappe_url"] == "https://hospital.example.ts.net"
    assert data["vps_media_url"] == "http://100.113.176.38:9010"
    assert data["jetson_lan_url"] == "http://192.168.1.125:8088"
    assert data["jetson_tailnet_ip"] == "100.64.238.95"
    assert data["jetson_public_url"] == "https://jetson.example.ts.net"
    assert data["face_device_url"] == "http://192.168.1.18:80"
    assert data["letter_uncertain_threshold"] == 0.45
    assert data["letter_accept_threshold"] == 0.75


def test_save_model_a_threshold_band_updates_runtime_and_yaml(tmp_path) -> None:  # noqa: ANN001
    cfg = AppConfig()
    config_path = tmp_path / "clinic.yaml"
    config_path.write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    app = create_display_app(DisplayHub(), cfg=cfg, config_path=config_path)

    response = TestClient(app).put(
        "/api/settings",
        json={
            "letter_chunk_seconds": 4.0,
            "tablet_chunk_seconds": 12.0,
            "letter_uncertain_threshold": 0.42,
            "letter_accept_threshold": 0.78,
            "max_letter_replacements": 1,
            "left_eye_start_easier_steps": 2,
        },
    )

    assert response.status_code == 200
    assert cfg.protocol.letter_uncertain_threshold == 0.42
    assert cfg.protocol.letter_chunk_seconds == 4.0
    assert cfg.protocol.tablet_chunk_seconds == 12.0
    assert cfg.protocol.letter_accept_threshold == 0.78
    assert cfg.protocol.left_eye_start_easier_steps == 2
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["protocol"]["letter_uncertain_threshold"] == 0.42
    assert saved["protocol"]["tablet_chunk_seconds"] == 12.0
    assert saved["protocol"]["letter_accept_threshold"] == 0.78


def test_input_mode_is_exposed_and_saved_for_restart(tmp_path) -> None:  # noqa: ANN001
    cfg = AppConfig()
    config_path = tmp_path / "clinic.yaml"
    config_path.write_text("ui:\n  patient_flow: speaker_v1\n  input_mode: speak\n", encoding="utf-8")
    client = TestClient(create_display_app(DisplayHub(), cfg=cfg, config_path=config_path))

    assert client.get("/api/settings").json()["settings"]["input_mode"] == "speak"
    assert client.get("/api/control/mode").json()["input_mode"] == "speak"
    response = client.put("/api/settings", json={"input_mode": "tablet"})
    assert response.status_code == 200
    assert response.json()["restart_required"] is True
    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["ui"]["input_mode"] == "tablet"
    assert client.put("/api/settings", json={"input_mode": "both"}).status_code == 400
    assert client.put("/api/settings", json={"input_mode": "invalid"}).status_code == 400
    control_html = client.get("/control").text
    assert "real-integration.js" in control_html
    assert 'class="screen active welcome"' in control_html
    assert "screen-welcome.png" not in control_html
    assert "/control-static/trung_vuong_logo.svg" in control_html
    assert client.get("/control-static/trung_vuong_logo.svg").status_code == 200
    assert "Roboto-VF.ttf" in control_html
    assert client.get("/control-static/fonts/Roboto-VF.ttf").status_code == 200
    assert "Nguyễn Văn A" not in control_html
    assert "class=\"tablet\"" not in control_html


def test_control_websocket_sends_runtime_mode_before_display_state() -> None:
    cfg = AppConfig()
    cfg.ui.input_mode = "tablet"
    app = create_display_app(DisplayHub(), cfg=cfg)
    with TestClient(app).websocket_connect("/ws/display") as ws:
        assert ws.receive_json() == {"type": "input_mode", "input_mode": "tablet"}
        assert ws.receive_json() == {
            "type": "show_message",
            "mode": "idle",
            "scene": "face",
            "text_vi": "Nhìn vào máy nhận diện khuôn mặt.",
            "exam_mode": True,
        }
    script = TestClient(app).get("/control-static/real-integration.js")
    assert script.status_code == 200
    assert script.headers["cache-control"] == "no-store"


def test_control_websocket_accepts_mode_choice_for_current_session() -> None:
    cfg = AppConfig()
    hub = DisplayHub()
    app = create_display_app(hub, cfg=cfg)
    hub.begin_input_mode_choice("speak")
    with TestClient(app).websocket_connect("/ws/display") as ws:
        assert ws.receive_json()["input_mode"] == "speak"
        ws.receive_json()  # current display state
        ws.send_json({"type": "ui_event", "action": "select_input_mode", "payload": {"mode": "tablet"}})
        assert ws.receive_json() == {"type": "input_mode", "input_mode": "tablet"}
    assert hub.input_mode == "tablet"
    assert hub.wait_ui_event({"select_input_mode"}, timeout=0.01) is not None
    assert not hub.choose_input_mode("speak")


def test_control_rejects_late_answer_from_previous_letter() -> None:
    hub = DisplayHub()
    app = create_display_app(hub, cfg=AppConfig())
    hub.active_letter_window_id = "current"
    with TestClient(app).websocket_connect("/ws/display") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "ui_event", "action": "speak_letter", "payload": {"letter": "K", "window_id": "previous"}})
        ws.send_json({"type": "ui_event", "action": "speak_letter", "payload": {"letter": "N", "window_id": "current"}})
    event = hub.wait_ui_event({"speak_letter"}, timeout=0.01)
    assert event is not None and event["payload"]["letter"] == "N"
    assert hub.wait_ui_event({"speak_letter"}, timeout=0.01) is None


def test_remote_chart_cannot_overwrite_patient_display_geometry() -> None:
    cfg = AppConfig()
    hub = DisplayHub()
    app = create_display_app(hub, cfg=cfg)
    with TestClient(app).websocket_connect("/ws/display", headers={"host": "tablet.example"}) as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "display_metrics", "screen_width": 1536, "screen_height": 864})
    assert hub.display_metrics == {}


def test_local_chart_supplies_patient_display_geometry() -> None:
    cfg = AppConfig()
    hub = DisplayHub()
    app = create_display_app(hub, cfg=cfg)
    with TestClient(app).websocket_connect("/ws/display", headers={"host": "127.0.0.1:8088"}) as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "display_metrics", "screen_width": 3840, "screen_height": 2160})
        assert ws.receive_json()["type"] == "display_config"
    assert hub.display_metrics["source"] == "jetson_chart"
    assert hub.display_metrics["screen_width"] == 3840


def test_rejects_inverted_model_a_threshold_band(tmp_path) -> None:  # noqa: ANN001
    cfg = AppConfig()
    config_path = tmp_path / "clinic.yaml"
    config_path.write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    app = create_display_app(DisplayHub(), cfg=cfg, config_path=config_path)

    response = TestClient(app).put(
        "/api/settings",
        json={
            "letter_uncertain_threshold": 0.80,
            "letter_accept_threshold": 0.75,
        },
    )

    assert response.status_code == 400


def test_vps_connection_check(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("ac.display_client._tcp_reachable", lambda *_args: True)

    def get(_self, url, **_kwargs):  # noqa: ANN001
        return httpx.Response(
            200,
            json={"message": "pong"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.Client, "get", get)
    app = create_display_app(DisplayHub(), cfg=AppConfig())
    response = TestClient(app).post(
        "/api/settings/vps/test",
        json={
            "vps_ip": "vision-k8s-mqtt.primetek.ai",
            "vps_mqtt_port": 8884,
            "frappe_url": "https://hospital.example.ts.net/",
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_save_vps_updates_yaml_and_restart_environment(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    cfg = AppConfig()
    cfg.mqtt.host = "100.1.1.1"
    cfg.hospital.base_url = "https://old.example.ts.net"
    config_path = tmp_path / "clinic.yaml"
    config_path.write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    env_path = tmp_path / "lab.env"
    env_path.write_text(
        "VPS_TAILNET_HOST=100.1.1.1\n"
        "VPS_HOST=100.1.1.1\n"
        "HOSPITAL_BASE_URL=https://old.example.ts.net\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AC_LAB_ENV_FILE", str(env_path))
    monkeypatch.delenv("REPLACE_AC", raising=False)

    app = create_display_app(DisplayHub(), cfg=cfg, config_path=config_path)
    response = TestClient(app).put(
        "/api/settings",
        json={
            "vps_ip": "100.2.2.2",
            "vps_mqtt_port": 1884,
            "frappe_url": "https://new.example.ts.net/",
        },
    )
    data = response.json()
    assert response.status_code == 200
    assert data["restart_required"] is True

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["mqtt"]["host"] == "100.2.2.2"
    assert saved["mqtt"]["port"] == 1884
    assert saved["hospital"]["base_url"] == "https://new.example.ts.net"
    assert saved["media"]["base_url"] == "http://192.168.1.78:9010"
    assert saved["face_vectordb"]["base_url"] == "http://127.0.0.1:8100"

    env_text = env_path.read_text(encoding="utf-8")
    assert "VPS_TAILNET_HOST=100.2.2.2" in env_text
    assert "MQTT_PORT=1884" in env_text
    assert "HOSPITAL_BASE_URL=https://new.example.ts.net" in env_text
