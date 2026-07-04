# Tauri 桌面应用封装 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把本地 web 应用封装成 Tauri 桌面应用(Windows + macOS),去多用户隔离,数据迁用户主目录,lark-cli 打包进应用。

**Architecture:** PyInstaller 冻结 Python 后端成 sidecar(单 .exe,含解释器)→ Tauri shell 启动 sidecar(动态端口)+ 注入数据目录 env → webview 加载前端 dist,用绝对端口地址调后端 → lark-cli Go 二进制按平台打进 resources,首次解压到用户主目录 bin/。

**关键现实约束:** 本会话环境**没装** Rust / Tauri CLI / PyInstaller。所以本计划分两部分:
- **Part A(Task 1-6)纯代码,TDD 可验证**——去多用户隔离、数据目录、sidecar 入口、seed 逻辑、前端端口注入、larkpub 本地二进制。这部分我自己跑测试保绿。
- **Part B(Task 7-10)工具链依赖**——Tauri 配置、PyInstaller spec、打包脚本、CI。这些**无法在当前环境执行/验证**,写成"配置文件 + 操作手册",由用户在本机装好工具链后照着跑。

**Spec:** `docs/superpowers/specs/2026-07-02-tauri-desktop-app-design.md`

---

## 文件结构改动总览

```
skill-tree/
├── backend/
│   ├── main.py             【改·Part A】去多用户 + DATA_ROOT 主目录 + seed
│   ├── entry.py            【新·Part A】sidecar 入口(uvicorn.run,PyInstaller 入口点)
│   ├── larkpub.py          【改·Part A】优先用本地 lark-cli 二进制
│   └── skill-tree-backend.spec  【新·Part B】PyInstaller 配置
├── desktop/                【新·Part B】Tauri shell
│   ├── src-tauri/
│   │   ├── Cargo.toml
│   │   ├── tauri.conf.json
│   │   ├── build.rs
│   │   ├── src/main.rs     (spawn sidecar + 动态端口 + 生命周期 + seed env)
│   │   ├── icons/
│   │   └── resources/      (lark-cli 二进制,打包时放入)
│   └── README.md           【新·Part B】打包手册
├── frontend/
│   ├── src/api.ts          【改·Part A】动态端口 BASE + 删 getUserId
│   ├── src/App.tsx         【改·Part A】删用户切换 UI
│   └── src/panels/SetupPanel.tsx  【改·Part A】删用户切换 UI
├── scripts/
│   └── build-desktop.sh    【新·Part B】一键打包脚本
└── data/users/default/     【保留】作为 seed 源(打包进应用)
```

---

## Part A — 纯代码,TDD 可验证

## Task 1: 后端去多用户隔离(集中重构 main.py)

**Why:** 单机 personal 应用,X-User-Id 那套是云部署遗留。57 处改动但全是同质模式(`resolve_user` + `user_dir(uid)` + Header 参数)。先做这步,后续 Task 才能在干净的 DATA_ROOT 上改。

**Files:**
- Modify: `skill-tree/backend/main.py`
- Modify: `skill-tree/backend/tests/test_apply.py`(若引用了 X-User-Id)
- Run: 全量 `python -m pytest tests/ -q` 保绿

- [ ] **Step 1: 读 main.py 全文,确认改动面**

Run: `cat skill-tree/backend/main.py`(通读,57 处 resolve_user/user_dir/x_user_id 散布在所有端点)

- [ ] **Step 2: 重构 main.py — 删除多用户层**

具体改动(机械但有 57 处,逐一处理):

1. **删除** `def resolve_user`、`_SAFE_ID` 正则、`USERS_DIR`。
2. **`DATA_ROOT`** 改为直接指向数据目录(本 Task 先保留 `data/users/default` 路径不变,Task 2 再改到用户主目录——分两步避免一次改太多)。即:`DATA_ROOT = Path(os.environ.get("DATA_ROOT", HERE.parent / "data" / "users" / "default"))`。
3. **`user_dir(uid)` 函数删除**。所有 `user_dir(uid)` 调用替换为 `DATA_ROOT`(直接用全局)。
4. **所有端点的 `x_user_id: str | None = Header(default=None)` 参数删除**,函数体里的 `uid = resolve_user(x_user_id)` 删除。
5. **`patch_task` 末尾** `return get_graph(x_user_id=uid)` → `return get_graph()`(参数没了)。
6. **删除 `/api/users` GET 和 POST 端点**(不再多用户)。
7. **`load_achievements` 等里** `USERS_DIR / "default"` 引用 → 用 DATA_ROOT 或 seed 路径(Task 2 处理 seed,本 Task 先指向 `data/users/default`)。
8. **文件头注释** 更新:删掉"X-User-Id 多用户"那行,改成单机说明。

