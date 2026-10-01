use std::{
    net::{SocketAddr, TcpStream},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

use tauri::Manager;

struct BackendProcess(Mutex<Option<Child>>);

const BACKEND_ADDRESS: &str = "127.0.0.1:8420";

fn ensure_backend_port_available() -> Result<(), String> {
    let address: SocketAddr = BACKEND_ADDRESS
        .parse()
        .map_err(|error| format!("Invalid backend address: {error}"))?;
    if TcpStream::connect_timeout(&address, Duration::from_millis(250)).is_ok() {
        return Err(format!(
            "Beatweave cannot start because {BACKEND_ADDRESS} is already in use. Close any stale Beatweave backend process and restart the app."
        ));
    }
    Ok(())
}

#[tauri::command]
fn reveal_file(path: String) -> Result<(), String> {
    let target = std::path::PathBuf::from(path);
    if !target.is_file() {
        return Err("The generated image file no longer exists.".to_string());
    }
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        Command::new("explorer")
            .arg(format!("/select,{}", target.display()))
            .creation_flags(0x08000000)
            .spawn()
            .map_err(|error| format!("Could not open Explorer: {error}"))?;
    }
    #[cfg(target_os = "macos")]
    Command::new("open")
        .args(["-R", &target.to_string_lossy()])
        .spawn()
        .map_err(|error| error.to_string())?;
    #[cfg(all(unix, not(target_os = "macos")))]
    Command::new("xdg-open")
        .arg(target.parent().unwrap_or(&target))
        .spawn()
        .map_err(|error| error.to_string())?;
    Ok(())
}

fn stop_backend(child: &mut Child) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;

        let status = Command::new("taskkill")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .creation_flags(0x08000000)
            .status();
        if !matches!(status, Ok(status) if status.success()) {
            let _ = child.kill();
        }
    }

    #[cfg(not(target_os = "windows"))]
    {
        let _ = child.kill();
    }

    let _ = child.wait();
}

fn spawn_backend(app: &tauri::App) -> Result<Child, String> {
    let manifest_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repository_root = manifest_dir
        .parent()
        .ok_or_else(|| "Could not locate the Beatweave repository root".to_string())?;
    let backend_dir = repository_root.join("backend");
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Could not resolve application data directory: {error}"))?;
    std::fs::create_dir_all(&data_dir)
        .map_err(|error| format!("Could not create application data directory: {error}"))?;

    let mut command = Command::new("uv");
    command
        .args(["run", "--project"])
        .arg(&backend_dir)
        .args(["python", "-m", "beatweave.main"])
        .current_dir(repository_root)
        .env("BEATWEAVE_DATA_DIR", data_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    command
        .spawn()
        .map_err(|error| format!("Failed to start the Beatweave backend with uv: {error}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![reveal_file])
        .setup(|app| {
            ensure_backend_port_available().map_err(std::io::Error::other)?;
            let mut child = spawn_backend(app).map_err(std::io::Error::other)?;
            thread::sleep(Duration::from_millis(500));
            if let Some(status) = child.try_wait()? {
                return Err(std::io::Error::other(format!(
                    "Beatweave backend exited during startup with {status}"
                ))
                .into());
            }
            app.manage(BackendProcess(Mutex::new(Some(child))));
            println!("Beatweave desktop and backend started");
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Beatweave");

    app.run(|handle, event| {
        if matches!(
            event,
            tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
        ) {
            let backend = handle.state::<BackendProcess>();
            if let Ok(mut process) = backend.0.lock() {
                if let Some(child) = process.as_mut() {
                    stop_backend(child);
                }
                *process = None;
            };
        }
    });
}
