#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
// 桌面应用入口:启动后端 sidecar + 注入端口给前端 + 生命周期管理。
// 经 cargo check 编译验证;完整运行验证待打包后做。详见 desktop/README.md。

use std::io::{BufRead, BufReader};
use std::net::TcpListener;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::Manager;

/// 127.0.0.1 上的空闲端口(传给 sidecar,比 uvicorn port=0 后取端口简单)。
fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0").expect("bind free port").local_addr().unwrap().port()
}

/// sidecar 进程句柄(退出时 kill)
struct SidecarState(Mutex<Option<Child>>);
/// setup 与 on_page_load 之间共享的端口
type SharedPort = Arc<Mutex<Option<u16>>>;

fn main() {
    let shared_port: SharedPort = Arc::new(Mutex::new(None));
    let port_for_load = shared_port.clone();
    let port_for_setup = shared_port.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState(Mutex::new(None)))
        .on_page_load(move |webview, _payload| {
            if let Some(p) = port_for_load.lock().unwrap().as_ref() {
                let _ = webview.eval(&format!("window.__SKILLTREE_PORT__='{}'", p));
            }
        })
        .setup(move |app| {
            let home = dirs::home_dir().expect("no home dir");
            let st_root = home.join(".skill-tree");
            let bin_dir = st_root.join("bin");
            let data_dir = st_root.join("data");
            std::fs::create_dir_all(&bin_dir).ok();
            std::fs::create_dir_all(&data_dir).ok();

            // 1. 解压 lark-cli 到 bin_dir
            let local_lark = bin_dir.join(if cfg!(windows) { "lark-cli.exe" } else { "lark-cli" });
            if !local_lark.exists() {
                let res_name = if cfg!(windows) { "lark-cli.exe" } else { "lark-cli" };
                if let Ok(rp) = app.path().resolve(res_name, tauri::path::BaseDirectory::Resource) {
                    std::fs::copy(&rp, &local_lark).ok();
                }
            }

            // 2. 找空闲端口,写入共享 state
            let port = free_port();
            *port_for_setup.lock().unwrap() = Some(port);

            // 3. spawn sidecar。打包:resource 目录 sidecar/;dev:src-tauri/sidecar/
            let sidecar_name = if cfg!(windows) { "skill-tree-backend.exe" } else { "skill-tree-backend" };
            let sidecar_exe = app
                .path()
                .resolve(format!("sidecar/{}", sidecar_name), tauri::path::BaseDirectory::Resource)
                .or_else(|_| {
                    let dev = std::env::current_dir()?.join("sidecar").join(sidecar_name);
                    if dev.exists() { Ok(dev) } else { Err(tauri::Error::Anyhow(anyhow::anyhow!("sidecar not found"))) }
                })
                .expect("resolve sidecar path");

            let mut child = Command::new(&sidecar_exe)
                .args(["--port", &port.to_string(), "--data-dir", data_dir.to_str().unwrap()])
                .env("SKILLTREE_BIN_DIR", bin_dir.to_str().unwrap())
                .stdout(Stdio::piped())
                .spawn()
                .expect("spawn sidecar");

            // 4. 读 stdout 等 READY:<port>(entry.py 打印)确认服务起来
            let stdout = child.stdout.take().expect("no sidecar stdout");
            let _ready: u16 = BufReader::new(stdout)
                .lines()
                .filter_map(|l| l.ok())
                .find_map(|l| l.strip_prefix("READY:").and_then(|s| s.trim().parse::<u16>().ok()))
                .expect("no READY:<port> from sidecar");

            *app.state::<SidecarState>().0.lock().unwrap() = Some(child);
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(s) = window.app_handle().try_state::<SidecarState>() {
                    if let Some(mut child) = s.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
