# CLAUDE.md — 实习技能树

This file gives AI coding agents context for working in this repository.

## Project Overview

实习备战系统。Owner: ***REMOVED*** (Zjrua)，***REMOVED***应用统计研究生(2025-2028)。
**技能树是主体**——可视化学习路径 + 掌握度追踪 + AI 生成；简历和开源项目是**果实**。

> 📄 **[系统设计文档（飞书）](https://my.feishu.cn/docx/M6FGdMITtoZenZxS8X5cRjXXnIQ)** — Agent 系统的完整设计思路与技术路线。
> 📄 **[Agent 实现详解（飞书）](https://my.feishu.cn/docx/T9D6dGuENoWdl7xk3onckfWNncg)** — 代码级实现细节（Planner/Executor/Writer、Reflexion、协议适配、RAG、Prompt 工程、测试体系）。与设计文档互补。
> 本地设计文档：
> - 设计 spec：`docs/design/2026-07-02-agent-depth-design.md`（最新：记忆/短路/提案/Reflexion/Prompt/doc→wiki）
> - 实现计划：`docs/plans/2026-07-02-agent-depth.md`
> - 原始设计：`docs/design/2026-06-30-llm-agent-design.md`

## 架构总览

全栈应用 + AI Agent：**React(前端) + FastAPI(后端,含 Agent/RAG) + JSON 文件存储(单用户)**。
可作本地 web 双进程跑，也可打包成 **Tauri 桌面应用**(Windows .msi / macOS .dmg)。

```
skill-tree/      ← 主体（全栈应用 + AI Agent）
  backend/         FastAPI：API + AI 引擎(Agent/RAG/飞书产出) + 布局/掌握度纯函数
  frontend/        React SPA：DAG 知识图谱 + 多会话 AI 对话 + 侧栏四板块
  desktop/         Tauri 桌面 shell（打包成安装包，见 desktop/README.md）
  data/  单用户数据源（dev 用；桌面应用复制到 ~/.skill-tree/data）
resume/          ← 果实（模块化 LaTeX 简历，被技能树节点引用）
projects/        ← 果实（搜广推开源项目，已移出本仓库到父目录 ../projects/，与 Resume 同级）
```

每个子目录有自己的 CLAUDE.md，讲该目录的架构与约定。**改某部分前先读对应子目录的 CLAUDE.md。**

## 桌面应用打包

本项目是 personal 应用，依赖本机资源(lark-cli / 本地源码 RAG)且数据敏感(api_key/简历)，
**结构上不该云部署**，封装成桌面应用是正确形态。

- 设计：`docs/design/2026-07-02-tauri-desktop-app-design.md`
- 打包手册：`skill-tree/desktop/README.md`（环境前置 / 一键脚本 / 报错排查）
- 一键打包：`bash skill-tree/scripts/build-desktop.sh`（前端 build → PyInstaller 冻结 → Tauri 打包）
- 架构：PyInstaller 冻结 Python 后端成 sidecar → Tauri shell spawn(动态端口) + lark-cli 打进 resources → webview 加载前端 dist

**已验证**（Windows）：PyInstaller 冻结 sidecar health 通过、seed 生效、cargo tauri build 产出 .msi/.exe、release exe 运行 sidecar 正确 spawn。

## Repository Structure

- `skill-tree/` — **主体**。详见 [skill-tree/CLAUDE.md](skill-tree/CLAUDE.md)
  - `backend/` — FastAPI + Agent 内核。详见 [skill-tree/backend/CLAUDE.md](skill-tree/backend/CLAUDE.md)
  - `frontend/` — React+TS。详见 [skill-tree/frontend/CLAUDE.md](skill-tree/frontend/CLAUDE.md)
  - `desktop/` — Tauri 桌面 shell。详见 [skill-tree/desktop/README.md](skill-tree/desktop/README.md)
  - `data/` — 单用户数据（方向树 + profile.json + achievements.json + llm_config.json + lark_config.json）
  - `tools/render.py` — 旧单文件生成器，仅用于生成 `dist/PROGRESS.md`(GitHub 预览)
  - `docs/` — 设计 spec + 实现计划（brainstorming/writing-plans 产出）
- `resume/` — **果实**。模块化 LaTeX 简历。详见 [resume/CLAUDE.md](resume/CLAUDE.md)
  - `shared/` 素材单一数据源 · `profiles/` 岗位组装 · `templates/` 7套模板 · `build/` 编译
- `projects/` — 搜广推开源项目（DeepCTR-Torch, DeepMatch, FuxiCTR 等），**已移出本仓库**到 `../projects/`（父目录，与 Resume 同级）。后端 `PROJECTS_DIR` 默认指向该处
- `docs/` — 学习笔记

## 启动

```bash
cd skill-tree && docker-compose up          # 一键（前端:5173 后端:8000）
# 或开发模式：backend `uvicorn main:app --reload --port 8000` + frontend `npm run dev`
```

## Key Conventions

### 数据流（状态驱动）
```
data/*.json ──GET /api/graph──▶ React state ──▶ DAG 节点+SVG 连线
        ▲                                      │
        └──PATCH /api/task(写盘)◀───勾选──────┘  → 重渲染：掌握度/连线/成就一起更新
```
- 节点位置和 SVG 连线同源于 `useMemo(layout)` → 展开/勾选时同步，永不错位
- 勾选 → `PATCH /api/task` → 后端写 JSON + 返回新图 → React 重渲染

### 多用户隔离
- `data/` 各自独立；user_id 来自 `X-User-Id` 请求头（前端存 localStorage）
- 现在是透传式（无鉴权），将来换 `Depends(get_current_user)` 做真鉴权，接口签名不变
- `llm_config.json` 含 API Key，**已 gitignore，永不入库**

### 知识点与掌握度（核心语义）
- 「知识点」= 一个学习任务。可带 `verify[]` 验收子任务
- 有验收的知识点：**勾完验收才算掌握**（学习任务勾选框置灰=清单）；无验收：勾选即掌握
- 节点点亮(done) = 所有知识点掌握。详见 backend/progress.py

## Common Tasks

- 加技能/方向/成就：改 `data/` 对应 JSON → 浏览器刷新（无需重启后端）
- 新用户：前端「⚙️设置」建用户，或 `POST /api/users`
- 编译简历：`cd resume/build && build_profile.cmd <profile>`
- 更新 GitHub 进度表：`python skill-tree/tools/render.py`

## What Not to Do

- 不要提交 `data/llm_config.json`（含 API Key，已 gitignore）
- 不要提交 `frontend/node_modules/`、`frontend/dist/`、`backend/__pycache__/`
- 不要删除 `../projects/` 下源码（学习参考，已移出本仓库）
- 不要在 resume 模板填虚构经历
- 不要移动 `resume/`（技能树用相对路径引用）

## Tech Stack

- 前端：React 18 + TypeScript + Vite（玉青宝石工坊美学）
- 后端：FastAPI + Python 标准库（ai/layout/progress 零三方依赖）
- 简历：XeLaTeX + ctex
- 部署：docker-compose
