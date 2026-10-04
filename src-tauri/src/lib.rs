use std::{
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

use serde::Serialize;
use tauri::{AppHandle, Manager, State};

struct BackendProcess(Mutex<Option<Child>>);
struct McpProcess(Mutex<Option<Child>>);

const BACKEND_ADDRESS: &str = "127.0.0.1:8420";
const MCP_ADDRESS: &str = "127.0.0.1:8421";
const MCP_URL: &str = "http://127.0.0.1:8421/mcp";

#[derive(Serialize)]
struct McpStatus {
    running: bool,
    url: &'static str,
    message: String,
}

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

fn is_address_reachable(address: &str) -> bool {
    address.parse::<SocketAddr>().ok().is_some_and(|address| {
        TcpStream::connect_timeout(&address, Duration::from_millis(250)).is_ok()
    })
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

#[tauri::command]
fn open_file_location(path: String) -> Result<(), String> {
    let target = std::path::PathBuf::from(path);
    if !target.is_file() {
        return Err("The file no longer exists.".to_string());
    }
    let directory = target
        .parent()
        .ok_or_else(|| "Could not determine the file's directory.".to_string())?;
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        Command::new("explorer")
            .arg(directory)
            .creation_flags(0x08000000)
            .spawn()
            .map_err(|error| format!("Could not open Explorer: {error}"))?;
    }
    #[cfg(target_os = "macos")]
    Command::new("open")
        .arg(directory)
        .spawn()
        .map_err(|error| error.to_string())?;
    #[cfg(all(unix, not(target_os = "macos")))]
    Command::new("xdg-open")
        .arg(directory)
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

fn packaged_tool_path(executable_dir: &Path, name: &str) -> PathBuf {
    executable_dir.join(format!("{name}{}", std::env::consts::EXE_SUFFIX))
}

fn spawn_packaged_backend(app: &tauri::App, backend_path: &Path) -> Result<Child, String> {
    let executable_dir = backend_path
        .parent()
        .ok_or_else(|| "Could not locate the packaged Beatweave tools".to_string())?;
    let ffmpeg_path = packaged_tool_path(executable_dir, "ffmpeg");
    let ffprobe_path = packaged_tool_path(executable_dir, "ffprobe");
    for (name, path) in [("FFmpeg", &ffmpeg_path), ("ffprobe", &ffprobe_path)] {
        if !path.is_file() {
            return Err(format!(
                "Packaged {name} executable is missing: {}",
                path.display()
            ));
        }
    }

    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Could not resolve application data directory: {error}"))?;
    std::fs::create_dir_all(&data_dir)
        .map_err(|error| format!("Could not create application data directory: {error}"))?;

    let mut command = Command::new(backend_path);
    command
        .env("BEATWEAVE_DATA_DIR", data_dir)
        .env("BEATWEAVE_FFMPEG_PATH", ffmpeg_path)
        .env("BEATWEAVE_FFPROBE_PATH", ffprobe_path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    command
        .spawn()
        .map_err(|error| format!("Failed to start the packaged Beatweave backend: {error}"))
}

fn spawn_backend(app: &tauri::App) -> Result<Child, String> {
    if !cfg!(debug_assertions) {
        let executable = std::env::current_exe()
            .map_err(|error| format!("Could not locate the Beatweave executable: {error}"))?;
        if let Some(executable_dir) = executable.parent() {
            let packaged_backend = packaged_tool_path(executable_dir, "beatweave-backend");
            if packaged_backend.is_file() {
                return spawn_packaged_backend(app, &packaged_backend);
            }
        }
        return Err("The packaged Beatweave backend is missing. Reinstall Beatweave.".to_string());
    }

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

fn spawn_mcp_server(app: &AppHandle) -> Result<Child, String> {
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Could not resolve application data directory: {error}"))?;
    std::fs::create_dir_all(&data_dir)
        .map_err(|error| format!("Could not create application data directory: {error}"))?;

    let mut command;
    if !cfg!(debug_assertions) {
        let executable = std::env::current_exe()
            .map_err(|error| format!("Could not locate the Beatweave executable: {error}"))?;
        let executable_dir = executable
            .parent()
            .ok_or_else(|| "Could not locate the packaged Beatweave tools".to_string())?;
        let mcp_path = packaged_tool_path(executable_dir, "beatweave-mcp");
        if !mcp_path.is_file() {
            return Err(
                "The packaged Beatweave MCP server is missing. Reinstall Beatweave.".to_string(),
            );
        }
        command = Command::new(mcp_path);
    } else {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let repository_root = manifest_dir
            .parent()
            .ok_or_else(|| "Could not locate the Beatweave repository root".to_string())?;
        let backend_dir = repository_root.join("backend");
        command = Command::new("uv");
        command
            .args(["run", "--project"])
            .arg(backend_dir)
            .args(["--group", "mcp", "beatweave-mcp"])
            .current_dir(repository_root);
    }

    command
        .args([
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            "8421",
        ])
        .env("BEATWEAVE_DATA_DIR", data_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    command
        .spawn()
        .map_err(|error| format!("Failed to start the Beatweave MCP server: {error}"))
}

fn current_mcp_status(process: &mut Option<Child>) -> Result<McpStatus, String> {
    if let Some(child) = process.as_mut() {
        match child.try_wait() {
            Ok(None) => {
                return Ok(McpStatus {
                    running: true,
                    url: MCP_URL,
                    message: "The MCP server is accepting local client connections.".to_string(),
                });
            }
            Ok(Some(_)) => *process = None,
            Err(error) => return Err(format!("Could not inspect the MCP server: {error}")),
        }
    }
    Ok(McpStatus {
        running: false,
        url: MCP_URL,
        message: "The MCP server is stopped.".to_string(),
    })
}

#[tauri::command]
fn mcp_status(state: State<'_, McpProcess>) -> Result<McpStatus, String> {
    let mut process = state
        .0
        .lock()
        .map_err(|_| "Could not access the MCP process state.".to_string())?;
    current_mcp_status(&mut process)
}

#[tauri::command]
fn start_mcp_server(app: AppHandle, state: State<'_, McpProcess>) -> Result<McpStatus, String> {
    let mut process = state
        .0
        .lock()
        .map_err(|_| "Could not access the MCP process state.".to_string())?;
    if current_mcp_status(&mut process)?.running {
        return current_mcp_status(&mut process);
    }
    if is_address_reachable(MCP_ADDRESS) {
        return Err(format!(
            "Cannot start the MCP server because {MCP_ADDRESS} is already in use."
        ));
    }

    let mut child = spawn_mcp_server(&app)?;
    for _ in 0..100 {
        thread::sleep(Duration::from_millis(100));
        if let Some(status) = child
            .try_wait()
            .map_err(|error| format!("Could not inspect the MCP server: {error}"))?
        {
            return Err(format!(
                "The MCP server exited during startup with {status}."
            ));
        }
        if is_address_reachable(MCP_ADDRESS) {
            *process = Some(child);
            return current_mcp_status(&mut process);
        }
    }
    stop_backend(&mut child);
    Err("The MCP server did not become ready within 10 seconds.".to_string())
}

#[tauri::command]
fn stop_mcp_server(state: State<'_, McpProcess>) -> Result<McpStatus, String> {
    let mut process = state
        .0
        .lock()
        .map_err(|_| "Could not access the MCP process state.".to_string())?;
    if let Some(child) = process.as_mut() {
        stop_backend(child);
    }
    *process = None;
    current_mcp_status(&mut process)
}

#[cfg(test)]
mod tests {
    use super::packaged_tool_path;
    use std::path::Path;

    #[test]
    fn packaged_tools_preserve_install_paths_with_spaces() {
        let directory = Path::new(r"C:\Users\Example User\App Data\Beatweave");
        assert_eq!(
            packaged_tool_path(directory, "beatweave-backend"),
            directory.join(format!("beatweave-backend{}", std::env::consts::EXE_SUFFIX))
        );
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            reveal_file,
            open_file_location,
            mcp_status,
            start_mcp_server,
            stop_mcp_server
        ])
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
            app.manage(McpProcess(Mutex::new(None)));
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
            let mcp = handle.state::<McpProcess>();
            if let Ok(mut process) = mcp.0.lock() {
                if let Some(child) = process.as_mut() {
                    stop_backend(child);
                }
                *process = None;
            };
        }
    });
}
