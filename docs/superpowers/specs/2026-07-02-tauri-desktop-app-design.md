# 设计文档:技能树 → Tauri 桌面应用

- **日期**:2026-07-02
- **作者**:zjrua(与 brainstorming 协作)
- **状态**:待实现
- **范围**:把本地 web 应用(前端 vite + 后端 FastAPI 分进程)封装成 Tauri 桌面应用,Windows + macOS 双平台分发;去掉多用户隔离;用户数据迁到用户主目录
- **关联**:`2026-07-02-agent-depth-design.md`(agent 内核不变,本文件只动"外壳"和"数据落点")

---

## 0. 为什么不做云、要做桌面应用

三个硬约束决定了这个项目**结构上不可能、也不应该云部署**:

1. **lark-cli 是本机 CLI**:后端 `larkpub.py` 靠 `subprocess` 调它发飞书文档。云上没有 lark-cli。
2. **RAG 扫本地源码**:`PROJECTS_DIR` 是本地路径,`rag/indexer.py` 扫本地 `.py` 文件建索引。
3. **数据敏感性**:`llm_config.json` 存 api_key,简历素材、个人学习数据都在本地。放任何联网服务都是安全负担。

结论:**本地单机是最正确选择**。问题只是"本地形态怎么最舒服 + 能分发"。现状(开俩进程 + 浏览器输端口)不像产品,Tauri 桌面应用是最佳落点。

## 1. 关键决策(已与用户确认)

| 决策点 | 选择 | 理由 |
|---|---|---|
| Python 运行时 | **PyInstaller 冻结** | 用户不需装 Python;~40-60MB 可接受 |
| 数据落点 | **用户主目录**(`~/.skill-tree/` 或 `%APPDATA%/skill-tree`) | 升级/卸载不丢数据;标准桌面 app 做法 |
| 多用户隔离 | **去掉** | 单机 personal 应用,X-User-Id 那套是云部署遗留,纯负担 |
| 平台 | **Windows + macOS** | 移动端砍掉(Python 不能打 iOS/Android;Tauri mobile 不成熟;后端要重写) |
| lark-cli | **打包进应用** | 用户双击装完即能产出飞书文档;Go 二进制按平台放 resources |
| 前端框架 | **Tauri 2.x**(webview 加载本地 dist) | 轻量(~10MB shell),React 前端直接复用 |

## 2. 架构:Tauri + Python sidecar

### 2.1 运行时拓扑

```
┌─────────────────────────────────────────────────────┐
│  Tauri 应用进程(Rust shell,~10MB)                  │
│                                                       │
│  ┌──────────────┐     ┌──────────────────────────┐  │
│  │ WebView       │     │  Sidecar: skill-tree-backend.exe │
│  │ (dist/index.  │     │  (PyInstaller 冻结的 uvicorn)    │
│  │  html + React)│ ←─→│  监听 127.0.0.1:<动态端口>        │
│  │               │     │                                    │
│  │ fetch /api/* ─┼────→│  FastAPI app                      │
│  └──────────────┘     │  + agent / rag / larkpub          │
│         │             └──────────────────────────┘        │
│         │                       │                          │
│         │                       │ subprocess               │
│         │                       ▼                          │
│         │             ┌──────────────────────────┐        │
│         │             │ lark-cli(Go 二进制,       │        │
│         │             │ 从 resources 解压到临时目录)│        │
│         │             └──────────────────────────┘        │
│         │                                               │
│         │ 读写                                           │
│         ▼                                               │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 用户主目录 ~/.skill-tree/                          │  │
│  │  ├── data/  (trees/profile/llm_config/...)        │  │
│  │  ├── resume/ (简历素材)                            │  │
│  │  └── projects/ (开源项目源码,RAG 扫描)            │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 三个进程/资源的生命周期

- **Tauri 主进程**(Rust):启动时 spawn sidecar,退出时 kill。`tauri.conf.json` 配 `sidecar`。
- **Python sidecar**:PyInstaller 打成单可执行 `skill-tree-backend.exe`。启动参数 `--port <动态>` + `--data-dir <用户主目录>`。动态端口避免冲突(找空闲端口传给 sidecar,sidecar 把端口写 stdout,Tauri 读到后再让 webview 发请求)。
- **lark-cli**:Go 二进制(每个平台一个,~15MB)。放 Tauri `resources`,首次启动解压到用户主目录下 `bin/`,`larkpub.py` 优先用该路径的 lark-cli,找不到才退回 PATH。

### 2.3 前端如何调后端(Tauri 的关键改造)

现状:`BASE=''` 同源,vite dev proxy 转发。Tauri 里 webview 加载 `dist/index.html`(tauri:// 协议或 file://),fetch `/api/...` **不会命中 sidecar**——需要 Tauri 的 Rust 侧做转发,或前端改用绝对 `http://127.0.0.1:<port>`。