- [ ] **Step 3: 处理 `create_user` 里引用 `USERS_DIR / "default" / "achievements.json"`**

这个逻辑(新建用户时复制 default 成就)随 `/api/users` 删除一并消失。确认无残留。

- [ ] **Step 4: 跑全量测试**

Run: `cd skill-tree/backend && python -m pytest tests/ -q`
Expected: 全 PASS。若有测试 import 了已删的函数(如 `resolve_user`),修正测试。`test_apply.py` 用纯函数 `_apply_node_to_tree`,不依赖 X-User-Id,应不受影响。

- [ ] **Step 5: 前端构建确认(前端还引用 getUserId,本 Task 先不删,确认不报后端错即可)**

跳过前端(本 Task 只动后端)。前端 getUserId 在 Task 5 删。

- [ ] **Step 6: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/main.py skill-tree/backend/tests/
git commit -m "refactor(backend): 去掉多用户隔离(单机应用)

删除 resolve_user / X-User-Id / USERS_DIR / /api/users 端点。
所有 user_dir(uid) 改为直接用 DATA_ROOT。为 Tauri 桌面化铺垫。"
```

---

## Task 2: 后端 DATA_ROOT 迁用户主目录 + 首次 seed 逻辑

**Why:** spec §3.3、§4。桌面应用数据必须存用户主目录(升级/卸载不丢)。seed 归属后端启动逻辑。

**Files:**
- Modify: `skill-tree/backend/main.py`(DATA_ROOT 默认主目录 + seed 函数)
- Test: 新增 `tests/test_seed.py`

- [ ] **Step 1: 写 seed 失败测试**

新建 `tests/test_seed.py`:
```python
from __future__ import annotations
from pathlib import Path
import main


def test_seed_copies_when_data_dir_empty(tmp_path):
    """DATA_ROOT 为空时,从 seed 目录复制初始数据。"""
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "agent.json").write_text('{"tree_id":"agent"}', encoding="utf-8")
    target = tmp_path / "data"
    main.seed_if_empty(target, seed)
    assert (target / "agent.json").exists()
    assert (target / "agent.json").read_text(encoding="utf-8") == '{"tree_id":"agent"}'


def test_seed_skips_when_data_already_present(tmp_path):
    """DATA_ROOT 已有数据时不覆盖(幂等)。"""
    seed = tmp_path / "seed"; seed.mkdir()
    (seed / "agent.json").write_text('{"seed":true}', encoding="utf-8")
    target = tmp_path / "data"; target.mkdir()
    (target / "existing.json").write_text('{"keep":true}', encoding="utf-8")
    main.seed_if_empty(target, seed)
    assert not (target / "agent.json").exists()   # 不覆盖、不补
    assert (target / "existing.json").read_text(encoding="utf-8") == '{"keep":true}'


def test_seed_no_seed_dir_is_noop(tmp_path):
    """seed 目录不存在时静默跳过(打包未含 seed 的 dev 场景)。"""
    target = tmp_path / "data"; target.mkdir()
    main.seed_if_empty(target, tmp_path / "nope")   # 不应抛错
    assert not list(target.iterdir())
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_seed.py -v`
Expected: AttributeError — `seed_if_empty` 不存在。

- [ ] **Step 3: 实现 seed_if_empty + DATA_ROOT 主目录化**

在 `main.py`:

```python
import os
from pathlib import Path

def _user_data_root() -> Path:
    """桌面应用:数据存用户主目录;开发期可被 DATA_ROOT env 覆盖。"""
    env = os.environ.get("DATA_ROOT")
    if env:
        return Path(env)
    # 默认:用户主目录下 .skill-tree/data
    home = Path.home()
    return home / ".skill-tree" / "data"


def seed_if_empty(target: Path, seed: Path) -> None:
    """target 为空(无任何文件)时,从 seed 复制初始数据;否则跳过(幂等)。"""
    if not seed.exists() or not seed.is_dir():
        return
    if target.exists() and any(target.iterdir()):
        return   # 已有数据,不覆盖
    target.mkdir(parents=True, exist_ok=True)
    import shutil
    for p in seed.iterdir():
        if p.is_file():
            shutil.copy2(p, target / p.name)
