"""Pydantic DTOs for the HTTP API (separate from SQLAlchemy ORM models)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProxyScheme = Literal["http", "https", "socks5"]
PhoneStatus = Literal["stopped", "starting", "running", "stopping", "crashed"]
ProxyMode = Literal["tun2socks", "system-http", "none"]


class ProxyIn(BaseModel):
    label: str = ""
    scheme: ProxyScheme = "http"
    host: str
    port: int = Field(ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    notes: str = ""


class ProxyOut(BaseModel):
    id: int
    label: str
    scheme: ProxyScheme
    host: str
    port: int
    username: str | None
    has_password: bool
    country: str | None
    region: str | None
    city: str | None
    latitude: float | None
    longitude: float | None
    timezone: str | None
    asn: str | None
    provider: str | None
    is_healthy: bool
    last_checked_at: datetime | None
    last_error: str | None
    latency_ms: int | None
    created_at: datetime
    notes: str
    # Which phone is currently holding this proxy (None if free).
    assigned_to_phone_id: int | None
    assigned_to_phone_name: str | None


class ProxyImportLine(BaseModel):
    """One line from a pasted/imported proxy list."""

    raw: str


class PhoneIn(BaseModel):
    name: str
    device_profile: str = "pixel-6"
    android_version: str = "13"
    resolution: str = "1080x1920"
    dpi: int = 420
    cpu: int = 2
    ram_mb: int = 4096
    autostart: bool = True
    # False (default) → clone from the 'configured' template; phone boots
    # straight to launcher with the setup wizard already dismissed.
    # True → clone from the 'factory' template; phone shows the usual
    # Android first-boot experience. Either way the clone has no user data.
    show_setup_wizard: bool = False
    proxy_mode: ProxyMode = "tun2socks"
    # Pass exactly one of: proxy_id (pick a specific row), auto_assign_proxy=True
    # (pick any free row), or neither (phone runs with no proxy).
    proxy_id: int | None = None
    auto_assign_proxy: bool = False
    # Optional overrides only used when bypass_ip=True (proxy_mode='none').
    # Leave empty to use the VM's own real geo from ipapi.co; set to pin
    # the phone's locale/timezone/GPS to a specific country + city while
    # still egressing through the VM's real IP.
    geo_override_country: str | None = None
    geo_override_city: str | None = None
    # When True, explicitly skip the proxy and use the host VM's own egress.
    # Geo is seeded from the host's public-IP geoIP so locale/timezone/GPS
    # stay consistent with what apps see at the network layer. Overrides
    # proxy_mode to 'none' and ignores proxy_id.
    bypass_ip: bool = False
    preinstall_apks: list[int] = Field(default_factory=list)


class PhoneOut(BaseModel):
    id: int
    name: str
    ldplayer_index: int | None
    device_profile: str
    android_version: str
    resolution: str
    dpi: int
    cpu: int
    ram_mb: int
    status: PhoneStatus
    autostart: bool
    show_setup_wizard: bool
    proxy_mode: ProxyMode
    proxy: ProxyOut | None
    geo_overrides: dict
    preinstall_apks: list[int]
    created_at: datetime
    last_started_at: datetime | None
    last_error: str | None
    deleted_at: datetime | None = None
    fingerprint: dict = {}


class ApkOut(BaseModel):
    id: int
    filename: str
    package_name: str | None
    version_name: str | None
    size_bytes: int
    sha256: str | None
    added_at: datetime
