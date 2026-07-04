# 桌面应用打包指南

把技能树从"本地 web 双进程"封装成 **Tauri 桌面应用**(Windows `.msi`/`.exe`、macOS `.dmg`)。

> 设计文档:`docs/superpowers/specs/2026-07-02-tauri-desktop-app-design.md`
> 架构:Tauri shell(Rust)→ spawn Python sidecar(PyInstaller 冻结的 uvicorn)→ webview 加载前端 dist,用动态端口调后端;lark-cli Go 二进制打进 resources,首次解压到用户主目录。

> ✅ **已验证(Windows)**：PyInstaller 冻结 sidecar(health + seed 通过)、`cargo tauri build` 产出 `.msi`(47MB)/`.exe`(35MB)、release exe 运行 sidecar 正确 spawn、数据落 `~/.skill-tree/data`。
> ⚠️ 未验证:双击安装包外壳体验(快捷方式/关联)、前端 UI 在 webview 渲染、macOS 包(需 Mac 环境或 CI)。

---

## 一、环境前置(一次性安装)

| 工具 | 用途 | 安装 |
|---|---|---|
| Node + npm | 前端构建 | https://nodejs.org |
| Python + pip | 后端 + PyInstaller | https://python.org |
| Rust 工具链 | Tauri shell 编译 | https://rustup.rs |
| Tauri CLI | 打包 | `cargo install tauri-cli --version "^2.0"` |
| PyInstaller | 后端冻结 | `pip install pyinstaller`(打包脚本会装) |
| lark-cli | 飞书功能(可选) | 已装则打包进去 |

验证:
```bash
node --version && npm --version
python --version
cargo --version && rustc --version
cargo tauri --version
```

---

## 二、一键打包

```bash
cd skill-tree
bash scripts/build-desktop.sh
```

脚本依次:前端 build → 后端 PyInstaller 冻结 → 复制 lark-cli → Tauri 打包。
产物:`desktop/src-tauri/target/release/bundle/`(Windows `.msi`/`.exe`,macOS `.dmg`)。

---

## 三、手动分步(调试用)

### 3.1 前端构建
```bash
cd frontend && npm run build
# 产物 frontend/dist/(Tauri 的 frontendDist 指向这里)
```

### 3.2 后端冻结(PyInstaller)
```bash
cd backend
pip install pyinstaller
pyinstaller skill-tree-backend.spec --noconfirm
# 产物 dist/skill-tree-backend/skill-tree-backend.exe(+ 依赖)
# 验证:
./dist/skill-tree-backend/skill-tree-backend.exe --port 8765 --data-dir /tmp/st-test
curl http://127.0.0.1:8765/api/health   # 应返回 {"ok":true,...}
```

### 3.3 放 lark-cli + 图标
```bash
# lark-cli(Windows Git Bash):
cp "$(which lark-cli)" desktop/src-tauri/resources/lark-cli.exe
# 图标(用 Tauri CLI 从一张 PNG 生成全套):
cargo tauri icon path/to/logo.png   # 生成 icons/ 全套
# 或手动放 desktop/src-tauri/icons/icon.ico(临时占位可)
```

### 3.4 Tauri 打包
```bash
# 把 sidecar 产物放到 Tauri exe 同目录(脚本会做,手动:
cp -r backend/dist/skill-tree-backend/* desktop/src-tauri/)
cd desktop/src-tauri
cargo tauri build
# 产物:target/release/bundle/
```

### 3.5 dev 模式(Tauri 跑前端 + 外部后端,开发用)
```bash
# 终端1:后端
cd backend && uvicorn main:app --port 8000
# 终端2:前端 dev(配 proxy 到 8000)
cd frontend && npm run dev
# 终端3:Tauri dev(走 devUrl localhost:5173)
cd desktop/src-tauri && cargo tauri dev
```

---

## 四、验证清单(打包后双击安装,确认这些能用)