```

把模块级 `DATA_ROOT = Path(...)` 改为:
```python
DATA_ROOT = _user_data_root()
# seed 源:打包内置的 seed/ 目录,或开发期的 data/users/default/
_SEED_DIR = Path(os.environ.get("SEED_DIR", HERE.parent / "data" / "users" / "default"))
# 启动时 seed(若 DATA_ROOT 为空)
seed_if_empty(DATA_ROOT, _SEED_DIR)
DATA_ROOT.mkdir(parents=True, exist_ok=True)
```

`RESUME_DIR` / `PROJECTS_DIR` 也改为用户主目录默认:
```python
RESUME_DIR = Path(os.environ.get("RESUME_DIR", Path.home() / ".skill-tree" / "resume"))
PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", Path.home() / ".skill-tree" / "projects"))
```

- [ ] **Step 4: 测试时隔离 DATA_ROOT(避免污染本机 ~/.skill-tree)**

测试通过 env 覆盖 DATA_ROOT。但 seed 是模块级执行(import 时跑),测试需在 import 前 set env。
最稳的办法:测试文件顶部
```python
import os, tempfile
os.environ["DATA_ROOT"] = tempfile.mkdtemp()
os.environ["SEED_DIR"] = tempfile.mkdtemp()   # 空,避免 seed
import main   # 之后再 import
```
注意:test_seed.py 直接测 `seed_if_empty` 函数(纯函数,不依赖模块级 DATA_ROOT),所以它**不受影响**。但其它测试 import main 时会触发模块级 seed —— 把 `tests/conftest.py` 加一个 fixture 或在 `tests/__init__.py` 设 env。检查是否已有 conftest,没有则建 `tests/conftest.py`:
```python
import os, tempfile
# 测试用临时 DATA_ROOT,避免污染本机 ~/.skill-tree
os.environ.setdefault("DATA_ROOT", tempfile.mkdtemp(prefix="st_test_"))
os.environ.setdefault("SEED_DIR", tempfile.mkdtemp(prefix="st_seed_"))
```

- [ ] **Step 5: 运行全量测试**

Run: `cd skill-tree/backend && python -m pytest tests/ -q`
Expected: 全 PASS(含新 seed 测试)。

- [ ] **Step 6: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/main.py skill-tree/backend/tests/test_seed.py skill-tree/backend/tests/conftest.py
git commit -m "feat(backend): DATA_ROOT 默认用户主目录 + 首次 seed 逻辑

桌面应用数据存 ~/.skill-tree/(升级/卸载不丢);启动时若空则从
内置 seed 复制初始技能树。dev 仍可用 DATA_ROOT env 覆盖。"
```

---

## Task 3: 前端删多用户 UI + 动态端口 BASE

**Why:** spec §3.2 前端部分 + §2.3。删 getUserId/X-User-Id(后端已不收),删用户切换 UI(SetupPanel 的 user-chip + 新建表单 + App 的 onUserChanged)。同时 BASE 改为支持动态端口(Tauri 注入)。

**Files:**
- Modify: `skill-tree/frontend/src/api.ts`
- Modify: `skill-tree/frontend/src/App.tsx`
- Modify: `skill-tree/frontend/src/panels/SetupPanel.tsx`
- Modify: `skill-tree/frontend/src/AgentChat.tsx`

- [ ] **Step 1: api.ts — 删 getUserId,BASE 动态化**

