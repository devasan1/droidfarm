"""Country-code → sensible-default locale + timezone.

When a phone is linked to a proxy we want the phone's locale and time
zone to match the *network egress country*, otherwise fingerprinting is
trivial ("phone says en-US but its IP is in Germany — bot").

This is a best-effort mapping keyed by ISO country name or 2-letter code
(the ipapi.co response uses both). Locale picks the most populous
language for the country; timezone picks the capital/most-populous zone.
Users can always override via ``geo_overrides.locale`` /
``geo_overrides.timezone`` on the phone row if the default is wrong.
"""

from __future__ import annotations

# Keyed by ISO alpha-2. The country-name aliases are layered on below so
# "United States" and "US" both resolve.
_BY_CC: dict[str, tuple[str, str]] = {
    "US": ("en-US", "America/New_York"),
    "CA": ("en-CA", "America/Toronto"),
    "GB": ("en-GB", "Europe/London"),
    "UK": ("en-GB", "Europe/London"),
    "IE": ("en-IE", "Europe/Dublin"),
    "AU": ("en-AU", "Australia/Sydney"),
    "NZ": ("en-NZ", "Pacific/Auckland"),
    "DE": ("de-DE", "Europe/Berlin"),
    "AT": ("de-AT", "Europe/Vienna"),
    "CH": ("de-CH", "Europe/Zurich"),
    "FR": ("fr-FR", "Europe/Paris"),
    "BE": ("fr-BE", "Europe/Brussels"),
    "LU": ("fr-LU", "Europe/Luxembourg"),
    "NL": ("nl-NL", "Europe/Amsterdam"),
    "IT": ("it-IT", "Europe/Rome"),
    "ES": ("es-ES", "Europe/Madrid"),
    "PT": ("pt-PT", "Europe/Lisbon"),
    "PL": ("pl-PL", "Europe/Warsaw"),
    "SE": ("sv-SE", "Europe/Stockholm"),
    "NO": ("no-NO", "Europe/Oslo"),
    "DK": ("da-DK", "Europe/Copenhagen"),
    "FI": ("fi-FI", "Europe/Helsinki"),
    "IS": ("is-IS", "Atlantic/Reykjavik"),
    "EE": ("et-EE", "Europe/Tallinn"),
    "LV": ("lv-LV", "Europe/Riga"),
    "LT": ("lt-LT", "Europe/Vilnius"),
    "CZ": ("cs-CZ", "Europe/Prague"),
    "SK": ("sk-SK", "Europe/Bratislava"),
    "HU": ("hu-HU", "Europe/Budapest"),
    "RO": ("ro-RO", "Europe/Bucharest"),
    "BG": ("bg-BG", "Europe/Sofia"),
    "GR": ("el-GR", "Europe/Athens"),
    "HR": ("hr-HR", "Europe/Zagreb"),
    "SI": ("sl-SI", "Europe/Ljubljana"),
    "RS": ("sr-RS", "Europe/Belgrade"),
    "UA": ("uk-UA", "Europe/Kyiv"),
    "RU": ("ru-RU", "Europe/Moscow"),
    "TR": ("tr-TR", "Europe/Istanbul"),
    "IL": ("he-IL", "Asia/Jerusalem"),
    "AE": ("ar-AE", "Asia/Dubai"),
    "SA": ("ar-SA", "Asia/Riyadh"),
    "EG": ("ar-EG", "Africa/Cairo"),
    "ZA": ("en-ZA", "Africa/Johannesburg"),
    "NG": ("en-NG", "Africa/Lagos"),
    "KE": ("en-KE", "Africa/Nairobi"),
    "MA": ("ar-MA", "Africa/Casablanca"),
    "IN": ("en-IN", "Asia/Kolkata"),
    "PK": ("en-PK", "Asia/Karachi"),
    "BD": ("bn-BD", "Asia/Dhaka"),
    "LK": ("si-LK", "Asia/Colombo"),
    "CN": ("zh-CN", "Asia/Shanghai"),
    "HK": ("zh-HK", "Asia/Hong_Kong"),
    "TW": ("zh-TW", "Asia/Taipei"),
    "JP": ("ja-JP", "Asia/Tokyo"),
    "KR": ("ko-KR", "Asia/Seoul"),
    "TH": ("th-TH", "Asia/Bangkok"),
    "VN": ("vi-VN", "Asia/Ho_Chi_Minh"),
    "PH": ("en-PH", "Asia/Manila"),
    "ID": ("id-ID", "Asia/Jakarta"),
    "MY": ("ms-MY", "Asia/Kuala_Lumpur"),
    "SG": ("en-SG", "Asia/Singapore"),
    "MX": ("es-MX", "America/Mexico_City"),
    "BR": ("pt-BR", "America/Sao_Paulo"),
    "AR": ("es-AR", "America/Argentina/Buenos_Aires"),
    "CL": ("es-CL", "America/Santiago"),
    "CO": ("es-CO", "America/Bogota"),
    "PE": ("es-PE", "America/Lima"),
    "VE": ("es-VE", "America/Caracas"),
}


_NAME_TO_CC: dict[str, str] = {
    "united states": "US", "united states of america": "US", "usa": "US",
    "canada": "CA", "united kingdom": "GB", "great britain": "GB",
    "ireland": "IE", "australia": "AU", "new zealand": "NZ",
    "germany": "DE", "austria": "AT", "switzerland": "CH",
    "france": "FR", "belgium": "BE", "luxembourg": "LU",
    "netherlands": "NL", "the netherlands": "NL", "holland": "NL",
    "italy": "IT", "spain": "ES", "portugal": "PT", "poland": "PL",
    "sweden": "SE", "norway": "NO", "denmark": "DK", "finland": "FI",
    "iceland": "IS", "estonia": "EE", "latvia": "LV", "lithuania": "LT",
    "czech republic": "CZ", "czechia": "CZ",
    "slovakia": "SK", "hungary": "HU", "romania": "RO", "bulgaria": "BG",
    "greece": "GR", "croatia": "HR", "slovenia": "SI", "serbia": "RS",
    "ukraine": "UA", "russia": "RU", "russian federation": "RU",
    "turkey": "TR", "israel": "IL",
    "united arab emirates": "AE", "uae": "AE",
    "saudi arabia": "SA", "egypt": "EG",
    "south africa": "ZA", "nigeria": "NG", "kenya": "KE", "morocco": "MA",
    "india": "IN", "pakistan": "PK", "bangladesh": "BD", "sri lanka": "LK",
    "china": "CN", "hong kong": "HK", "taiwan": "TW",
    "japan": "JP", "south korea": "KR", "korea": "KR",
    "thailand": "TH", "vietnam": "VN", "philippines": "PH",
    "indonesia": "ID", "malaysia": "MY", "singapore": "SG",
    "mexico": "MX", "brazil": "BR", "argentina": "AR", "chile": "CL",
    "colombia": "CO", "peru": "PE", "venezuela": "VE",
}


def locale_and_tz_for(country: str | None) -> tuple[str | None, str | None]:
    """Return (locale, timezone) defaults for a country name or ISO code."""
    if not country:
        return (None, None)
    c = country.strip()
    # Try ISO alpha-2 first (case-insensitive), then the name alias table.
    if c.upper() in _BY_CC:
        return _BY_CC[c.upper()]
    cc = _NAME_TO_CC.get(c.lower())
    if cc and cc in _BY_CC:
        return _BY_CC[cc]
    return (None, None)
