"""Configuration loader for Assistant Controller."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings


ROOT = Path(__file__).resolve().parents[2]


class MqttConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 1883
    username: str = ""
    password: str = ""
    keepalive: int = 60
    tls: bool = False
    tls_ca_certs: str | None = None


class HttpConfig(BaseModel):
    timeout_seconds: float = 10.0


class DisplayConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8088
    # Physical chart sizing. "auto" derives CSS px/mm from the chart browser's
    # reported screen dimensions plus diagonal_inches; "manual" uses px_per_mm.
    calibration_mode: str = "auto"  # auto | manual
    diagonal_inches: float = 32.0
    px_per_mm: float = 5.42
    calibration_target_mm: float = 100.0
    calibrated_at: str = ""


class ProtocolConfig(BaseModel):
    distance_m: float = 5.0
    passes_per_eye: int = 3  # legacy; staircase uses max_rows_per_eye
    letters_per_row: int = 5
    # Clinic / Snellen top-down: start large, pass a whole line, then go smaller.
    # On first failed line N, stop that eye — lines above (1..N-1) were read well.
    snellen_stop_on_fail: bool = True
    # Legacy adaptive staircase (disabled for Snellen). If enabled, snellen_stop_on_fail is ignored.
    adaptive_row_testing: bool = False
    adaptive_initial_letters: int = 2
    adaptive_tiebreak_letters: int = 1
    adaptive_verify_letters: int = 2
    # Production speaker strategy: provisional 2+1 range, final 3/5 verify.
    smart_range_testing: bool = False
    smart_range_initial_letters: int = 2
    smart_range_tiebreak_letters: int = 1
    smart_verify_letters: int = 5
    max_letter_replacements: int = 1
    left_eye_start_easier_steps: int = 1
    max_misses: int = 2  # Snellen/ETDRS line pass: ≤2 misses on a 5-letter line (≥3/5)
    min_correct: int | None = None  # if set, overrides; else letters - max_misses
    # Model A-only scoring: low=miss, middle=one replacement, high=score label.
    letter_uncertain_threshold: float = 0.45
    letter_accept_threshold: float = 0.75
    # Staircase sizes (large → small). Default = hospital chart 1/10…10/10.
    row_logmars: list[float] = Field(
        default_factory=lambda: [
            1.0,
            0.69897,
            0.52288,
            0.39794,
            0.30103,
            0.22185,
            0.15490,
            0.09691,
            0.04576,
            0.0,
        ]
    )
    start_logmar: float = 0.69897  # 2/10
    logmar_step: float = 0.1
    readiness_timeout_seconds: float = 120.0
    letter_timeout_seconds: float = 10.0  # BQP <10s per letter
    letter_chunk_seconds: float = 3.0
    tablet_chunk_seconds: float = 10.0
    listen_timeout_seconds: float | None = None  # alias; defaults to letter_timeout
    same_size_retries: int = 0  # Snellen: no same-size retry; fail ends the eye
    max_rows_per_eye: int = 16
    staircase: bool = True
    demo_mode: bool = False
    # Lab/off-site: chart shows "Bỏ qua" on wait gates; skip = treat step as passed
    allow_step_skip: bool = False
    start_from_age_norm: bool = False
    row_search: str = "snellen"  # snellen | binary

    @model_validator(mode="after")
    def validate_letter_thresholds(self) -> "ProtocolConfig":
        if not 1.0 <= self.letter_chunk_seconds <= 30.0 or not 1.0 <= self.tablet_chunk_seconds <= 30.0:
            raise ValueError("letter capture windows must be between 1 and 30 seconds")
        low = float(self.letter_uncertain_threshold)
        high = float(self.letter_accept_threshold)
        if not 0.0 <= low < high <= 1.0:
            raise ValueError(
                "letter thresholds must satisfy 0 <= uncertain < accept <= 1"
            )
        if not 0 <= int(self.max_letter_replacements) <= 1:
            raise ValueError("max_letter_replacements must be 0 or 1")
        return self

    def effective_letter_timeout(self) -> float:
        if self.listen_timeout_seconds is not None:
            return float(self.listen_timeout_seconds)
        return float(self.letter_timeout_seconds)

    def effective_min_correct(self) -> int:
        if self.min_correct is not None:
            return int(self.min_correct)
        return max(0, self.letters_per_row - self.max_misses)

    def uses_snellen_stop_on_fail(self) -> bool:
        """Fail at line N ⇒ stop; acuity is last passed line (N-1)."""
        return bool(self.snellen_stop_on_fail) and not bool(self.adaptive_row_testing)

    def uses_binary_row_search(self) -> bool:
        return str(self.row_search or "").strip().lower() == "binary"

    def uses_smart_range_testing(self) -> bool:
        return bool(self.smart_range_testing) and self.uses_binary_row_search()


class VoiceConfig(BaseModel):
    """Station voice directory under scenarios/vi/{male|female}/.

    auto = opposite of Patient.sex; unknown uses male.
    """

    gender: str = "auto"  # auto | male | female


class AudioInputConfig(BaseModel):
    """Clinic audio I/O.

    input:
      browser — chart getUserMedia → /ws/mic → /audio.raw
      device  — Jetson sounddevice (USB dongle) or bridges.sloan_audio_url if set
    output:
      browser — TV/kiosk chart tab (<audio> + WS play_audio)
      sounddevice / device — Jetson Pulse/ALSA (Yealink BT51, analog jack, …)
      both — TV speakers and Yealink together
    input_device / output_device: sounddevice name substring (e.g. Yealink).
    """

    input: str = "device"  # browser | device
    output: str = "sounddevice"  # browser | sounddevice | device | both
    input_device: str = ""
    output_device: str = ""
    prompts_dir: str = "display/prompts/vi"


class PathsConfig(BaseModel):
    dmn: str = "dmn/acuity_flow.dmn"
    scenarios: str = "scenarios/vi/manifest.yaml"
    journals: str = "data/journals"


class FaceDeviceConfig(BaseModel):
    """Closed AiFace panel used for B1 patient identify in demo."""

    mode: str = "off"  # off | aiface
    host: str = "192.168.1.18"
    port: int = 80
    # Address exposed by this Jetson for AiFace BS WebSocket events.
    callback_host: str = ""
    callback_port: int = 7788
    password: str = "12345678"
    device_id: str = "panel-01"
    role: str = "combined"  # combined | front_door | vision_room
    poll_interval_seconds: float = 1.0
    timeout_seconds: float = 120.0
    # Max age (seconds) for a new log row after baseline; does not replay old scans.
    accept_recent_seconds: float = 15.0
    # AiFace BS live events on clinic station (WS :7788 → HTTP :7790); Jetson localhost when AC runs there.
    live_events_url: str = "http://127.0.0.1:7790/events"


class FaceDeviceEntry(BaseModel):
    id: str
    host: str
    role: str = "vision_room"
    port: int = 80


class HospitalConfig(BaseModel):
    base_url: str = "http://192.168.1.78:8000"  # Mac hospital host
    timeout_seconds: float = 10.0
    api_key: str = ""
    api_secret: str = ""


class MediaConfig(BaseModel):
    """Mac media gateway — patient audio/images (not Hospital API)."""

    enabled: bool = True
    base_url: str = "http://192.168.1.78:9010"
    token: str = "dev-media-token"
    timeout_seconds: float = 30.0


class CccdQrConfig(BaseModel):
    """Face ID JPEG → media cccd_qr → VPS qr_decode → Frappe apply_cccd_scan."""

    enabled: bool = True
    after_face: bool = True
    timeout_seconds: float = 60.0


class FaceVectorDbConfig(BaseModel):
    """Hospital / cloud face gallery (VectorDB API) — sync down to AiFace panel.

    Placeholder contract until the real VectorDB OpenAPI lands. Env overrides:
    FACE_VECTORDB_ENABLED, FACE_VECTORDB_BASE_URL, FACE_VECTORDB_API_KEY,
    FACE_VECTORDB_MODE (http|mock|off).
    """

    enabled: bool = False
    mode: str = "mock"  # off | mock | http
    base_url: str = "http://127.0.0.1:8100"
    api_key: str = ""
    api_key_header: str = "X-Api-Key"
    timeout_seconds: float = 15.0
    # Path templates relative to base_url
    list_path: str = "/v1/faces"
    get_path: str = "/v1/faces/{enroll_id}"
    image_path: str = "/v1/faces/{enroll_id}/image"
    # Sync behaviour
    sync_on_startup: bool = True
    sync_before_identify: bool = False
    # When true, gallery comes from Frappe today's appointments (desk enrolls).
    sync_today_appointments_only: bool = True
    prune_not_in_today: bool = True
    # Jetson pull-loop: re-read today's appointments and push/prune AiFace gallery.
    # Needed because Frappe (VPS) often cannot reach the Jetson on the clinic LAN.
    sync_today_poll_seconds: float = 10.0
    # No Frappe Start button: when today's gallery has ≥1 face, wait for AiFace
    # match and auto-enter the vision test.
    auto_start_on_face: bool = True
    # Local overnight wipe on the Jetson (preserve stranger id).
    overnight_wipe_enabled: bool = True
    overnight_wipe_hour: int = 0
    overnight_wipe_minute: int = 5
    max_faces: int = 500
    # AiFace setuserinfo backupnum for face template / display JPEG
    device_face_backupnum: int = 50


class BridgesConfig(BaseModel):
    readiness: str = "mock"  # mock | smarteyes
    stt: str = "mock"  # mock | sloan | ui
    face: FaceDeviceConfig = Field(default_factory=FaceDeviceConfig)
    smarteyes_root: str = "../SmartEyes"
    smarteyes_config: str = "../SmartEyes/configs/default.yaml"
    # Camera index ("0") or name ("macbook" / "C270")
    smarteyes_source: str | int = "macbook"
    smarteyes_show_window: bool = False  # OpenCV HighGUI fails off main thread (macOS)
    # /preview MJPEG + overlay render. False at boot saves Jetson CPU; exam WAIT_READY still starts CV.
    smarteyes_preview_enabled: bool = False
    smarteyes_strict: bool = True  # fail if SmartEyes import/camera fails
    sloan_root: str = "../sloan_stt"
    min_confidence_demo: float = 0.55
    sloan_audio_url: str = ""
    sloan_audio_sample_rate: int = 48000
    sloan_energy_threshold: float = 0.025
    sloan_silence_duration: float = 0.35
    sloan_min_margin: float = 0.05
    sloan_min_voiced_seconds: float = 0.15
    sloan_vad_padding_seconds: float = 0.12
    # Optional per-letter recognizer calibration. The exam decision still uses
    # protocol.letter_uncertain_threshold and protocol.letter_accept_threshold.
    sloan_class_confidence_thresholds: dict[str, float] = Field(default_factory=dict)


class UiConfig(BaseModel):
    """Patient chart flow. speaker_v1 = clinic speaker-guided path."""

    patient_flow: str = "classic"  # classic | speaker_v1
    input_mode: str = "speak"  # speak | tablet
    input_mode_choice_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    # Live SmartEyes coaching on the patient TV (often English HUD). Off = keep
    # VN stand/cover copy. CV still runs; /preview overlay is unchanged.
    chart_cv_coaching: bool = False

    @model_validator(mode="after")
    def validate_input_mode(self) -> "UiConfig":
        if self.input_mode not in {"speak", "tablet"}:
            raise ValueError("ui.input_mode must be speak or tablet")
        return self


class AppConfig(BaseModel):
    station_id: str = "station-01"
    mqtt: MqttConfig = Field(default_factory=MqttConfig)
    http: HttpConfig = Field(default_factory=HttpConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    protocol: ProtocolConfig = Field(default_factory=ProtocolConfig)
    ui: UiConfig = Field(default_factory=UiConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    bridges: BridgesConfig = Field(default_factory=BridgesConfig)
    hospital: HospitalConfig = Field(default_factory=HospitalConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    audio: AudioInputConfig = Field(default_factory=AudioInputConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    cccd_qr: CccdQrConfig = Field(default_factory=CccdQrConfig)
    face_vectordb: FaceVectorDbConfig = Field(default_factory=FaceVectorDbConfig)
    # Production dual-panel stub (MVP uses bridges.face only)
    face_devices: list[FaceDeviceEntry] = Field(default_factory=list)

    def resolve(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (ROOT / p)


class EnvOverrides(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    mqtt_host: str | None = None
    mqtt_port: int | None = None
    mqtt_user: str | None = None
    mqtt_pass: str | None = None
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool | None = None
    mqtt_tls_ca_certs: str | None = None
    station_id: str | None = None
    face_host: str | None = None
    face_port: int | None = None
    jetson_lan_ip: str | None = None
    aiface_callback_port: int | None = None
    face_password: str | None = None
    face_mode: str | None = None
    face_vectordb_enabled: bool | None = None
    face_vectordb_base_url: str | None = None
    face_vectordb_api_key: str | None = None
    face_vectordb_mode: str | None = None


def _merge_config(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge nested YAML mappings so hospital profiles can extend a base."""
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_config(path: Path, stack: tuple[Path, ...] = ()) -> dict[str, Any]:
    cfg_path = path.expanduser().resolve()
    if cfg_path in stack:
        chain = " -> ".join(str(item) for item in (*stack, cfg_path))
        raise ValueError(f"Circular config inheritance: {chain}")
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Assistant Controller config not found: {cfg_path}")
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Assistant Controller config must be a YAML mapping: {cfg_path}")
    parent = data.pop("extends", None)
    if not parent:
        return data
    parent_path = Path(parent)
    if not parent_path.is_absolute():
        parent_path = cfg_path.parent / parent_path
    return _merge_config(_read_config(parent_path, (*stack, cfg_path)), data)


