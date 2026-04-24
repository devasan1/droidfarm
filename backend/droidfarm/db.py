"""SQLite schema + session factory.

We use synchronous SQLAlchemy for simplicity — the sidecar is a single process
with light write volume and SQLite fits the 'durably persist phone + proxy
assignments across restarts' use case perfectly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from droidfarm.config import SETTINGS


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Proxy(Base):
    __tablename__ = "proxies"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String, default="", nullable=False)
    scheme: Mapped[str] = mapped_column(String, default="http", nullable=False)  # http | socks5
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    password: Mapped[str | None] = mapped_column(String, nullable=True)
    # geoIP data, populated on import / health-check
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    asn: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    # health
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # lifecycle
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    # denormalized: set when a phone reserves this proxy, cleared on release.
    # Guarantees uniqueness at the DB level via unique=True on phones.proxy_id.
    notes: Mapped[str] = mapped_column(String, default="", nullable=False)

    phone: Mapped[Phone | None] = relationship(back_populates="proxy", uselist=False)


class Phone(Base):
    __tablename__ = "phones"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # LDPlayer-side identifier; populated once the instance is created.
    ldplayer_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_profile: Mapped[str] = mapped_column(String, default="pixel-6", nullable=False)
    android_version: Mapped[str] = mapped_column(String, default="13", nullable=False)
    resolution: Mapped[str] = mapped_column(String, default="1080x1920", nullable=False)
    dpi: Mapped[int] = mapped_column(Integer, default=420)
    cpu: Mapped[int] = mapped_column(Integer, default=2)
    ram_mb: Mapped[int] = mapped_column(Integer, default=4096)

    # status is driven by the LDPlayer poll loop.
    status: Mapped[str] = mapped_column(String, default="stopped", nullable=False)
    # stopped | starting | running | stopping | crashed
    autostart: Mapped[bool] = mapped_column(Boolean, default=True)
    # When True, clone from the _droidfarm_template_factory (shows first-boot
    # setup wizard). When False (default), clone from _droidfarm_template_configured
    # (already past setup). In both cases the phone is data-clean on every
    # wipe / restart-with-wipe.
    show_setup_wizard: Mapped[bool] = mapped_column(Boolean, default=False)
    # Whether tun2socks / system proxy should be applied on boot.
    proxy_mode: Mapped[str] = mapped_column(String, default="tun2socks", nullable=False)
    # tun2socks | system-http | none

    # Unique 1:1 link to proxies; proxy_id is UNIQUE so two phones can never
    # share the same row.
    proxy_id: Mapped[int | None] = mapped_column(
        ForeignKey("proxies.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )
    proxy: Mapped[Proxy | None] = relationship(back_populates="phone")

    # Geo overrides applied at boot (locale/timezone/GPS). Free-form JSON so
    # we can add new fields without migrations.
    geo_overrides: Mapped[dict] = mapped_column(JSON, default=dict)

    # APKs to install as soon as the phone boots for the first time.
    preinstall_apks: Mapped[list[str]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    # Soft-delete marker. When set, the phone is hidden from the main
    # grid and its proxy is freed, but the LDPlayer instance and all
    # on-disk data are kept so Restore is lossless. Purge permanently
    # destroys the instance + row.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Apk(Base):
    __tablename__ = "apks"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    package_name: Mapped[str | None] = mapped_column(String, nullable=True)
    version_name: Mapped[str | None] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


_engine = create_engine(
    f"sqlite:///{SETTINGS.db_path}",
    future=True,
    # SQLite needs this for multi-threaded FastAPI.
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(_engine)
    _migrate_in_place()


def _migrate_in_place() -> None:
    """Tiny in-place migration: adds columns that SQLAlchemy's
    create_all doesn't back-fill onto tables that already exist. Cheaper
    than Alembic for a single-process desktop app."""
    from sqlalchemy import inspect, text

    insp = inspect(_engine)
    if "phones" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("phones")}
    with _engine.begin() as conn:
        if "deleted_at" not in cols:
            conn.execute(text("ALTER TABLE phones ADD COLUMN deleted_at DATETIME"))


@contextmanager
def session_scope() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
