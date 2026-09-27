use std::{
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

use tauri::Manager;

struct BackendProcess(Mutex<Option<Child>>);

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
        .setup(|app| {
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
                    let _ = child.kill();
                    let _ = child.wait();
                }
                *process = None;
            };
        }
    });
}