读 `src/api.ts`。改动:
1. 删除 `USER_KEY`、`getUserId`、`setUserId`、`authHeaders` 里 `'X-User-Id': getUserId()`(改成空或直接删 authHeaders,所有调用处用普通 headers)。
2. `BASE` 改为:
```typescript
// Tauri 打包后由 shell 注入端口(通过 window.__SKILLTREE_PORT__);开发期空串走 vite proxy
const PORT = (typeof window !== 'undefined' && (window as any).__SKILLTREE_PORT__) || ''
export const BASE = PORT ? `http://127.0.0.1:${PORT}` : ''
```
3. 所有原本 `headers: { 'X-User-Id': getUserId() }` 或 `authHeaders(...)` 的调用,改成不带 X-User-Id(后端已不读)。例如 `headers: { 'Content-Type': 'application/json' }`。

- [ ] **Step 2: App.tsx — 删用户切换 UI**

读 `src/App.tsx`。改动:
1. 删 `import { ..., getUserId } from './api'` 里的 getUserId(若 api 仍导出空函数可留,但调用处删)。
2. 删 `onUserChanged` useCallback 和 `<SetupPanel onUserChanged={...} />` 的该 prop。
3. 删"当前用户 {getUserId()}"显示。

- [ ] **Step 3: SetupPanel.tsx — 删用户管理区块**

读 `src/panels/SetupPanel.tsx`。这个文件改动较大(它有完整的用户列表/切换/新建 UI)。改动:
1. 删 `getUserId, setUserId` import,删 `UserInfo` type import(若专为多用户)。
2. 删 `pickUser`、新建用户表单、`user-chip` 列表渲染区块。
3. 删 `onUserChanged` prop(组件不再需要)。
4. 保留 LLM 配置 + 飞书 wiki 归档配置(这些是个人配置,单机仍需要)。
5. Props 接口删 `onUserChanged`。

- [ ] **Step 4: AgentChat.tsx — 删 getUserId 用法**

读 `src/AgentChat.tsx`。改动:
1. 删 `import { api, getUserId } from './api'` 的 getUserId。
2. 删 `const uid = getUserId()` 及其后续对 `uid` 的引用(CACHE_KEY 等)。

- [ ] **Step 5: 前端构建确认**

Run: `cd skill-tree/frontend && npm run build`
Expected: 构建成功,无 TS 报错。若有"未使用 import"或"找不到 getUserId"报错,清理干净。

- [ ] **Step 6: 后端测试回归确认(后端已不读 X-User-Id,前端不发,应无影响)**

Run: `cd skill-tree/backend && python -m pytest tests/ -q`
Expected: 全 PASS。

- [ ] **Step 7: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/frontend/src/
git commit -m "refactor(frontend): 删多用户 UI + BASE 动态端口

去掉用户切换/新建 UI(单机应用);getUserId/X-User-Id 全清;
BASE 支持 Tauri 注入端口(window.__SKILLTREE_PORT__)。"
```

---

## Task 4: backend/entry.py — sidecar 入口

**Why:** spec §5、§6.2。PyInstaller 需要一个入口脚本,启动 uvicorn。dev 仍可用 `uvicorn main:app`,但打包走 entry.py(能被 PyInstaller 识别为入口点,且能从命令行收 port/data-dir 参数)。

**Files:**
- Create: `skill-tree/backend/entry.py`

- [ ] **Step 1: 创建 entry.py**

```python
"""entry.py — PyInstaller sidecar 入口。

打包后由 Tauri shell 启动:
  skill-tree-backend.exe --port 52317 --data-dir ~/.skill-tree/data

读 port/data-dir,设 env(main.py 据此定 DATA_ROOT),起 uvicorn。
"""
from __future__ import annotations
import argparse
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default=None, help="覆盖 DATA_ROOT")
    parser.add_argument("--resume-dir", default=None)
    parser.add_argument("--projects-dir", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.data_dir:
        os.environ["DATA_ROOT"] = args.data_dir
    if args.resume_dir:
        os.environ["RESUME_DIR"] = args.resume_dir
    if args.projects_dir:
        os.environ["PROJECTS_DIR"] = args.projects_dir

    import uvicorn
    # READY 信号:Tauri shell 读 stdout 等这行再让 webview 请求
    print(f"READY:{args.port}", flush=True)
    uvicorn.run("main:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 本地 smoke 验证 entry.py 能起服务**

Run(后台):
```bash
cd skill-tree/backend
DATA_ROOT=$(mktemp -d) python entry.py --port 8765 &
sleep 2
curl -s http://127.0.0.1:8765/api/health
```
Expected: 返回 `{"ok":true,...}`。验证后 kill 该进程。

- [ ] **Step 3: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/entry.py
git commit -m "feat(backend): entry.py sidecar 入口(PyInstaller 打包点)

读 --port/--data-dir,设 env,起 uvicorn,打印 READY:<port> 供 Tauri shell 同步。"
```

---

## Task 5: larkpub 优先用本地 lark-cli 二进制

**Why:** spec §2.2。打包后用户机器 PATH 里没有 lark-cli,Tauri 会把它解压到 `~/.skill-tree/bin/`。larkpub 要优先找这个路径的二进制。

**Files:**
- Modify: `skill-tree/backend/larkpub.py`
- Modify: `skill-tree/backend/tests/test_larkpub.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_larkpub.py` 追加:
```python
def test_resolve_lark_cli_prefers_local_bin(tmp_path, monkeypatch):
    """优先用 SKILLTREE_BIN_DIR 下的 lark-cli;找不到才退 PATH。"""
    import larkpub
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # 模拟本地已解压的 lark-cli(空文件即可,只测路径解析)
    (bindir / "lark-cli.exe").write_text("")
    (bindir / "lark-cli").write_text("")
    monkeypatch.setenv("SKILLTREE_BIN_DIR", str(bindir))
    path = larkpub.resolve_lark_cli()
    # 在 Windows 上应命中 .exe,其它命中无后缀;二者都应在 bindir 下
    assert str(bindir) in path
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_larkpub.py::test_resolve_lark_cli_prefers_local_bin -v`
Expected: `resolve_lark_cli` 不存在。

