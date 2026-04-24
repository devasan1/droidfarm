"""Per-phone hardware fingerprint generation.

Every clone of a template LDPlayer instance ends up with identical
hardware identifiers (IMEI, Android ID, MAC, build props, serial,
WebView UA). Apps that look for "two devices with the same fingerprint
== same user" will flag clones as siblings and ban accounts. This
module synthesizes a plausible-but-unique fingerprint per phone.

Nothing here is cryptographically random — it's meant to *look* like a
real retail device, not to hide from a forensic analysis. The values
are deterministic only inside a single call; each call produces a new
dict.
"""

from __future__ import annotations

import random
import secrets
import string
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    manufacturer: str
    brand: str          # e.g. "google", "samsung" — lowercased, ro.product.brand
    model: str          # user-visible model, ro.product.model + Build.MODEL
    device: str         # codename, ro.product.device
    product: str        # product name, ro.product.name
    webview_base: str   # base Chromium version in WebView UA
    android_release: str  # "13", "14"
    build_id: str       # build fingerprint tag, e.g. "TQ3A.230901.001"


# A curated pool of current-ish retail devices. Keeps the fingerprint
# surface looking like a real Play Store user base. Expand as needed.
_DEVICE_POOL: list[DeviceProfile] = [
    DeviceProfile(
        "Google", "google", "Pixel 7", "panther", "panther",
        "119.0.6045.163", "13", "TQ3A.230901.001",
    ),
    DeviceProfile(
        "Google", "google", "Pixel 7 Pro", "cheetah", "cheetah",
        "119.0.6045.163", "13", "TQ3A.230901.001",
    ),
    DeviceProfile(
        "Google", "google", "Pixel 6", "oriole", "oriole",
        "119.0.6045.163", "13", "TQ3A.230901.001",
    ),
    DeviceProfile(
        "Google", "google", "Pixel 8", "shiba", "shiba",
        "120.0.6099.144", "14", "UP1A.231105.003",
    ),
    DeviceProfile(
        "samsung", "samsung", "SM-S918B", "dm3q", "dm3qxxx",
        "119.0.6045.163", "13", "TP1A.220624.014",
    ),
    DeviceProfile(
        "samsung", "samsung", "SM-A536B", "a53x", "a53xxxx",
        "118.0.5993.80", "13", "TP1A.220624.014",
    ),
    DeviceProfile(
        "Xiaomi", "Xiaomi", "2201123G", "cupid", "cupid_global",
        "118.0.5993.80", "13", "TKQ1.220829.002",
    ),
    DeviceProfile(
        "OnePlus", "OnePlus", "CPH2415", "OP5929L1", "OP5929L1",
        "118.0.5993.80", "13", "TP1A.220905.001",
    ),
    DeviceProfile(
        "OPPO", "OPPO", "CPH2459", "OP574CL1", "CPH2459",
        "118.0.5993.80", "13", "TP1A.220905.001",
    ),
    DeviceProfile(
        "motorola", "motorola", "motorola edge 30", "dubai",
        "dubai_g", "118.0.5993.80", "13", "T1RDS33M.1-36-7",
    ),
    DeviceProfile(
        "Sony", "Sony", "XQ-CT54", "pdx-223", "XQ-CT54",
        "118.0.5993.80", "13", "64.1.A.2.442",
    ),
    DeviceProfile(
        "HMD Global", "Nokia", "Nokia G60 5G", "AOP_sprout",
        "Nokia_G60", "118.0.5993.80", "13", "00WW_1_380",
    ),
]


def _luhn_check_digit(num: str) -> str:
    """Standard Luhn checksum over decimal digits, returns the 15th IMEI digit."""
    total = 0
    # num is 14 digits; double every *second* digit from the right of the
    # full 15-digit payload, i.e. positions 1,3,5,... in 0-indexed from right.
    for i, ch in enumerate(reversed(num)):
        d = ord(ch) - 48
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def _random_imei() -> str:
    """Generate a 15-digit IMEI with a valid Luhn check digit.

    The TAC (first 8 digits) is picked from a small pool of real
    type-allocation codes for common smartphones so IMEI-database
    lookups don't flag the number as obviously synthetic.
    """
    tacs = [
        "35847310",  # Samsung Galaxy family
        "86700504",  # Google Pixel family
        "35269211",  # Xiaomi
        "35471415",  # OnePlus
        "35852310",  # OPPO
        "35984510",  # Motorola
    ]
    tac = random.choice(tacs)
    serial = "".join(random.choices("0123456789", k=6))
    base = tac + serial
    return base + _luhn_check_digit(base)


def _random_android_id() -> str:
    """16-hex-char Settings.Secure.ANDROID_ID value (64-bit)."""
    return secrets.token_hex(8)


def _random_mac() -> str:
    """A locally-administered unicast MAC. Second nibble == 2 per
    IEEE 802c — mirrors what modern Android (8+) uses for MAC
    randomization on Wi-Fi networks, so it blends in."""
    octets = [0x02] + [random.randint(0x00, 0xFF) for _ in range(5)]
    return ":".join(f"{o:02x}" for o in octets)


def _random_serial() -> str:
    """10-char alphanumeric build serial."""
    return "".join(
        random.choices(string.ascii_uppercase + string.digits, k=10)
    )


def _random_gsf_id() -> str:
    """16-hex-char Google Services Framework ID. Apps look at this for
    cross-install tracking on the same device."""
    return secrets.token_hex(8)


def _random_advertising_id() -> str:
    """Google Advertising ID (GAID) — UUIDv4 string."""
    return str(uuid.uuid4())


def _random_instance_id() -> str:
    """Firebase Instance ID — 11 url-safe base64 chars."""
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(random.choices(alphabet, k=11))


def _webview_ua(profile: DeviceProfile) -> str:
    """A realistic Chrome-on-Android user agent string that matches the
    profile's build + webview version."""
    return (
        f"Mozilla/5.0 (Linux; Android {profile.android_release}; "
        f"{profile.model}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{profile.webview_base} Mobile Safari/537.36"
    )


def generate_fingerprint(
    seed: str | None = None,
    device_profile: str | None = None,
) -> dict:
    """Return a fresh per-phone fingerprint.

    Args:
        seed: if provided, makes the result reproducible for that seed
            (useful for tests). Production paths should leave this None
            so secrets.token_hex stays cryptographically random.
        device_profile: if provided and matches a ``DeviceProfile.model``
            in the pool, pin the hardware to that model. Otherwise pick
            a random one from the pool.
    """
    if seed is not None:
        random.seed(seed)

    if device_profile:
        profile = next(
            (p for p in _DEVICE_POOL if p.model == device_profile),
            random.choice(_DEVICE_POOL),
        )
    else:
        profile = random.choice(_DEVICE_POOL)

    return {
        "manufacturer": profile.manufacturer,
        "brand": profile.brand,
        "model": profile.model,
        "device": profile.device,
        "product": profile.product,
        "android_release": profile.android_release,
        "build_id": profile.build_id,
        "imei": _random_imei(),
        "android_id": _random_android_id(),
        "mac_wifi": _random_mac(),
        "mac_bluetooth": _random_mac(),
        "serial_no": _random_serial(),
        "gsf_id": _random_gsf_id(),
        "advertising_id": _random_advertising_id(),
        "firebase_iid": _random_instance_id(),
        "webview_ua": _webview_ua(profile),
    }


def list_device_profiles() -> list[dict]:
    """Return the catalogue of device profiles (for the UI dropdown)."""
    return [
        {
            "manufacturer": p.manufacturer,
            "model": p.model,
            "android_release": p.android_release,
        }
        for p in _DEVICE_POOL
    ]