**决策:前端用动态端口绝对地址。** Tauri 启动 sidecar 拿到端口后,通过 `window.__TAURI__.invoke` 或初始化时注入全局变量把端口告诉前端,前端 `BASE = http://127.0.0.1:${port}`。比 Rust 转发简单,且 sidecar 挂了前端能感知(连接失败)。

### 2.4 前端 dev 模式不变

开发时仍是 `vite dev`(5173)+ `uvicorn`(8000)+ proxy。只有打包产物走 Tauri。**dev 体验零改动**。

## 3. 去多用户隔离(集中重构)

### 3.1 现状

- 后端 `main.py`:57 处 `resolve_user` / `X-User-Id` / `x_user_id`。
- 前端:4 文件 16 处 `getUserId()` 传 header。

### 3.2 改法

**后端**:
- 删除 `resolve_user`、`X-User-Id` 参数、`USERS_DIR` 分层。
- `DATA_ROOT` 直接指向用户主目录(`~/.skill-tree/data`)。
- 所有 `user_dir(uid)` → 直接 `DATA_ROOT`(单用户)。
- `/api/users`、`POST /api/users` 端点**删除**(不再多用户)。
- `load_trees` 等"按用户目录"逻辑简化为"按 DATA_ROOT"。

**前端**:
- 删除 `getUserId`/`setUserId`/`USER_KEY`、所有 `X-User-Id` header。
- 用户切换 UI(若有)删除。

### 3.3 首次启动 seed(数据迁移的归属)

**决策:seed 逻辑放后端**(`main.py` 启动时执行),不放 Tauri——后端最清楚需要哪些文件,且 dev 模式(无 Tauri)也能享受首次 seed。

- 后端启动时:若 `DATA_ROOT` 为空(无任何 .json),从打包内置的 `seed/` 目录(或开发期的 `data/users/default/`)复制初始技能树/profile/成就到 `DATA_ROOT`。已有数据则跳过(幂等,不覆盖)。
- 这取代了原 §3.2 提到的迁移,集中在一处,dev 和打包行为一致。
- Tauri 侧只负责把 `DATA_ROOT` env 指到用户主目录,不关心 seed。

### 3.4 测试影响

`test_apply.py` 等用 `tmp_path` 的测试不受影响(本来就不依赖多用户)。无 TestClient,纯函数测试风格不变。

## 4. 数据目录方案

```
~/.skill-tree/              (Windows: %APPDATA%/skill-tree; macOS: ~/Library/Application Support/skill-tree)
├── data/                   原 data/users/default/ 内容
│   ├── *.json              技能树
│   ├── profile.json
│   ├── llm_config.json
│   ├── lark_config.json
│   ├── chat_history.json
│   ├── achievements.json
│   └── rag_index/
├── resume/                 简历素材(可选,首次不预置)
├── projects/               开源项目源码(RAG 扫描,用户可放入)
└── bin/
    └── lark-cli(.exe)      从 resources 解压
```

- `DATA_ROOT` / `RESUME_DIR` / `PROJECTS_DIR` 三个 env 全指向用户主目录子路径。
- sidecar 启动时由 Tauri 注入这三个 env。
- 首次运行:若 `data/` 为空,从打包内置的 `seed/data/`(原 default 用户)复制一份。

## 5. 文件结构新增

```
skill-tree/
├── backend/
│   ├── main.py             【改】去多用户 + DATA_ROOT 默认主目录
│   ├── entry.py            【新】PyInstaller 入口(调 uvicorn.run)
│   ├── *.spec              【新】PyInstaller 配置(或用 CLI 参数)
│   └── ...
├── desktop/                【新】Tauri shell
│   ├── src-tauri/
│   │   ├── tauri.conf.json 【新】sidecar + resources + window 配置
│   │   ├── src/main.rs     【新】spawn sidecar + 注入端口 + 生命周期
│   │   ├── Cargo.toml
│   │   └── icons/
│   │   └── resources/
│   │       ├── lark-cli-windows.exe   【打包时下载】
│   │       └── lark-cli-macos         【打包时下载】
│   └── README.md           【新】打包流程说明
├── frontend/
│   └── src/api.ts          【改】BASE 动态端口 + 删 getUserId
└── scripts/
    └── build-desktop.*     【新】一键打包(冻结后端 → tauri build)
```

## 6. 打包流程(开发者侧)

### 6.1 一次性环境