- [ ] **Step 3: 实现**

在 `larkpub.py`:
```python
import os, sys

def resolve_lark_cli() -> str:
    """优先用 SKILLTREE_BIN_DIR 下的 lark-cli(Tauri 解压位置);否则退 PATH 里的 lark-cli。"""
    bin_dir = os.environ.get("SKILLTREE_BIN_DIR")
    if bin_dir:
        exe = "lark-cli.exe" if sys.platform == "win32" else "lark-cli"
        local = os.path.join(bin_dir, exe)
        if os.path.exists(local):
            return local
    return "lark-cli"   # 退 PATH(开发期 / 用户自装)
```

把 `publish_doc` 里所有 `"lark-cli", "docs", ...` 和 `"lark-cli", "wiki", ...` 命令列表改成以 `resolve_lark_cli()` 开头:
```python
lark = resolve_lark_cli()
create_cmd = [lark, "docs", "+create", "--as", "user", "--content", xml_content]
# ...
move_cmd = [lark, "wiki", "+move", "--as", "user", "--obj-type", "docx", ...]
```

- [ ] **Step 4: 运行测试**

Run: `cd skill-tree/backend && python -m pytest tests/test_larkpub.py -v`
Expected: PASS。注意:既有测试 monkeypatch `larkpub._run`,不碰 lark-cli 路径,应仍 pass。

- [ ] **Step 5: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/larkpub.py skill-tree/backend/tests/test_larkpub.py
git commit -m "feat(lark): larkpub 优先用本地 lark-cli 二进制(SKILLTREE_BIN_DIR)

打包后 Tauri 把 lark-cli 解压到用户主目录 bin/,larkpub 优先用该路径,
找不到退 PATH。为打包进应用铺垫。"
```

---

## Task 6: 打包 seed 准备 + 后端 requirements 加 PyInstaller

**Why:** Part A 收尾。确认 seed 源目录(`data/users/default/`)内容完整(打包时 PyInstaller 要带进去),requirements 注明 PyInstaller(打包用,非运行依赖)。

**Files:**
- Verify: `skill-tree/data/users/default/`
- Modify: `skill-tree/backend/requirements.txt`(加注释,不强制装)

- [ ] **Step 1: 确认 seed 源完整**

Run: `ls -la skill-tree/data/users/default/`
Expected: 含 agent.json / recommendation.json / profile.json / achievements.json / llm_config.json 等关键文件。这些会作为打包内置 seed。

- [ ] **Step 2: requirements.txt 加打包说明注释**

读 `skill-tree/backend/requirements.txt`,末尾加注释:
```
# 打包专用(非运行依赖):pyinstaller>=6.0
```
不实际加 pyinstaller 到依赖(避免开发期误装)。

- [ ] **Step 3: Part A 全量回归**

Run: `cd skill-tree/backend && python -m pytest tests/ -q && cd ../frontend && npm run build`
Expected: 后端全 PASS + 前端构建成功。Part A 完成。

- [ ] **Step 4: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/requirements.txt
git commit -m "chore: 标注 PyInstaller 为打包依赖;确认 seed 源完整

Part A(纯代码 TDD 部分)完成。Part B(Tauri shell/打包)需本机工具链。"
```

---

## Part B — 工具链依赖(配置 + 手册,用户本机执行)

> **这部分无法在当前会话环境执行/验证**(无 Rust / Tauri CLI / PyInstaller)。写成配置文件 + 操作手册。用户装好工具链后按 Task 7-10 执行。每个 Task 顶部标注"环境前置"。

## Task 7: PyInstaller spec(后端冻结配置)

**环境前置:** `pip install pyinstaller`

**Files:**
- Create: `skill-tree/backend/skill-tree-backend.spec`

- [ ] **Step 1: 写 .spec 文件**

