"""Basic smoke tests for the API."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Redirect data dir to a tmp path BEFORE importing the app so SQLite + apks
# get written somewhere isolated.
_TMP = Path(tempfile.mkdtemp(prefix="droidfarm-test-"))
os.environ["DROIDFARM_DATA_DIR"] = str(_TMP)
os.environ["DROIDFARM_MOCK"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from droidfarm.db import init_db  # noqa: E402
from droidfarm.main import app  # noqa: E402

init_db()
client = TestClient(app)


def test_health() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mock_driver"] is True


def test_proxy_import_and_phone_creation() -> None:
    r = client.post(
        "/api/proxies/import",
        json={
            "text": "\n".join(
                [
                    "user1:pass1@10.0.0.1:8080",
                    "socks5://u:p@10.0.0.2:1080",
                    "10.0.0.3:3128",
                    "# comment ignored",
                    "",
                    "not a proxy line",
                ]
            ),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 3
    assert body["skipped"] == 1

    proxies = client.get("/api/proxies").json()
    assert len(proxies) == 3
    first = proxies[0]
    assert first["host"] == "10.0.0.1"
    assert first["assigned_to_phone_id"] is None

    # Create a phone, auto-assign a proxy (autostart=False so the status
    # stays deterministic during the test).
    r = client.post(
        "/api/phones",
        json={"name": "phone-01", "auto_assign_proxy": True, "autostart": False},
    )
    assert r.status_code == 201, r.text
    phone = r.json()
    assert phone["proxy"] is not None
    assert phone["proxy"]["id"] == first["id"]

    # A second phone must get a *different* proxy.
    r = client.post(
        "/api/phones",
        json={"name": "phone-02", "auto_assign_proxy": True, "autostart": False},
    )
    assert r.status_code == 201
    phone2 = r.json()
    assert phone2["proxy"]["id"] != phone["proxy"]["id"]

    # Trying to reserve an already-taken proxy must fail.
    r = client.post(
        "/api/phones",
        json={"name": "phone-03", "proxy_id": phone["proxy"]["id"], "autostart": False},
    )
    assert r.status_code == 409

    # Duplicate phone name must fail.
    r = client.post("/api/phones", json={"name": "phone-01", "autostart": False})
    assert r.status_code == 409


def test_lifecycle_transitions() -> None:
    r = client.post("/api/phones", json={"name": "phone-99", "autostart": False})
    phone_id = r.json()["id"]
    assert r.json()["status"] == "stopped"

    r = client.post(f"/api/phones/{phone_id}/start")
    assert r.json()["status"] == "starting"

    r = client.post(f"/api/phones/{phone_id}/stop")
    assert r.json()["status"] == "stopping"
