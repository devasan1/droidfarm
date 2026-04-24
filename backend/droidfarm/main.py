"""FastAPI entrypoint."""

from __future__ import annotations

import logging

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from droidfarm import __version__
from droidfarm.api.routes_apks import router as apks_router
from droidfarm.api.routes_health import router as health_router
from droidfarm.api.routes_phones import router as phones_router
from droidfarm.api.routes_proxies import router as proxies_router
from droidfarm.config import SETTINGS
from droidfarm.db import init_db

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="DroidFarm",
        description="Desktop control plane for proxied Android emulators.",
        version=__version__,
    )

    # CORS for the Vite dev server.
    if SETTINGS.dev_mode:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health_router)
    app.include_router(phones_router)
    app.include_router(proxies_router)
    app.include_router(apks_router)

    # Serve the built React frontend at / (production bundle). The bat/
    # shell launcher runs `npm run build` in frontend/ before booting
    # the backend, so frontend/dist is expected to exist. When it
    # doesn't (e.g. pure backend dev), we return a helpful placeholder
    # so health still works.
    #
    # The launchers can also pin the dist path via DROIDFARM_STATIC_DIR
    # (useful for docker-compose + linux droidfarm.sh where the repo
    # layout at runtime may not match the build-tree relative guess).
    import os
    static_env = os.environ.get("DROIDFARM_STATIC_DIR")
    if static_env:
        dist = Path(static_env)
    else:
        dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(dist / "assets")),
            name="assets",
        )

        @app.get("/", include_in_schema=False)
        @app.get("/{full_path:path}", include_in_schema=False)
        def _spa(full_path: str = "") -> FileResponse:
            # SPA fallback — every non-API path returns index.html so
            # react-router can do its own routing client-side.
            if full_path.startswith("api/"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            return FileResponse(dist / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def _placeholder() -> dict:
            return {
                "ok": True,
                "message": (
                    "frontend/dist not built yet. Run `npm run build` in "
                    "frontend/, or use DroidFarm.bat which does it for you."
                ),
            }

    @app.on_event("startup")
    def _startup() -> None:
        init_db()
        logger.info("droidfarm %s listening on %s:%s", __version__, SETTINGS.host, SETTINGS.port)
        logger.info("data dir: %s", SETTINGS.data_dir)
        logger.info("mock driver: %s", SETTINGS.mock_driver)
        if SETTINGS.ldconsole_path:
            logger.info("ldconsole: %s", SETTINGS.ldconsole_path)
        else:
            logger.warning("ldconsole.exe not found; running with mock driver")
        _resume_autostart_phones()

    return app


def _resume_autostart_phones() -> None:
    """On backend boot, bring every phone that has ``autostart=True``
    back online. The user specified: 'keeps on running unless stopped' —
    this honors that across backend restarts and host reboots.

    Done through the normal start pipeline so template preparation,
    geo-spoof, and proxy assignment all fire just like manual starts.
    """
    from droidfarm.api.routes_phones import _start_in_background
    from droidfarm.db import Phone, session_scope
    from sqlalchemy import select

    try:
        with session_scope() as s:
            ids = [
                row[0]
                for row in s.execute(
                    select(Phone.id).where(
                        Phone.autostart.is_(True),
                        Phone.status != "running",
                        Phone.deleted_at.is_(None),
                    )
                ).all()
            ]
            # Pre-flip the status so the UI shows 'starting' immediately.
            for pid in ids:
                p = s.get(Phone, pid)
                if p is not None:
                    p.status = "starting"
                    p.last_error = None
        for pid in ids:
            logger.info("autostart: resuming phone id=%s", pid)
            _start_in_background(pid)
    except Exception as e:
        logger.warning("autostart scan failed: %s", e)


app = create_app()


def main() -> None:
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(
        "droidfarm.main:app",
        host=SETTINGS.host,
        port=SETTINGS.port,
        reload=SETTINGS.dev_mode,
    )


if __name__ == "__main__":
    main()
