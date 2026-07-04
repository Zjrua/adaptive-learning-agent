#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
// 桌面应用入口:启动后端 sidecar + 注入端口给前端 + 生命周期管理。
//
// ⚠ 本文件未经实跑验证(本会话环境无 Rust/Tauri 工具链)。
//   首次 cargo tauri build 时可能需要调整:
//   - sidecar 可执行文件的实际路径(current_exe().parent() + sidecar 名)
//   - lark-cli resource 路径解析(BaseDirectory::Resource)
//   - 端口注入时序(READY 等待)
//   详见 desktop/README.md 的常见报错排查。

use std::io::{BufRead, BufReader};
use std::net::TcpListener;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;

/// 找一个 127.0.0.1 上的空闲端口传给 sidecar(比 uvicorn port=0 后取端口简单)。
fn free_port() -> u16 {
    let l = TcpListener::bind("127.0.0.1:0").expect("bind free port");
    l.local_addr().unwrap().port()
}

struct SidecarState(Mutex<Option<Child>>);

fn main() {
    // 用 tauri::State 托管 sidecar 句柄,app 退出时 kill
    let sidecar_holder = SidecarState(Mutex::new(None));

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(sidecar_holder)
        .setup(|app| {
            // 1. 用户主目录下的 .skill-tree/bin 放 lark-cli
            let home = dirs::home_dir().expect("no home dir");
            let st_root = home.join(".skill-tree");
            let bin_dir = st_root.join("bin");
            let data_dir = st_root.join("data");
            std::fs::create_dir_all(&bin_dir).ok();
            std::fs::create_dir_all(&data_dir).ok();

            // 解压 resources 里的 lark-cli 到 bin_dir
            let local_lark = bin_dir.join(if cfg!(windows) { "lark-cli.exe" } else { "lark-cli" });
            if !local_lark.exists() {
                if let Ok(resource_path) = app.path().resolve(
                    if cfg!(windows) { "resources/lark-cli.exe" } else { "resources/lark-cli" },
                    tauri::path::BaseDirectory::Resource,
                ) {
                    std::fs::copy(&resource_path, &local_lark).ok();
                }
            }

            // 2. 找空闲端口
            let port = free_port();

            // 3. spawn 后端 sidecar。
            //    打包后:sidecar 在 Tauri resource 目录(sidecar/skill-tree-backend.exe)
            //    dev 模式:在 src-tauri/sidecar/skill-tree-backend.exe
            let sidecar_name = if cfg!(windows) { "skill-tree-backend.exe" } else { "skill-tree-backend" };
            let sidecar_exe = app
                .path()
                .resolve(format!("sidecar/{}", sidecar_name), tauri::path::BaseDirectory::Resource)
                .or_else(|_| {
                    // dev 模式回退:src-tauri/sidecar/
                    let dev_path = std::env::current_dir()
                        .map(|p| p.join("sidecar").join(sidecar_name))?;
                    if dev_path.exists() {
                        Ok(dev_path)
                    } else {
                        Err(tauri::Error::Anyhow(anyhow::anyhow!("sidecar not found")))
                    }
                })
                .expect("resolve sidecar path");

            let mut child = Command::new(&sidecar_exe)
                .args([
                    "--port", &port.to_string(),
                    "--data-dir", data_dir.to_str().unwrap(),
                ])
                .env("SKILLTREE_BIN_DIR", bin_dir.to_str().unwrap())
                .stdout(Stdio::piped())
                .spawn()
                .expect("spawn sidecar");

            // 4. 读 stdout 等 READY:<port>(entry.py 打印)确认服务起来
            let stdout = child.stdout.take().expect("no sidecar stdout");
            let reader = BufReader::new(stdout);
            let _ready_port: u16 = reader
                .lines()
                .filter_map(|l| l.ok())
                .find_map(|l| l.strip_prefix("READY:").and_then(|s| s.trim().parse::<u16>().ok()))
                .expect("no READY:<port> from sidecar (timeout?)");

            // 存句柄供退出时 kill
            if let Some(s) = app.try_state::<SidecarState>() {
                *s.0.lock().unwrap() = Some(child);
            }

            // 5. 注入端口给前端(webview 每次加载前注入 window.__SKILLTREE_PORT__)
            let port_str = port.to_string();
            app.on_page_load(move |webview, _payload| {
                let _ = webview.eval(&format!("window.__SKILLTREE_PORT__='{}'", port_str));
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            // 窗口销毁时 kill sidecar,避免僵尸进程
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