- [ ] 技能树图谱能加载(seed 数据生效:首次启动从内置 seed 复制到 `~/.skill-tree/data`)
- [ ] AI 对话能发(在设置里配 LLM provider/key 后)
- [ ] 「写飞书」能产出文档(lark-cli 解压到 `~/.skill-tree/bin/` 成功)
- [ ] 关闭窗口后 sidecar 进程被 kill(任务管理器查 `skill-tree-backend` 应消失)
- [ ] 数据在 `~/.skill-tree/data/`(Windows: `%USERPROFILE%\.skill-tree\`)

---

## 五、常见报错排查

### `ModuleNotFoundError: No module named 'xxx'`(PyInstaller)
后端有动态 import,PyInstaller 静态分析漏了。编辑 `skill-tree-backend.spec`,把缺的模块加进 `hiddenimports` 列表,重打。

### lark-cli 飞书功能不可用
- 检查 `~/.skill-tree/bin/lark-cli[.exe]` 是否存在(首次解压)
- 检查 `lark-cli auth login` 是否执行过(auth token 存在用户主目录)
- 后端日志看 `resolve_lark_cli()` 解析到哪个路径

### 前端加载白屏 / 请求 404
- `window.__SKILLTREE_PORT__` 没注入:Tauri 的 `on_page_load` eval 没跑;检查 main.rs sidecar 是否打印了 `READY:<port>`
- 端口注入时序:sidecar 还没 ready 前端就请求;main.rs 已用读 stdout `READY:` 阻塞等待,确认 sidecar stdout 没被 buffer(entry.py 用了 `flush=True`)

### sidecar 启动失败 / 端口冲突
- sidecar 路径错:`current_exe().parent()` 在不同打包模式下位置不同,用 `println!` 打印实际路径调试
- 端口冲突:用了 `free_port()` 找空闲端口,理论不会冲突;若仍冲突检查是否有残留 sidecar 进程

### seed 没生效(首次启动图谱空)
- 检查 `_resolve_seed_dir()` 解析到的路径是否含 seed 文件
- PyInstaller 打包的 seed 解包位置:`sys._MEIPASS/seed`(onefile)或 `__file__/../_internal/seed`(onedir);main.py 已兼容探测,若仍不对用 `print(_SEED_DIR)` 调试
- **踩过的坑**:frozen 态 `Path(__file__).parent`(HERE)指向 PyInstaller 临时解压的 main.pyc 位置,不可靠。已改用 `sys.executable` 目录向上探测 `_internal/seed`。若改了打包结构重测此处。

### `cargo check` 报 `on_page_load` 方法不存在(Tauri 2 API 变动)
Tauri 2 的 `App` 上没有 `on_page_load`(那是 Tauri 1 API)。正确做法:在 `tauri::Builder` 链上用 `.on_page_load(move |webview, _payload| {...})`(builder 方法),端口经 `Arc<Mutex<Option<u16>>>` 在 setup 与 on_page_load 间共享。当前 main.rs 已是此模式。

### 残留 sidecar 进程锁住 `.pyd`(PermissionError 重打)
后台 `&` 启动的 sidecar,bash 的 `$!` 杀的是 wrapper 不是真 exe 子进程,导致 PyInstaller `_internal/*.pyd` 被锁,下次重打报 `WinError 5`。用 `netstat -ano | grep :<port>` 找真实 PID,`taskkill //F //PID <pid>` 清掉。

### SmartScreen 警告(Windows)/ Gatekeeper 拦(macOS)
**首版不签名,这是预期的**。Windows 点"仍要运行";macOS 右键→打开。要消除需购买代码签名证书(Windows)/Apple Developer 账号公证(macOS),见 spec §7。

---

## 六、跨平台打包说明

| 平台 | 产物 | 打包环境 |
|---|---|---|
| Windows | `.msi` / `.exe`(NSIS) | 必须在 Windows 上打 |
| macOS | `.dmg` / `.app` | 必须在 macOS 上打 |

**PyInstaller 和 Tauri 都不能交叉打包**。如果你只有 Windows:
- Windows 包:本机直接打
- macOS 包:用 GitHub Actions(`macos-latest` runner),或借一台 Mac

macOS via GitHub Actions 的最小 workflow 参考(后续可加):
```yaml
# .github/workflows/build-macos.yml
jobs:
  build:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - uses: actions-rs/toolchain@v1
        with: { toolchain: stable }
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: cd skill-tree/frontend && npm ci && npm run build
      - run: cd skill-tree/backend && pip install -r requirements.txt pyinstaller && pyinstaller skill-tree-backend.spec --noconfirm
      - run: cd skill-tree/desktop/src-tauri && cargo install tauri-cli --version "^2.0" && cargo tauri build
      - uses: actions/upload-artifact@v4
        with: { name: macos-dmg, path: skill-tree/desktop/src-tauri/target/release/bundle/dmg/ }
```