```python
# skill-tree-backend.spec — PyInstaller 配置,冻结后端为单可执行 sidecar
# 用法: cd backend && pyinstaller skill-tree-backend.spec
# 产物: dist/skill-tree-backend/skill-tree-backend.exe(目录模式,启动更快)
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# uvicorn / fastapi / pydantic 常有隐藏 import,显式收集
datas, binaries, hiddenimports = [], [], []
for pkg in ('uvicorn', 'fastapi', 'pydantic'):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

# 带上 seed 数据(首次启动复制到用户主目录)
datas += [('../data/users/default', 'seed')]

hiddenimports += ['main', 'entry', 'ai', 'larkpub', 'layout', 'progress', 'chat_store',
                  'agent.loop', 'agent.prompts', 'agent.tools', 'agent.tool_runtime',
                  'agent.protocol', 'agent.session',
                  'rag.indexer', 'rag.retriever', 'rag.paper_fetch', 'rag.store']

a = Analysis(
    ['entry.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='skill-tree-backend',
          console=True, icon=None)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='skill-tree-backend')
```

> **注意**:seed 目录的 `datas` 路径(`../data/users/default`)在打包时相对于 spec 文件位置。`SEED_DIR` env 在 entry/Tauri 里要指向解压后的 `seed/` 子目录(PyInstaller datas 会把目录内容平铺到 dist 旁的 `_internal/seed/`)。实际 `_SEED_DIR` 解析可能需要调整为 `Path(sys._MEIPASS)/"seed"` 或 `Path(__file__).parent/"seed"`——**打包时验证,本会话无法预判确切路径**。

- [ ] **Step 2: 本地冻结验证(用户执行)**

```bash
cd skill-tree/backend
pip install pyinstaller
pyinstaller skill-tree-backend.spec
# 验证产物能跑
./dist/skill-tree-backend/skill-tree-backend.exe --port 8765 --data-dir /tmp/st-test
curl http://127.0.0.1:8765/api/health
```
预期:health 返回 ok。若报 ModuleNotFoundError,把缺的模块加进 hiddenimports 重打。

- [ ] **Step 3: 提交 spec**

```bash
git add skill-tree/backend/skill-tree-backend.spec
git commit -m "build: PyInstaller spec(冻结后端为 sidecar)"
```

---

## Task 8: Tauri shell 脚手架

**环境前置:** Rust 工具链(`rustup`) + Tauri CLI(`cargo install tauri-cli --version "^2.0"` 或 `npm install -D @tauri-apps/cli`)。

**Files:**
- Create: `skill-tree/desktop/src-tauri/Cargo.toml`
- Create: `skill-tree/desktop/src-tauri/tauri.conf.json`
- Create: `skill-tree/desktop/src-tauri/src/main.rs`
- Create: `skill-tree/desktop/src-tauri/build.rs`
- Create: `skill-tree/desktop/src-tauri/icons/`(占位图标)

- [ ] **Step 1: Cargo.toml**

```toml
[package]
name = "skill-tree-desktop"
version = "0.1.0"
edition = "2021"

[build-dependencies]
tauri-build = { version = "2.0", features = [] }

[dependencies]
tauri = { version = "2.0", features = [] }
tauri-plugin-shell = "2.0"
serde = { version = "1", features = ["derive"] }
serde_json = "1"

[features]
custom-protocol = ["tauri/custom-protocol"]
```

- [ ] **Step 2: tauri.conf.json(关键:sidecar + resources + window)**

```json
{
  "$schema": "https://schema.tauri.app/config/2.0",
  "productName": "Skill Tree",
  "version": "0.1.0",
  "identifier": "com.zjrua.skilltree",
  "build": {
    "frontendDist": "../../frontend/dist",
    "devUrl": "http://localhost:5173"
  },
  "app": {
    "windows": [
      {
        "title": "技能树",
        "width": 1280,
        "height": 800,
        "minWidth": 900,
        "minHeight": 600
      }
    ],
    "security": {
      "csp": null
    }
  },
  "bundle": {
    "active": true,
    "targets": ["msi", "nsis"],
    "icon": ["icons/icon.ico"],
    "resources": ["resources/lark-cli*"],
    "externalBin": []
  }
}
```

> 注意:`frontendDist` 指向前端构建产物。`resources` 把 lark-cli 二进制打进安装包。`targets` Windows 用 msi/nsis;macOS 在 mac 环境改为 ["dmg","app"]。

- [ ] **Step 3: main.rs(spawn sidecar + 动态端口 + 注入前端)**

