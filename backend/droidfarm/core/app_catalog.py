"""Curated catalog of common apps users want to pre-load.

The catalog is just metadata — slug, display name, package name,
category, icon, and a canonical source URL. DroidFarm never ships the
APKs themselves (they're Google-Play-restricted redistributables), so
we give the user three equally convenient paths to get them into the
library:

1. **"Open source page"** — opens the canonical APKMirror page in a new
   tab. User downloads the APK there and drags it onto DroidFarm's APK
   library. Zero risk of copyright issues.

2. **"Fetch from URL"** — user pastes a direct-download URL (from
   APKMirror, APKPure, or an internal mirror) and DroidFarm downloads
   it server-side into the library. Convenient for self-hosted mirrors.

3. **Local drop folder** — anything in ``<data_dir>/catalog/`` at
   startup is auto-indexed into the library, so you can populate a
   library image with your own vetted APK set and DroidFarm will pick
   them up.

The catalog is intentionally short and focused on the "social /
messaging / video" apps most farming workflows care about.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class CatalogEntry:
    slug: str
    display_name: str
    package: str
    category: str
    description: str
    source_url: str  # APKMirror / official page — for "Open source page"
    homepage_url: str  # the app publisher's homepage

    def to_dict(self) -> dict:
        return asdict(self)


# Keep this list in sync with the UI. Picked for multi-account farming
# use cases: social + video + messaging + e-commerce.
CATALOG: list[CatalogEntry] = [
    CatalogEntry(
        slug="tiktok",
        display_name="TikTok",
        package="com.zhiliaoapp.musically",
        category="Video / Social",
        description="Short-form video social network.",
        source_url="https://www.apkmirror.com/apk/tiktok-pte-ltd/tik-tok/",
        homepage_url="https://www.tiktok.com",
    ),
    CatalogEntry(
        slug="instagram",
        display_name="Instagram",
        package="com.instagram.android",
        category="Social",
        description="Photo + Reels social network.",
        source_url="https://www.apkmirror.com/apk/instagram/instagram-instagram/",
        homepage_url="https://www.instagram.com",
    ),
    CatalogEntry(
        slug="facebook",
        display_name="Facebook",
        package="com.facebook.katana",
        category="Social",
        description="Facebook main app (feed, Marketplace, groups).",
        source_url="https://www.apkmirror.com/apk/facebook-2/facebook/",
        homepage_url="https://www.facebook.com",
    ),
    CatalogEntry(
        slug="youtube",
        display_name="YouTube",
        package="com.google.android.youtube",
        category="Video",
        description="YouTube video player.",
        source_url="https://www.apkmirror.com/apk/google-inc/youtube/",
        homepage_url="https://www.youtube.com",
    ),
    CatalogEntry(
        slug="twitter",
        display_name="X (Twitter)",
        package="com.twitter.android",
        category="Social",
        description="X / Twitter microblogging app.",
        source_url="https://www.apkmirror.com/apk/twitter-inc/twitter/",
        homepage_url="https://twitter.com",
    ),
    CatalogEntry(
        slug="whatsapp",
        display_name="WhatsApp",
        package="com.whatsapp",
        category="Messaging",
        description="WhatsApp Messenger.",
        source_url="https://www.apkmirror.com/apk/whatsapp-inc/whatsapp/",
        homepage_url="https://www.whatsapp.com",
    ),
    CatalogEntry(
        slug="telegram",
        display_name="Telegram",
        package="org.telegram.messenger",
        category="Messaging",
        description="Telegram Messenger.",
        source_url="https://www.apkmirror.com/apk/telegram-fz-llc/telegram/",
        homepage_url="https://telegram.org",
    ),
    CatalogEntry(
        slug="snapchat",
        display_name="Snapchat",
        package="com.snapchat.android",
        category="Social",
        description="Snapchat camera + messaging.",
        source_url="https://www.apkmirror.com/apk/snap-inc/snapchat/",
        homepage_url="https://www.snapchat.com",
    ),
    CatalogEntry(
        slug="reddit",
        display_name="Reddit",
        package="com.reddit.frontpage",
        category="Social",
        description="Reddit app.",
        source_url="https://www.apkmirror.com/apk/reddit-inc/reddit/",
        homepage_url="https://www.reddit.com",
    ),
    CatalogEntry(
        slug="discord",
        display_name="Discord",
        package="com.discord",
        category="Messaging",
        description="Discord chat + voice.",
        source_url="https://www.apkmirror.com/apk/discord-inc/discord/",
        homepage_url="https://discord.com",
    ),
    CatalogEntry(
        slug="gmail",
        display_name="Gmail",
        package="com.google.android.gm",
        category="Email",
        description="Google Gmail client.",
        source_url="https://www.apkmirror.com/apk/google-inc/gmail/",
        homepage_url="https://mail.google.com",
    ),
    CatalogEntry(
        slug="chrome",
        display_name="Chrome",
        package="com.android.chrome",
        category="Browser",
        description="Google Chrome browser.",
        source_url="https://www.apkmirror.com/apk/google-inc/chrome/",
        homepage_url="https://www.google.com/chrome/",
    ),
]


def list_catalog() -> list[dict]:
    return [e.to_dict() for e in CATALOG]


def get_entry(slug: str) -> CatalogEntry | None:
    for e in CATALOG:
        if e.slug == slug:
            return e
    return None