def load_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or (ROOT / "configs" / "default.yaml")
    data = _read_config(cfg_path)
    cfg = AppConfig.model_validate(data)

    env = EnvOverrides()
    if os.getenv("MQTT_HOST") or env.mqtt_host:
        cfg.mqtt.host = os.getenv("MQTT_HOST") or env.mqtt_host or cfg.mqtt.host
    if os.getenv("MQTT_PORT") or env.mqtt_port:
        cfg.mqtt.port = int(os.getenv("MQTT_PORT") or env.mqtt_port or cfg.mqtt.port)
    mqtt_user = os.getenv("MQTT_USER")
    if mqtt_user is None:
        mqtt_user = os.getenv("MQTT_USERNAME")
    if mqtt_user is None:
        mqtt_user = env.mqtt_user or env.mqtt_username
    if mqtt_user is not None:
        cfg.mqtt.username = mqtt_user
    mqtt_pass = os.getenv("MQTT_PASS")
    if mqtt_pass is None:
        mqtt_pass = os.getenv("MQTT_PASSWORD")
    if mqtt_pass is None:
        mqtt_pass = env.mqtt_pass or env.mqtt_password
    if mqtt_pass is not None:
        cfg.mqtt.password = mqtt_pass
    if os.getenv("MQTT_TLS") is not None or env.mqtt_tls is not None:
        raw_tls = os.getenv("MQTT_TLS")
        cfg.mqtt.tls = (
            raw_tls.strip().lower() in ("1", "true", "yes", "on")
            if raw_tls is not None
            else bool(env.mqtt_tls)
        )
    if os.getenv("MQTT_TLS_CA_CERTS") or env.mqtt_tls_ca_certs:
        cfg.mqtt.tls_ca_certs = os.getenv("MQTT_TLS_CA_CERTS") or env.mqtt_tls_ca_certs
    if os.getenv("STATION_ID") or env.station_id:
        cfg.station_id = os.getenv("STATION_ID") or env.station_id or cfg.station_id
    if os.getenv("FACE_MODE") or env.face_mode:
        cfg.bridges.face.mode = os.getenv("FACE_MODE") or env.face_mode or cfg.bridges.face.mode
    if os.getenv("FACE_HOST") or env.face_host:
        cfg.bridges.face.host = os.getenv("FACE_HOST") or env.face_host or cfg.bridges.face.host
    if os.getenv("FACE_PORT") or env.face_port:
        cfg.bridges.face.port = int(os.getenv("FACE_PORT") or env.face_port or cfg.bridges.face.port)
    if os.getenv("JETSON_LAN_IP") or env.jetson_lan_ip:
        cfg.bridges.face.callback_host = (
            os.getenv("JETSON_LAN_IP") or env.jetson_lan_ip or cfg.bridges.face.callback_host
        )
    if os.getenv("AIFACE_CALLBACK_PORT") or env.aiface_callback_port:
        cfg.bridges.face.callback_port = int(
            os.getenv("AIFACE_CALLBACK_PORT")
            or env.aiface_callback_port
            or cfg.bridges.face.callback_port
        )
    if os.getenv("FACE_PASSWORD") is not None or env.face_password is not None:
        cfg.bridges.face.password = (
            os.getenv("FACE_PASSWORD")
            if os.getenv("FACE_PASSWORD") is not None
            else (env.face_password or cfg.bridges.face.password)
        )
    # Face VectorDB gallery (placeholder until real API)
    if os.getenv("FACE_VECTORDB_ENABLED") is not None or env.face_vectordb_enabled is not None:
        raw = os.getenv("FACE_VECTORDB_ENABLED")
        if raw is not None:
            cfg.face_vectordb.enabled = raw.strip().lower() in ("1", "true", "yes", "on")
        elif env.face_vectordb_enabled is not None:
            cfg.face_vectordb.enabled = env.face_vectordb_enabled
    if os.getenv("FACE_VECTORDB_BASE_URL") or env.face_vectordb_base_url:
        cfg.face_vectordb.base_url = (
            os.getenv("FACE_VECTORDB_BASE_URL")
            or env.face_vectordb_base_url
            or cfg.face_vectordb.base_url
        )
    if os.getenv("FACE_VECTORDB_API_KEY") is not None or env.face_vectordb_api_key is not None:
        cfg.face_vectordb.api_key = (
            os.getenv("FACE_VECTORDB_API_KEY")
            if os.getenv("FACE_VECTORDB_API_KEY") is not None
            else (env.face_vectordb_api_key or "")
        )
    if os.getenv("FACE_VECTORDB_MODE") or env.face_vectordb_mode:
        cfg.face_vectordb.mode = (
            os.getenv("FACE_VECTORDB_MODE") or env.face_vectordb_mode or cfg.face_vectordb.mode
        )
    # Hospital / media HTTP. VPS_HOST rewrites mqtt + HTTP bases; explicit URLs win after.
    vps = (os.getenv("VPS_HOST") or "").strip()
    if vps:
        if not (os.getenv("MQTT_HOST") or env.mqtt_host):
            cfg.mqtt.host = vps
        cfg.hospital.base_url = f"http://{vps}:8000"
        cfg.media.base_url = f"http://{vps}:9010"
        cfg.face_vectordb.base_url = f"http://{vps}:8100"
    if os.getenv("HOSPITAL_BASE_URL"):
        cfg.hospital.base_url = os.environ["HOSPITAL_BASE_URL"].rstrip("/")
    if os.getenv("MEDIA_BASE_URL"):
        cfg.media.base_url = os.environ["MEDIA_BASE_URL"].rstrip("/")
    if os.getenv("MEDIA_TOKEN"):
        cfg.media.token = os.environ["MEDIA_TOKEN"]
    if os.getenv("FACE_VECTORDB_BASE_URL") or env.face_vectordb_base_url:
        cfg.face_vectordb.base_url = (
            os.getenv("FACE_VECTORDB_BASE_URL")
            or env.face_vectordb_base_url
            or cfg.face_vectordb.base_url
        )
    return cfg