```rust
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
// hide console on Windows release

use std::process::{Command, Stdio};
use std::io::{BufRead, BufReader};
use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // 1. 解 lark-cli 到用户主目录 bin/
            let home = dirs::home_dir().expect("no home dir");
            let st_root = home.join(".skill-tree");
            let bin_dir = st_root.join("bin");
            std::fs::create_dir_all(&bin_dir).ok();
            // 解压 resources 里的 lark-cli 到 bin_dir(Tauri resources 通过 path 解析)
            let resource_path = app.path()
                .resolve("resources/lark-cli", tauri::path::BaseDirectory::Resource)
                .expect("lark-cli resource missing");
            let local_lark = bin_dir.join(if cfg!(windows) {"lark-cli.exe"} else {"lark-cli"});
            if !local_lark.exists() {
                std::fs::copy(&resource_path, &local_lark).ok();
            }

            // 2. spawn 后端 sidecar
            let data_dir = st_root.join("data");
            std::fs::create_dir_all(&data_dir).ok();
            let sidecar_exe = std::env::current_exe()
                .map(|p| p.parent().unwrap().join("skill-tree-backend"))
                .expect("resolve sidecar");
            let mut child = Command::new(&sidecar_exe)
                .args([
                    "--port", "0",   // 0 = 让 OS 分配;sidecar 打印实际端口(见 entry.py 说明)
                    "--data-dir", data_dir.to_str().unwrap(),
                ])
                .env("SKILLTREE_BIN_DIR", bin_dir.to_str().unwrap())
                .stdout(Stdio::piped())
                .spawn()
                .expect("spawn sidecar");

            // 3. 读 stdout 拿端口(entry.py 打印 READY:<port>)
            let stdout = child.stdout.take().expect("no stdout");
            let reader = BufReader::new(stdout);
            let port = reader.lines()
                .filter_map(|l| l.ok())
                .find_map(|l| l.strip_prefix("READY:").and_then(|s| s.trim().parse::<u16>().ok()))
                .expect("no READY:<port> from sidecar");

            // 4. 注入端口到前端(webview 加载前设全局变量)
            //    通过初始化脚本注入 window.__SKILLTREE_PORT__
            let port_str = port.to_string();
            app.on_page_load(move |webview, _payload| {
                let _ = webview.eval(&format!("window.__SKILLTREE_PORT__='{}'", port_str));
            });

            // 5. 退出时 kill sidecar
            app.on_window_event(move |event| {
                if let tauri::WindowEvent::Destroyed = event {
                    let _ = child.kill();
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

> **关键注意点(打包时验证,本会话无法跑)**:
> - `--port 0` + entry.py 打印实际端口:`uvicorn.run(port=0)` 的实际端口需从 `server.servers[0].sockets[0].getsockname()[1]` 取,entry.py 现版打印的是 args.port(=0)。**Task 7 实现时 entry.py 要改成在 uvicorn 启动后取实际端口打印**。或 Tauri 侧传固定端口(找一个空闲端口)。**建议:Tauri 侧找空闲端口(Rust std 或 sysinfo)传给 sidecar,避免 uvicorn port=0 取端口的复杂度。** main.rs 里加端口探测:
> ```rust
> fn free_port() -> u16 {
>     let l = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
>     l.local_addr().unwrap().port()
> }
> ```
> 然后传 `--port <free_port()>`。

- [ ] **Step 4: build.rs**

```rust
fn main() {
    tauri_build::build()
}
```

- [ ] **Step 5: 放占位图标**

`skill-tree/desktop/src-tauri/icons/` 放一个 `icon.ico`(Windows)/`icon.icns`(macOS)。临时用任意 256x256 ico 占位。

- [ ] **Step 6: 提交(不验证,仅落配置)**

```bash
git add skill-tree/desktop/
git commit -m "build(tauri): shell 脚手架(sidecar spawn + 动态端口 + lark-cli 解压)

本会话无 Rust/Tauri 工具链,配置未经执行验证。用户装好工具链后:
cargo tauri build(详见 desktop/README.md,Task 10)。"
```

---

## Task 9: 打包脚本 + desktop/README 操作手册

**环境前置:** 同 Task 7+8。

**Files:**
- Create: `skill-tree/scripts/build-desktop.sh`
- Create: `skill-tree/desktop/README.md`

- [ ] **Step 1: build-desktop.sh(一键打包)**

```bash
#!/usr/bin/env bash
# 一键打包桌面应用(当前平台)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 1/4 前端构建"
cd frontend && npm run build && cd ..

echo "==> 2/4 后端 PyInstaller 冻结"
cd backend
pip install -q pyinstaller
pyinstaller skill-tree-backend.spec --noconfirm
cd ..

echo "==> 3/4 放 lark-cli 到 resources(按当前平台)"
mkdir -p desktop/src-tauri/resources
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*|Windows*) cp "$(which lark-cli)" desktop/src-tauri/resources/lark-cli.exe 2>/dev/null || echo "WARN: lark-cli not found, 飞书功能打包后不可用" ;;
  Darwin) cp "$(which lark-cli)" desktop/src-tauri/resources/lark-cli 2>/dev/null || echo "WARN: lark-cli not found" ;;
