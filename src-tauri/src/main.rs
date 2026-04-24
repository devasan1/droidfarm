// DroidFarm Tauri desktop shell.
//
// On first launch, the shell creates a per-user venv under
// %LOCALAPPDATA%\DroidFarm\venv (or ~/.droidfarm/venv on *nix), pip-installs
// the bundled backend into it, and spawns ``python -m droidfarm``. The venv
// is reused on subsequent launches so the second boot is ~3 seconds.
//
// The backend source tree is placed next to the .exe via tauri.conf.json's
// ``bundle.resources``. Python 3.10+ must be on PATH — the NSIS installer
// offers to run ``DroidFarm.bat`` which installs Python silently via winget
// if needed.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use tauri::{Manager, State};

struct BackendHandle(Mutex<Option<Child>>);

/// Where to put the per-user venv + marker files. Writable without admin.
fn user_state_dir() -> PathBuf {
    if cfg!(windows) {
        if let Ok(local) = std::env::var("LOCALAPPDATA") {
            return PathBuf::from(local).join("DroidFarm");
        }
        if let Ok(appdata) = std::env::var("APPDATA") {
            return PathBuf::from(appdata).join("DroidFarm");
        }
    }
    match std::env::var("HOME") {
        Ok(h) => PathBuf::from(h).join(".droidfarm"),
        Err(_) => PathBuf::from(".droidfarm"),
    }
}

/// Path to the python inside a venv dir. Platform-specific layout.
fn venv_python(venv_dir: &Path) -> PathBuf {
    if cfg!(windows) {
        venv_dir.join("Scripts").join("python.exe")
    } else {
        venv_dir.join("bin").join("python")
    }
}

/// Find a system Python usable for bootstrapping a venv. Prefers the
/// ``py`` launcher on Windows (which can resolve 3.11 specifically),
/// falls back to ``python`` / ``python3`` on PATH.
fn find_bootstrap_python() -> Option<String> {
    let candidates: &[&[&str]] = if cfg!(windows) {
        &[&["py", "-3.11"], &["py", "-3"], &["py"], &["python"], &["python3"]]
    } else {
        &[&["python3.11"], &["python3"], &["python"]]
    };
    for argv in candidates {
        let mut cmd = Command::new(argv[0]);
        for a in &argv[1..] {
            cmd.arg(a);
        }
        let status = cmd
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        if matches!(status, Ok(s) if s.success()) {
            // Re-encode the found command as a single shell-style string
            // so the caller can split it back. We keep argv joined with \0
            // internally but the spawner re-parses via space split after we
            // return a human string. For simplicity, callers get the first
            // token and we pass the rest via a parallel function.
            return Some(argv.join(" "));
        }
    }
    None
}

/// Split a command string produced by ``find_bootstrap_python`` back into
/// program + args. Only handles the simple space-delimited forms we emit
/// above; do not feed arbitrary user input.
fn split_cmd(s: &str) -> (String, Vec<String>) {
    let mut parts = s.split_whitespace();
    let prog = parts.next().unwrap_or("").to_string();
    let args: Vec<String> = parts.map(|p| p.to_string()).collect();
    (prog, args)
}

/// Create the venv if missing and pip-install the bundled backend into it.
/// Returns the path to the venv's python on success. Idempotent: if the
/// marker file exists from a previous successful install, does nothing.
fn ensure_venv(venv_dir: &Path, backend_dir: &Path) -> Result<PathBuf, String> {
    std::fs::create_dir_all(venv_dir.parent().unwrap_or(Path::new(".")))
        .map_err(|e| format!("create state dir: {e}"))?;

    let py_in_venv = venv_python(venv_dir);
    let marker = venv_dir.join(".droidfarm-backend-installed");
    if py_in_venv.exists() && marker.exists() {
        return Ok(py_in_venv);
    }

    if !py_in_venv.exists() {
        let boot = find_bootstrap_python().ok_or_else(|| {
            "Python 3.11 not found on PATH. Install Python 3.11 from \
             https://www.python.org/downloads/ (or run DroidFarm.bat once) \
             and relaunch DroidFarm."
                .to_string()
        })?;
        let (prog, args) = split_cmd(&boot);
        eprintln!("[droidfarm] creating venv at {}", venv_dir.display());
        let status = Command::new(&prog)
            .args(&args)
            .arg("-m")
            .arg("venv")
            .arg(venv_dir)
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .status()
            .map_err(|e| format!("venv spawn failed: {e}"))?;
        if !status.success() {
            return Err(format!("venv creation exited with status {status}"));
        }
    }

    eprintln!("[droidfarm] upgrading pip in venv");
    let status = Command::new(&py_in_venv)
        .args(["-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check"])
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status()
        .map_err(|e| format!("pip upgrade spawn: {e}"))?;
    if !status.success() {
        // Non-fatal: old pip can still install most wheels.
        eprintln!("[droidfarm] pip upgrade returned {status}; continuing");
    }

    eprintln!(
        "[droidfarm] pip install -e {} (first-run; ~30-60s)",
        backend_dir.display()
    );
    let status = Command::new(&py_in_venv)
        .args(["-m", "pip", "install", "--disable-pip-version-check", "-e"])
        .arg(backend_dir)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status()
        .map_err(|e| format!("pip install backend spawn: {e}"))?;
    if !status.success() {
        return Err(format!("pip install backend exited with status {status}"));
    }

    std::fs::write(&marker, "ok\n").map_err(|e| format!("write marker: {e}"))?;
    Ok(py_in_venv)
}

fn spawn_backend(python: &Path, backend_dir: &Path, static_dir: &Path) -> Result<Child, String> {
    Command::new(python)
        .current_dir(backend_dir)
        .env("DROIDFARM_STATIC_DIR", static_dir)
        .arg("-m")
        .arg("droidfarm")
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|e| format!("failed to start backend: {e}"))
}

fn wait_for_backend(timeout_secs: u64) -> bool {
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);
    while Instant::now() < deadline {
        if std::net::TcpStream::connect("127.0.0.1:7870").is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(250));
    }
    false
}

fn main() {
    tauri::Builder::default()
        .manage(BackendHandle(Mutex::new(None)))
        .setup(|app| {
            let resource_dir = app.path().resource_dir()?;
            let backend_dir = resource_dir.join("backend");
            let static_dir = resource_dir.join("frontend").join("dist");
            let venv_dir = user_state_dir().join("venv");

            match ensure_venv(&venv_dir, &backend_dir) {
                Ok(python) => match spawn_backend(&python, &backend_dir, &static_dir) {
                    Ok(child) => {
                        let handle: State<'_, BackendHandle> = app.state();
                        *handle.0.lock().unwrap() = Some(child);
                    }
                    Err(msg) => {
                        eprintln!("[droidfarm] backend failed to launch: {msg}");
                    }
                },
                Err(msg) => {
                    eprintln!("[droidfarm] backend provisioning failed: {msg}");
                }
            }

            // First-run install can be slow; give it plenty of time.
            // Subsequent boots hit the fast path and return in <5s.
            let _ready = wait_for_backend(120);
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let handle: State<'_, BackendHandle> = window.app_handle().state();
                let mut guard = handle.0.lock().unwrap();
                if let Some(mut child) = guard.take() {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running DroidFarm");
}
