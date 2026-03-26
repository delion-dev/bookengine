use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

struct ServerProcess(Mutex<Option<Child>>);

/// Resolve the bundled sidecar binary path.
///
/// Tauri places `externalBin` entries (with triple suffix stripped) next to
/// the main executable when installed. We look for:
///   <exe_dir>/book_engine_server.exe    (Windows, installed)
///   <exe_dir>/book_engine_server         (macOS/Linux, installed)
///   <project_root>/frontend/src-tauri/binaries/book_engine_server[-triple].exe  (dev)
fn find_sidecar(app: &tauri::App) -> Option<PathBuf> {
    // 1. Installed: same directory as the main executable
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let candidates = [
                dir.join("book_engine_server.exe"),
                dir.join("book_engine_server"),
            ];
            for c in &candidates {
                if c.exists() {
                    return Some(c.clone());
                }
            }
        }
    }

    // 2. Development build: project_root/frontend/src-tauri/binaries/
    if let Ok(exe) = std::env::current_exe() {
        if let Some(root) = exe.ancestors().nth(5) {
            let binaries_dir = root.join("frontend").join("src-tauri").join("binaries");
            if let Ok(entries) = fs::read_dir(&binaries_dir) {
                for entry in entries.flatten() {
                    let name = entry.file_name();
                    let name_str = name.to_string_lossy();
                    if name_str.starts_with("book_engine_server") {
                        return Some(entry.path());
                    }
                }
            }
        }
    }

    None
}

/// Find a working Python executable on PATH.
fn find_python() -> Option<String> {
    for candidate in &["python", "python3", "py"] {
        if Command::new(candidate)
            .arg("--version")
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
        {
            return Some(candidate.to_string());
        }
    }
    None
}

/// Read project_root from %APPDATA%\BookEngine\config.json.
/// Falls back to guessing from the exe path (works in dev builds).
fn resolve_project_root() -> Option<PathBuf> {
    // 1. Config file
    if let Some(appdata) = dirs_next::data_dir() {
        let config_path = appdata.join("BookEngine").join("config.json");
        if let Ok(contents) = fs::read_to_string(&config_path) {
            if let Ok(val) = serde_json::from_str::<serde_json::Value>(&contents) {
                if let Some(root) = val["project_root"].as_str() {
                    let p = PathBuf::from(root);
                    if p.exists() {
                        return Some(p);
                    }
                }
            }
        }
    }

    // 2. Dev fallback: exe is at <root>/frontend/src-tauri/target/[profile]/book-engine.exe
    //    So root = exe.ancestors().nth(5)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(root) = exe.ancestors().nth(5) {
            let candidate = root.to_path_buf();
            if candidate.join("tools").join("core_engine_cli.py").exists() {
                return Some(candidate);
            }
        }
    }

    None
}

/// Spawn the server process, preferring the bundled sidecar over system Python.
///
/// Priority:
///   1. Bundled PyInstaller sidecar (book_engine_server.exe) — no Python required
///   2. System Python + core_engine_cli.py               — dev / source installs
fn spawn_server(app: &tauri::App) -> Option<Child> {
    // --- Strategy 1: bundled sidecar ---
    if let Some(sidecar) = find_sidecar(app) {
        match Command::new(&sidecar)
            .args(["--host", "127.0.0.1", "--port", "8000"])
            .spawn()
        {
            Ok(child) => {
                println!("[BookEngine] Server started via sidecar: {}", sidecar.display());
                return Some(child);
            }
            Err(e) => {
                eprintln!("[BookEngine] Sidecar found but failed to start: {e}");
                // Fall through to Python fallback
            }
        }
    }

    // --- Strategy 2: system Python ---
    let python = find_python();
    let project_root = resolve_project_root();
    match (python, project_root) {
        (Some(py), Some(root)) => {
            let script = root.join("tools").join("core_engine_cli.py");
            match Command::new(&py)
                .args([script.to_str().unwrap_or(""), "run-server"])
                .current_dir(&root)
                .spawn()
            {
                Ok(child) => {
                    println!("[BookEngine] Server started via system Python ({py})");
                    Some(child)
                }
                Err(e) => {
                    eprintln!("[BookEngine] Failed to start server via Python: {e}");
                    None
                }
            }
        }
        (None, _) => {
            eprintln!("[BookEngine] No sidecar and Python not found — server not started");
            None
        }
        (_, None) => {
            eprintln!("[BookEngine] No sidecar and project root not found — server not started");
            None
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let child = spawn_server(app);
            app.manage(ServerProcess(Mutex::new(child)));
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<ServerProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                            println!("[BookEngine] Server stopped");
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application")
}
