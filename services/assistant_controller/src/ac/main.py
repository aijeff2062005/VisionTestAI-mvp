"""VisionTestAI Assistant Controller entrypoint."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
import uuid
from pathlib import Path

from pydantic import HttpUrl

from ac.audio_player import AudioPlayer
from ac.config import ROOT, load_config
from ac.display_client import DisplayClient, DisplayHub, run_display_server
from ac.dmn_engine import DmnEngine
from ac.face_client import build_face_client
from ac.face_sync import sync_vectordb_to_device
from ac.face_gallery_loop import TodayFaceSyncLoop
from ac.walk_in import FaceWalkInLoop
from ac.hospital_client import HospitalClient
from ac.http_callback import HttpCallbackClient
from ac.media_client import MediaClient
from ac.models import ExamType, EyesMode, SessionCancel, SessionStart, SessionState, SessionStatus
from ac.mqtt_gateway import MqttGateway
from ac.orchestrator import Orchestrator
from ac.readiness_bridge import (
    ExclusiveInputSttBridge,
    SloanSttBridge,
    UiSttBridge,
    build_readiness_bridge,
    build_stt_bridge,
)
from ac.session_manager import SessionManager
from ac.vector_face_client import build_vector_face_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("ac.main")
logging.getLogger("httpx").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VisionTestAI Assistant Controller")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to configs/default.yaml",
    )
    parser.add_argument("--no-mqtt", action="store_true", help="Skip MQTT (display-only / test)")
    parser.add_argument(
        "--mqtt-optional",
        action="store_true",
        help="Continue if MQTT broker is unreachable (chart/audio still run)",
    )
    parser.add_argument("--no-display-server", action="store_true", help="Do not start chart HTTP server")
    parser.add_argument(
        "--demo-session",
        action="store_true",
        help="Auto-start one local exam session after boot (full demo without MQTT pub)",
    )
    parser.add_argument(
        "--demo-callback",
        default=None,
        help="callback_url used with --demo-session (default: hospital.base_url/api/vision/results)",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    logger.info("Station=%s root=%s", cfg.station_id, ROOT)
    if not args.demo_callback:
        args.demo_callback = HospitalClient(cfg.hospital.base_url).results_callback_url()

    sessions = SessionManager(cfg.station_id, cfg.resolve(cfg.paths.journals))
    dmn = DmnEngine(cfg.resolve(cfg.paths.dmn))
    hub = DisplayHub()
    display = DisplayClient(hub)
    audio_output = (getattr(getattr(cfg, "audio", None), "output", None) or "sounddevice").strip().lower()
    if audio_output in ("device", "sounddevice", "alsa", "pulse"):
        audio_output = "sounddevice"
    elif audio_output in ("both", "all"):
        audio_output = "both"
    audio = AudioPlayer(
        cfg.resolve(cfg.paths.scenarios),
        output=audio_output,
        output_device=getattr(cfg.audio, "output_device", "") or "",
        prompts_dir=cfg.resolve(getattr(cfg.audio, "prompts_dir", "display/prompts/vi")),
        play_browser=lambda url, duration: display.play_audio(url, duration_seconds=duration),
        stop_browser=display.stop_audio,
    )
    http = HttpCallbackClient(cfg.http.timeout_seconds)

    se_cfg = cfg.resolve(cfg.bridges.smarteyes_config)
    readiness = build_readiness_bridge(
        cfg.bridges.readiness,
        cfg.resolve(cfg.bridges.smarteyes_root),
        config_path=se_cfg if se_cfg.is_file() else None,
        source=cfg.bridges.smarteyes_source,
        show_window=cfg.bridges.smarteyes_show_window,
        strict=cfg.bridges.smarteyes_strict,
        preview_enabled=cfg.bridges.smarteyes_preview_enabled,
    )
    audio_input = (getattr(getattr(cfg, "audio", None), "input", None) or "device").strip().lower()
    hub.audio_input = audio_input
    hub.audio_output = audio_output
    hub.audio_device_label = (
        getattr(cfg.audio, "input_device", None) or getattr(cfg.audio, "output_device", None) or ""
    )
    chart_audio_url = f"http://127.0.0.1:{int(cfg.display.port)}/audio.raw"
    input_mode = cfg.ui.input_mode if cfg.bridges.stt == "sloan" else cfg.bridges.stt
    stt = build_stt_bridge(
        cfg.bridges.stt,
        cfg.resolve(cfg.bridges.sloan_root),
        cfg.protocol.letter_uncertain_threshold,
        audio_url=cfg.bridges.sloan_audio_url,
        audio_sample_rate=cfg.bridges.sloan_audio_sample_rate,
        energy_threshold=cfg.bridges.sloan_energy_threshold,
        silence_duration=cfg.bridges.sloan_silence_duration,
        min_margin=cfg.bridges.sloan_min_margin,
        min_voiced_seconds=cfg.bridges.sloan_min_voiced_seconds,
        vad_padding_seconds=cfg.bridges.sloan_vad_padding_seconds,
        class_confidence_thresholds=cfg.bridges.sloan_class_confidence_thresholds,
        chart_audio_url=chart_audio_url,
        mic_hub=hub,
        input_device=getattr(cfg.audio, "input_device", "") or "",
    )
    if isinstance(stt, SloanSttBridge) and hasattr(
        readiness, "set_stt_inference_active"
    ):
        stt.inference_activity_callback = readiness.set_stt_inference_active
    if cfg.bridges.stt == "sloan":
        stt = ExclusiveInputSttBridge(stt, UiSttBridge())
    if isinstance(stt, (UiSttBridge, ExclusiveInputSttBridge)):
        stt.bind(hub)
    face = build_face_client(
        cfg.bridges.face.mode,
        host=cfg.bridges.face.host,
        password=cfg.bridges.face.password,
        port=cfg.bridges.face.port,
        poll_interval_seconds=cfg.bridges.face.poll_interval_seconds,
        accept_recent_seconds=cfg.bridges.face.accept_recent_seconds,
        live_events_url=cfg.bridges.face.live_events_url,
        callback_host=cfg.bridges.face.callback_host,
        callback_port=cfg.bridges.face.callback_port,
    )
    face_vector = build_vector_face_client(cfg.face_vectordb)
    media = MediaClient(
        cfg.media.base_url,
        token=cfg.media.token,
        timeout_seconds=cfg.media.timeout_seconds,
        station_id=cfg.station_id,
        enabled=cfg.media.enabled,
    )
    hospital = HospitalClient(
        cfg.hospital.base_url,
        timeout_seconds=cfg.hospital.timeout_seconds,
        api_key=cfg.hospital.api_key,
        api_secret=cfg.hospital.api_secret,
    )
    logger.info(
        "Bridges readiness=%s stt=%s audio_input=%s audio_output=%s chart_mic=%s face=%s(enabled=%s host=%s) vectordb=%s(enabled=%s mode=%s) media=%s",
        cfg.bridges.readiness,
        input_mode,
        audio_input,
        audio_output,
        chart_audio_url,
        cfg.bridges.face.mode,
        face.enabled,
        cfg.bridges.face.host if face.enabled else "-",
        cfg.face_vectordb.mode,
        cfg.face_vectordb.enabled and face_vector.enabled,
        cfg.face_vectordb.mode if cfg.face_vectordb.enabled else "off",
        "on" if media.enabled else "off",
    )

    # The today-face loop already performs an immediate sync in its own thread.
    # Doing the same network/device job here delayed the chart and Face ID
    # listener at every boot, sometimes for tens of seconds.
    if cfg.face_vectordb.enabled and cfg.face_vectordb.sync_on_startup and not cfg.face_vectordb.sync_today_appointments_only:
        if face_vector.enabled:
            logger.info("Startup: sync VectorDB faces → AiFace panel for on-device verify")
            sync_res = sync_vectordb_to_device(
                face_vector,
                face,
                max_faces=cfg.face_vectordb.max_faces,
                device_face_backupnum=cfg.face_vectordb.device_face_backupnum,
                media=media,
            )
        else:
            sync_res = None
        if sync_res is not None:
            logger.info("Startup face sync: %s", sync_res.as_dict())

    try:
        face.ensure_bs_server(
            cfg.bridges.face.callback_host or None,
            cfg.bridges.face.callback_port,
        )
    except Exception:  # noqa: BLE001
        logger.warning("AiFace BS server check failed", exc_info=True)

    mqtt: MqttGateway | None = None
    orch: Orchestrator | None = None
    walk_in_ref: dict[str, FaceWalkInLoop | None] = {"loop": None}

    def publish_status(status: SessionStatus) -> None:
        if mqtt:
            mqtt.publish_status(status)
        else:
            logger.info("STATUS %s", status.model_dump(mode="json"))

    def on_start(payload: SessionStart) -> None:
        assert orch is not None
        prematch = None
        loop = walk_in_ref.get("loop")
        if payload.auto_enter_test and loop is not None:
            prematch = loop.take_prematch()
        session, err = sessions.start(payload)
        if err == "busy":
            publish_status(
                SessionStatus(
                    session_id=payload.session_id,
                    station_id=cfg.station_id,
                    state=SessionState.FAILED,
                    step_id="busy",
                    message_vi="Trạm đang bận",
                    error_code="busy",
                    queue_number=payload.queue_number,
                )
            )
            return
        assert session is not None
        publish_status(
            SessionStatus(
                session_id=session.start.session_id,
                station_id=cfg.station_id,
                state=SessionState.ACCEPTED,
                step_id="accepted",
                message_vi="Đã nhận phiên đo",
                queue_number=session.start.queue_number,
            )
        )
        orch.start_session_async(session, prematch=prematch)

    def on_cancel(payload: SessionCancel) -> None:
        assert orch is not None
        logger.info(
            "Cancel requested session_id=%s reason=%s",
            payload.session_id,
            payload.reason,
        )
        done = sessions.cancel(payload.session_id, payload.reason)
        sid = (done.start.session_id if done else payload.session_id)
        if done:
            orch.request_stop()
            # Keep the cancellation reason in logs/status only. Both patient-facing
            # screens return to their normal home state without a stop message.
            orch.display.show_station_home()
        else:
            active = sessions.active
            if active is not None and active.state not in (
                SessionState.COMPLETED,
                SessionState.FAILED,
                SessionState.CANCELLED,
            ) and active.start.session_id != payload.session_id:
                logger.warning(
                    "Cancel ignored: session_id=%s does not match active=%s",
                    payload.session_id,
                    active.start.session_id,
                )
                return
            logger.info(
                "No active assistant session for cancel session_id=%s; resetting patient displays",
                payload.session_id,
            )
            # Frappe can cancel before this station has accepted/created its
            # session. Still return both screens home. A stale cancel for a
            # different active session is ignored above.
            orch.display.show_station_home()
            return
        publish_status(
            SessionStatus(
                session_id=sid,
                station_id=cfg.station_id,
                state=SessionState.CANCELLED,
                step_id="cancel",
                message_vi=None,
            )
        )

    orch = Orchestrator(
        cfg=cfg,
        sessions=sessions,
        dmn=dmn,
        display=display,
        audio=audio,
        readiness=readiness,
        stt=stt,
        http=http,
        publish_status=publish_status,
        face=face,
        face_vector=face_vector,
        media=media,
    )

    if not args.no_display_server:
        try:
            run_display_server(
                hub,
                cfg.display.host,
                cfg.display.port,
                face=face,
                face_vector=face_vector,
                media=media,
                hospital=hospital,
                face_vectordb_cfg=cfg.face_vectordb,
                readiness=readiness,
                audio_input=audio_input,
                cfg=cfg,
                config_path=args.config,
                orchestrator=orch,
                audio_player=audio,
                stt_bridge=stt,
            )
        except OSError as exc:
            logger.error("%s", exc)
            return 1
        logger.info(
            "Chart display http://%s:%s/  camera preview http://%s:%s/preview  "
            "(face sync/wipe/identify: GET /api/face/health, "
            "POST /api/face/sync_today, /api/face/wipe_gallery)",
            cfg.display.host,
            cfg.display.port,
            cfg.display.host,
            cfg.display.port,
        )
        time.sleep(0.2)

    if bool(cfg.bridges.smarteyes_preview_enabled):
        try:
            readiness.set_preview_enabled(True)
            logger.info("SmartEyes camera started for /preview (smarteyes_preview_enabled)")
        except Exception:  # noqa: BLE001
            logger.exception("SmartEyes camera failed to start — /preview will wait")
    else:
        # Always-on CV+MJPEG starves Jetson alongside Sloan STT.
        logger.info(
            "SmartEyes camera idle — open /preview and toggle ON, or start a session"
        )

    if not args.no_mqtt:
        mqtt = MqttGateway(
            host=cfg.mqtt.host,
            port=cfg.mqtt.port,
            station_id=cfg.station_id,
            username=cfg.mqtt.username,
            password=cfg.mqtt.password,
            tls=cfg.mqtt.tls,
            tls_ca_certs=cfg.mqtt.tls_ca_certs,
            keepalive=cfg.mqtt.keepalive,
            on_start=on_start,
            on_cancel=on_cancel,
        )
        try:
            mqtt.start()
        except OSError as exc:
            logger.error(
                "MQTT broker unreachable at %s:%s (%s). "
                "Start Mosquitto, then re-run. Examples:\n"
                "  brew services start mosquitto\n"
                "  docker run --rm -p 1883:1883 eclipse-mosquitto:2\n"
                "Or run:  python -m ac.main --demo-session --mqtt-optional",
                cfg.mqtt.host,
                cfg.mqtt.port,
                exc,
            )
            if not args.mqtt_optional and not args.demo_session:
                return 1
            mqtt = None
            logger.warning("Continuing without MQTT")
        except Exception:  # noqa: BLE001
            logger.exception("MQTT connect failed")
            if not args.mqtt_optional and not args.demo_session:
                return 1
            mqtt = None
            logger.warning("Continuing without MQTT")
    else:
        logger.warning("Running without MQTT (--no-mqtt)")

    if args.demo_session:
        demo = SessionStart(
            session_id=str(uuid.uuid4()),
            patient_id="PENDING_FACE",
            queue_number="DEMO",
            exam_type=ExamType.DISTANCE_ACUITY_5M,
            eyes=EyesMode.BOTH,
            callback_url=HttpUrl(args.demo_callback),
            correlation_id=str(uuid.uuid4()),
            locale="vi-VN",
        )
        logger.info("Starting --demo-session id=%s", demo.session_id)
        time.sleep(0.5)
        on_start(demo)

    face_loop: TodayFaceSyncLoop | None = None
    walk_in: FaceWalkInLoop | None = None
    if cfg.face_vectordb.enabled and cfg.face_vectordb.sync_today_appointments_only:
        face_loop = TodayFaceSyncLoop(
            hospital=hospital,
            face=face,
            media=media,
            cfg=cfg.face_vectordb,
        )
        face_loop.start()
        if cfg.face_vectordb.auto_start_on_face and face.enabled:
            walk_in = FaceWalkInLoop(
                hospital=hospital,
                face=face,
                sessions=sessions,
                display=display,
                cfg=cfg.face_vectordb,
                on_start=on_start,
                callback_url=str(args.demo_callback),
            )
            walk_in_ref["loop"] = walk_in
            walk_in.start()

    stop = {"flag": False}

    def _sig(_signum: int, _frame: object) -> None:
        stop["flag"] = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    logger.info("AC running. Ctrl+C to stop.")
    while not stop["flag"]:
        time.sleep(0.3)

    logger.info("Shutting down…")
    if walk_in:
        walk_in.stop()
    if face_loop:
        face_loop.stop()
    if orch:
        orch.request_stop()
    close_stt = getattr(stt, "close", None)
    if callable(close_stt):
        close_stt()
    try:
        readiness.stop(force=True)
    except TypeError:
        readiness.stop()
    if mqtt:
        mqtt.stop()
    close_face = getattr(face, "close", None)
    if callable(close_face):
        close_face()
    return 0


if __name__ == "__main__":
    sys.exit(main())