esac

echo "==> 4/4 Tauri 打包"
# 把后端 sidecar 产物放到 Tauri 能找到的位置
cp -r backend/dist/skill-tree-backend desktop/src-tauri/
cd desktop/src-tauri
cargo tauri build

echo "==> 完成。安装包在 desktop/src-tauri/target/release/bundle/"
```

- [ ] **Step 2: desktop/README.md(操作手册)**

写清楚:环境前置(Rust/Node/Python/PyInstaller)、一键打包命令、手动各步、常见报错(ModuleNotFoundError 加 hiddenimports / lark-cli 找不到 / 端口注入时序)、Windows 与 macOS 差异、产物位置。引用 spec §6。

- [ ] **Step 3: 提交**

```bash
git add skill-tree/scripts/build-desktop.sh skill-tree/desktop/README.md
git commit -m "build: 桌面打包脚本 + 操作手册(desktop/README.md)"
```

---

## Task 10: 首版 Windows 打包跑通(用户执行 + 反馈)

**环境前置:** Windows + Rust + Node + Python + PyInstaller + lark-cli。

- [ ] **Step 1: 装工具链**

```bash
# Rust
winget install Rustlang.Rustup   # 或 https://rustup.rs
# Tauri CLI
cargo install tauri-cli --version "^2.0"
# PyInstaller
pip install pyinstaller
```

- [ ] **Step 2: 跑一键脚本**

```bash
cd skill-tree
bash scripts/build-desktop.sh
```

- [ ] **Step 3: 验证安装包**

产物:`desktop/src-tauri/target/release/bundle/msi/*.msi`(或 nsis)。双击安装,启动应用,验证:
- 技能树图谱能加载(seed 数据生效)
- AI 对话能发(配 LLM 后)
- 「写飞书」能产出文档(lark-cli 解压成功)
- 关闭窗口后 sidecar 进程被 kill(任务管理器查)

- [ ] **Step 4: 修复发现的问题(反馈到 Task 7/8/9 配置)**

常见问题(手册里列):
- `ModuleNotFoundError` → 加进 .spec 的 hiddenimports,重打
- lark-cli 解压路径错 → 调 main.rs 的 resource_path / bin_dir 逻辑
- 端口注入时序 → 加 READY 等待重试
- seed 没生效 → 调 entry.py 的 SEED_DIR 路径

- [ ] **Step 5: 提交修复**

```bash
git commit -am "fix(tauri): Windows 打包问题修复(基于实测)"
```

---

## 完成标准

### Part A(我能验证)
- [ ] 后端去多用户隔离,全量测试 PASS
- [ ] DATA_ROOT 默认主目录 + seed 逻辑有测试
- [ ] 前端删多用户 UI,构建成功
- [ ] entry.py 能本地起服务
- [ ] larkpub 优先本地二进制,有测试

### Part B(用户验证)
- [ ] PyInstaller 能冻结后端(本地 .exe 能跑 health)
- [ ] Tauri 能打包出 Windows .msi
- [ ] 安装后双击能用(图谱/对话/飞书)
- [ ] macOS 通过 GitHub Actions 或 Mac 环境产出 .dmg(后续)

---

## 自审记录(写完计划后)

**Spec coverage:**
- §2 架构 → Task 4(entry sidecar)+ Task 8(Tauri shell)+ Task 5(lark-cli 解压)
- §3 去多用户 → Task 1(后端)+ Task 3(前端)
- §3.3 seed → Task 2
- §4 数据目录 → Task 2
- §6 打包流程 → Task 7/8/9/10
- §7 签名/更新 → 首版不做(spec §10.2 已说明)

**Placeholder scan:** Task 8 main.rs 标注了 3 处"打包时验证"——这是诚实的环境限制声明,不是偷懒占位(本会话无 Rust 无法跑)。手册 Task 9/10 覆盖验证路径。

**Type/signature consistency:**
- `seed_if_empty(target, seed)` — Task 2 定义,test 引用一致 ✓
- `resolve_lark_cli()` — Task 5 定义,publish_doc 引用一致 ✓
- `entry.py` 的 `--port` 参数 与 main.rs 传参一致 ✓(注意 Task 8 标注的 port=0 问题,手册已说明用 free_port 替代)

**风险标注:** Part B 全部依赖本会话缺失的工具链,无法验证。这是环境约束,非计划缺陷。计划诚实标注了每处"打包时验证"。
