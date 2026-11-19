"""Hospitals (tenants) sharing one media gateway.

MEDIA_TENANTS="main:station-01;qdymd:qdymd-01,qdymd-02" names each tenant and its stations. The
token of tenant <name> is the file MEDIA_TENANT_TOKENS_DIR/<name>, so tokens never sit in the
environment. A tenant's token reaches only objects under its own stations ("<station>/…").
Without MEDIA_TENANTS the gateway keeps the single MEDIA_TOKEN for every station.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tenant:
    name: str
    token: str
    stations: frozenset[str]


def parse_tenants(spec: str, tokens_dir: str) -> list[Tenant]:
    """Parse MEDIA_TENANTS; any inconsistency stops the gateway at start with the offending entry."""
    tenants: list[Tenant] = []
    owner: dict[str, str] = {}
    for part in filter(None, (p.strip() for p in spec.split(";"))):
        name, sep, stations_csv = part.partition(":")
        name = name.strip()
        stations = frozenset(s.strip() for s in stations_csv.split(",") if s.strip())
        if not sep or not name or "/" in name or not stations:
            raise ValueError(f"MEDIA_TENANTS entry {part!r}: expected <tenant>:<station>[,<station>…]")
        if any(t.name == name for t in tenants):
            raise ValueError(f"MEDIA_TENANTS: tenant {name!r} is listed twice")
        for station in stations:
            if station in owner:
                raise ValueError(
                    f"MEDIA_TENANTS: station {station!r} is listed under both {owner[station]!r} and {name!r}"
                )
            owner[station] = name
        if not tokens_dir:
            raise ValueError("MEDIA_TENANTS is set but MEDIA_TENANT_TOKENS_DIR is empty")
        token_file = Path(tokens_dir) / name
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            raise ValueError(f"MEDIA_TENANTS: no token file {token_file} for tenant {name!r}") from None
        if not token:
            raise ValueError(f"MEDIA_TENANTS: token file {token_file} for tenant {name!r} is empty")
        tenants.append(Tenant(name=name, token=token, stations=stations))
    if len({t.token for t in tenants}) != len(tenants):
        raise ValueError("MEDIA_TENANTS: two tenants share one token")
    return tenants


def match_tenant(tenants: list[Tenant], token: str | None) -> Tenant | None:
    if not token:
        return None
    for tenant in tenants:
        if hmac.compare_digest(token.encode(), tenant.token.encode()):
            return tenant
    return None
