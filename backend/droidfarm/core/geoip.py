"""GeoIP lookup + proxy health check.

When a proxy is imported we want to know:
  (a) is it actually reachable and how fast,
  (b) what country/city/lat/long it appears to originate from.

(b) is what makes the phone "feel like it's in that city" — we copy the
location fields onto the phone's geo_overrides JSON at boot and push them
into Android via adb.

We call https://ipapi.co/json/ **through the proxy** so the upstream sees
the exit IP, not the control-plane host. ipapi.co is free up to 1k
requests/day and requires no API key. Users who need more can set
DROIDFARM_IPAPI_URL to any API with the same schema.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from droidfarm.db import Proxy

logger = logging.getLogger(__name__)

IPAPI_URL = "https://ipapi.co/json/"
TIMEOUT = 12.0


def _to_float(v: object) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def lookup_host_geo() -> "GeoResult":
    """GeoIP lookup for the **host VM's own public IP** — no proxy.

    Used when a phone is created with proxy_mode='none' / bypass: we still
    want to spoof locale/timezone/GPS, we just use the VM's IP-based geo
    as the source of truth.
    """
    t0 = time.monotonic()
    try:
        with httpx.Client(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "droidfarm/0.1 host-geo"},
        ) as c:
            r = c.get(IPAPI_URL)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return GeoResult(ok=False, latency_ms=None, error=f"{type(e).__name__}: {e}")
    latency_ms = int((time.monotonic() - t0) * 1000)
    if "error" in data:
        return GeoResult(ok=False, latency_ms=latency_ms, error=str(data.get("reason") or data.get("error")))
    return GeoResult(
        ok=True,
        latency_ms=latency_ms,
        ip=data.get("ip"),
        country=data.get("country_name") or data.get("country"),
        region=data.get("region"),
        city=data.get("city"),
        latitude=_to_float(data.get("latitude")),
        longitude=_to_float(data.get("longitude")),
        timezone=data.get("timezone"),
        asn=data.get("asn"),
        provider=data.get("org") or data.get("asn_org"),
    )


@dataclass
class GeoResult:
    ok: bool
    latency_ms: int | None
    error: str | None = None
    ip: str | None = None
    country: str | None = None
    region: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    asn: str | None = None
    provider: str | None = None


def _proxy_url(p: Proxy) -> str:
    auth = ""
    if p.username:
        pwd = quote(p.password or "", safe="")
        user = quote(p.username, safe="")
        auth = f"{user}:{pwd}@"
    return f"{p.scheme}://{auth}{p.host}:{p.port}"


def check_proxy(p: Proxy) -> GeoResult:
    """Issue one GET through the proxy and parse the response into a GeoResult."""
    url = _proxy_url(p)
    t0 = time.monotonic()
    try:
        with httpx.Client(
            proxy=url,
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "droidfarm/0.1 proxy-check"},
        ) as c:
            r = c.get(IPAPI_URL)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        return GeoResult(ok=False, latency_ms=None, error=str(e))
    except Exception as e:
        return GeoResult(ok=False, latency_ms=None, error=f"{type(e).__name__}: {e}")

    latency_ms = int((time.monotonic() - t0) * 1000)

    if "error" in data:
        return GeoResult(ok=False, latency_ms=latency_ms, error=str(data.get("reason") or data.get("error")))

    return GeoResult(
        ok=True,
        latency_ms=latency_ms,
        ip=data.get("ip"),
        country=data.get("country_name") or data.get("country"),
        region=data.get("region"),
        city=data.get("city"),
        latitude=_to_float(data.get("latitude")),
        longitude=_to_float(data.get("longitude")),
        timezone=data.get("timezone"),
        asn=data.get("asn"),
        provider=data.get("org") or data.get("asn_org"),
    )
