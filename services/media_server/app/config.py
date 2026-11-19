"""Media gateway settings (Mac host)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    media_root: str = "./data"
    media_host: str = "0.0.0.0"
    media_port: int = 9010
    media_public_base: str = "http://103.249.117.203:9010"
    media_token: str = "dev-media-token"
    media_stations: str = "station-01"
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    grant_ttl_seconds: int = 600
    # Several hospitals on one gateway (see app/tenants.py); empty = single MEDIA_TOKEN.
    media_tenants: str = ""
    media_tenant_tokens_dir: str = ""

    def station_list(self) -> list[str]:
        return [s.strip() for s in self.media_stations.split(",") if s.strip()]


settings = Settings()
