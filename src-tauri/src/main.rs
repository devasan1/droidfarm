// DroidFarm Tauri desktop shell.
//
// Starts the Python backend as a child process, waits for it to
// respond on http://localhost:7870, then the Tauri window (declared
// in tauri.conf.json) loads that URL so the user sees the same
// browser UI Linux users get — just wrapped in a native window.
//
// First-run expectation: the installer (MSI/NSIS) has placed the
// backend source tree next to the .exe via tauri.conf.json's
// `bundle.resources`. Python 3.11+ must be on PATH — the NSIS
// installer offers to run `DroidFarm.bat` which installs Python
// silently via winget if needed.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use tauri::{Manager, State};

struct BackendHandle(Mutex<Option<Child>>);

fn find_python() -> Option<String> {
    for candidate in [
        "backend/.venv/Scripts/python.exe",
        "backend\\.venv\\Scripts\\python.exe",
        "py",
        "python",
        "python3",
    ] {
        let status = Command::new(candidate)
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        if matches!(status, Ok(s) if s.success()) {
            return Some(candidate.to_string());
        }
    }
    None
}

fn spawn_backend(resource_dir: &std::path::Path) -> Result<Child, String> {
    let py = find_python().ok_or_else(|| {
        "Python 3.11+ not found on PATH. Run DroidFarm.bat once to \
         provision the venv, or install Python 3.11 and retry."
            .to_string()
    })?;
    let backend_dir = resource_dir.join("backend");
    Command::new(py)
        .current_dir(&backend_dir)
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
        let ok = std::net::TcpStream::connect("127.0.0.1:7870").is_ok();
        if ok {
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
            match spawn_backend(&resource_dir) {
                Ok(child) => {
                    let handle: State<'_, BackendHandle> = app.state();
                    *handle.0.lock().unwrap() = Some(child);
                }
                Err(msg) => {
                    eprintln!("[droidfarm] backend failed to launch: {msg}");
                }
            }
            // Block the setup hook briefly while the backend comes up
            // so the first page load succeeds.
            let _ready = wait_for_backend(30);
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let handle: State<'_, BackendHandle> = window.app_handle().state();
                if let Some(mut child) = handle.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running DroidFarm");
}
