"""Template instance management — "clean phone, ready to clone".

Every phone the user adds is a *copy* of one of two hidden templates:

* ``_droidfarm_template_factory``   — never booted past the first-run
  setup wizard. Cloning it produces a phone that shows the usual
  "Welcome", language-picker, Wi-Fi-opt-in, Google-account screens.

* ``_droidfarm_template_configured`` — booted once, then the setup
  wizard is dismissed via adb (``device_provisioned=1``,
  ``user_setup_complete=1``, SetupWizard component disabled) and the
  instance is shut down again. Cloning produces a phone that boots
  straight to the default launcher with no on-boarding.

Both templates contain **no user data / apps / cache** beyond what
ships with LDPlayer's stock Android image; they're literally "fresh
phone, first boot state" with the configured variant just past the
wizard gate.

Preparation runs once per Windows VM, on the first backend start with
a real (non-mock) driver available. The result is a persistent record
in ``<data_dir>/templates.json`` so subsequent boots skip the work.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from droidfarm.core import adb as adb_mod
from droidfarm.core.driver import (
    TEMPLATE_CONFIGURED_NAME,
    TEMPLATE_FACTORY_NAME,
    Driver,
    LaunchOptions,
)

logger = logging.getLogger(__name__)

_PREPARE_LOCK = threading.Lock()

# adb commands that move the emulator state past the setup wizard. Run
# in order after the phone reports boot-complete. Uses 'settings put'
# + 'pm disable' which are both available on stock AOSP.
_SKIP_SETUP_CMDS = [
    ("settings", "put", "global", "device_provisioned", "1"),
    ("settings", "put", "secure", "user_setup_complete", "1"),
    ("pm", "disable-user", "--user", "0", "com.google.android.setupwizard"),
    ("pm", "disable-user", "--user", "0", "com.android.provision"),
]


def _state_path(data_dir: Path) -> Path:
    return data_dir / "templates.json"


def _load_state(data_dir: Path) -> dict:
    p = _state_path(data_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save_state(data_dir: Path, state: dict) -> None:
    p = _state_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))


def _wait_boot_complete(driver: Driver, name: str, timeout_s: float = 180.0) -> str:
    """Wait until the phone reports sys.boot_completed=1. Returns the
    adb serial string so callers can run subsequent adb commands."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        inst = next((i for i in driver.list() if i.name == name), None)
        if inst and inst.status == "running" and inst.adb_port:
            serial = f"127.0.0.1:{inst.adb_port}"
            try:
                adb_mod.connect(serial)
                out = adb_mod.shell(serial, "getprop", "sys.boot_completed", timeout=10).strip()
                if out == "1":
                    return serial
            except Exception:
                pass
        time.sleep(3)
    raise TimeoutError(f"{name} did not finish booting within {timeout_s:.0f}s")


def _run_skip_setup(serial: str) -> None:
    for cmd in _SKIP_SETUP_CMDS:
        try:
            adb_mod.shell(serial, *cmd)
        except Exception as e:
            logger.warning("skip-setup step %s failed: %s", cmd, e)


def _ensure_factory_template(driver: Driver) -> None:
    """Create (if missing) the clean 'factory' template — just an empty
    instance with no boot/customization at all."""
    existing = next((i for i in driver.list() if i.name == TEMPLATE_FACTORY_NAME), None)
    if existing is not None:
        return
    driver.create(TEMPLATE_FACTORY_NAME, LaunchOptions())
    logger.info("created factory template %s", TEMPLATE_FACTORY_NAME)


def _ensure_configured_template(driver: Driver) -> None:
    """Boot the factory template once, dismiss the setup wizard, shut it
    down — that becomes the 'configured' template."""
    existing = next((i for i in driver.list() if i.name == TEMPLATE_CONFIGURED_NAME), None)
    if existing is not None:
        return
    # Derive from the factory template so we don't repeat the base setup.
    opts = LaunchOptions()
    driver.clone(TEMPLATE_CONFIGURED_NAME, TEMPLATE_FACTORY_NAME, opts)
    logger.info("cloning configured template %s from factory — booting to dismiss setup wizard",
                TEMPLATE_CONFIGURED_NAME)
    driver.start(TEMPLATE_CONFIGURED_NAME, opts)
    try:
        serial = _wait_boot_complete(driver, TEMPLATE_CONFIGURED_NAME)
        logger.info("configured template booted, running skip-setup sequence")
        _run_skip_setup(serial)
        time.sleep(3)  # let settings propagate
    finally:
        driver.stop(TEMPLATE_CONFIGURED_NAME)
    logger.info("configured template ready")


def ensure_templates(driver: Driver, data_dir: Path) -> dict:
    """Top-level entrypoint — idempotent, thread-safe.

    Runs on first phone creation (or explicit admin ping) to make sure
    both templates exist. Records prep metadata in templates.json so
    restarts skip the work.
    """
    with _PREPARE_LOCK:
        state = _load_state(data_dir)
        if state.get("factory_ready") and state.get("configured_ready"):
            return state

        try:
            _ensure_factory_template(driver)
            state["factory_ready"] = True
            _save_state(data_dir, state)
        except Exception as e:
            logger.error("factory template prep failed: %s", e)
            state["factory_error"] = str(e)
            _save_state(data_dir, state)
            return state

        try:
            _ensure_configured_template(driver)
            state["configured_ready"] = True
            _save_state(data_dir, state)
        except Exception as e:
            logger.error("configured template prep failed: %s", e)
            state["configured_error"] = str(e)
            _save_state(data_dir, state)

        return state


def source_template_for(skip_setup: bool) -> str:
    """Pick which template a new phone should be cloned from."""
    return TEMPLATE_CONFIGURED_NAME if skip_setup else TEMPLATE_FACTORY_NAME


def wipe_from_template(driver: Driver, phone_name: str, source: str, opts: LaunchOptions) -> None:
    """Factory-reset a phone by destroying and re-cloning it from the
    source template. Preserves the LaunchOptions (IMEI / Android ID /
    resolution / etc.) so fingerprint signals survive the wipe.
    """
    try:
        driver.stop(phone_name)
    except Exception:
        pass
    time.sleep(2)
    driver.destroy(phone_name)
    time.sleep(1)
    driver.clone(phone_name, source, opts)