- 装 Rust + Tauri CLI(`cargo install tauri-cli --version "^2.0"`).
- 装 Node + Python(开发用;打包产物不含)。

### 6.2 每次 release

1. **前端**:`cd frontend && npm run build` → `dist/`.
2. **后端冻结**:`cd backend && pyinstaller entry.spec` → `dist/skill-tree-backend/`(含 Python 解释器 + 依赖 + 代码).
   - entry.spec 的 datas 要带上 `seed/data/`(初始示例数据).
3. **lark-cli 二进制**:下载对应平台版本放 `resources/`(脚本自动按平台拉).
4. **Tauri 打包**:`cd desktop/src-tauri && cargo tauri build` → 生成 `.msi`/`.exe`(Windows)或 `.dmg`(macOS).
5. Tauri 把 sidecar + lark-cli resources + dist 前端全打进安装包。

### 6.3 平台矩阵

| 平台 | 产物 | 打包环境要求 |
|---|---|---|
| Windows | `.msi` / `.exe`(NSIS) | Windows + Rust + PyInstaller |
| macOS | `.dmg` | macOS + Rust + PyInstaller |

**跨平台打包限制**:PyInstaller 和 Tauri 都**不能交叉打包**(Windows 包必须在 Windows 上打,Mac 包必须在 Mac 上打)。需要 GitHub Actions 矩阵 CI,或你在对应平台手动打。macOS 若无 Mac,用 GitHub Actions macos-latest。

## 7. 代码签名与自动更新

### 7.1 签名(可选,首版可不做)

- Windows:无签名会 SmartScreen 警告。要消除需购买代码签名证书($$$)。**首版接受警告**,README 注明"首次运行点仍要运行"。
- macOS:无签名会 Gatekeeper 拦。需 Apple Developer 账号 + 公证。**首版可做 ad-hoc 签名**(本地能用,分发给别人会被拦)或要求用户右键打开。

### 7.2 自动更新(Tauri Updater,后续)

Tauri 2 自带 updater。首版**不做**(YAGNI),后续接 GitHub Releases 做签名更新。

## 8. 实施阶段(给 writing-plans 的分解提示)

1. **去多用户隔离**(后端 main.py + 前端 4 文件)——纯重构,测试保绿。
2. **数据目录迁移**(DATA_ROOT 默认主目录 + 后端首次 seed 逻辑,见 §3.3)。
3. **sidecar 入口**(backend/entry.py + PyInstaller spec,本地能 `pyinstaller` 跑通)。
4. **Tauri shell 骨架**(desktop/ 脚手架,sidecar 生命周期 + 动态端口注入前端)。
5. **lark-cli 资源打包**(resources + 解压 + larkpub.py 优先用本地二进制)。
6. **Windows 打包跑通**(产出 .msi,本机双击验证)。
7. **macOS 打包**(GitHub Actions 或 Mac 环境)。
8. **收尾**(README 打包说明 + 移除 docker-compose 的开发冗余 / 保留 dev 用)。

## 9. 面试讲法

「我把这个 personal 学习系统从'本地 web 双进程'封装成 **Tauri 桌面应用**——因为它的后端依赖本机资源(lark-cli、本地源码 RAG)且数据敏感(api_key、简历),**结构上不该云部署**。用 PyInstaller 冻结 Python 后端当 sidecar、Tauri 做 shell、lark-cli 按平台打进 resources,实现了 Windows/macOS 双平台单文件分发,用户双击即用。同时去掉了为'未来云部署'预留的多用户隔离,让代码符合实际形态。」

## 10. 范围与风险

### 10.1 首版范围

- 去多用户隔离 + 数据迁主目录
- PyInstaller sidecar + Tauri shell
- lark-cli 打包
- Windows 打包跑通(主战场)
- macOS 打包(GitHub Actions)

### 10.2 不在首版

- 代码签名/公证(费用 + 流程重,首版接受警告)
- 自动更新(接 GitHub Releases,后续)
- 移动端(砍掉,技术栈不匹配)
- Linux(需求弱)

### 10.3 风险

| 风险 | 缓解 |
|---|---|
| PyInstaller 冻结 uvicorn/标准库 urllib 有隐藏依赖 | 用 `--hidden-import` 补;本地先 `pyinstaller` 跑通验证 |
| 动态端口注入前端时序(sidecar 没起好前端就请求) | Tauri 等 sidecar stdout 输出 "READY:<port>" 再加载 webview |
| lark-cli 二进制获取/版本固定 | 打包脚本固定拉 v1.0.60,校验 hash |
| macOS 无 Mac 环境 | GitHub Actions macos-latest 打包 |
| 首次数据迁移把用户已有数据覆盖 | 只在 `data/` 为空时 seed |
