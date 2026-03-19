use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

struct ServerProcess(Mutex<Option<Child>>);

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let python = find_python();
            let project_root = resolve_project_root();

            let child: Option<Child> = match (python, project_root) {
                (Some(py), Some(root)) => {
                    let script = root.join("tools").join("core_engine_cli.py");
                    match Command::new(&py)
                        .args([script.to_str().unwrap_or(""), "run-server"])
                        .current_dir(&root)
                        .spawn()
                    {
                        Ok(c) => {
                            println!("[BookEngine] Server started (python={py})");
                            Some(c)
                        }
                        Err(e) => {
                            eprintln!("[BookEngine] Failed to start server: {e}");
                            None
                        }
                    }
                }
                (None, _) => {
                    eprintln!("[BookEngine] Python not found — server not started");
                    None
                }
                (_, None) => {
                    eprintln!("[BookEngine] Project root not found — server not started");
                    None
                }
            };

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
