# CLAUDE.md — 实习技能树

This file gives AI coding agents context for working in this repository.

## Project Overview

实习备战系统。Owner: ***REMOVED*** (Zjrua)，***REMOVED***应用统计研究生(2025-2028)。
**技能树是主体**——可视化学习路径 + 掌握度追踪 + AI 生成；简历和开源项目是**果实**。

## 架构总览

全栈应用：**React(前端) + FastAPI(后端) + JSON 文件存储(多用户隔离)**。

```
skill-tree/      ← 主体（全栈应用）
  backend/         FastAPI：API + AI 引擎 + 布局/掌握度纯函数
  frontend/        React SPA：DAG 知识图谱 + 侧栏四板块
  data/users/<id>/ 每用户独立数据（树/profile/成就/llm配置）
resume/          ← 果实（模块化 LaTeX 简历，被技能树节点引用）
projects/        ← 果实（搜广推开源项目，纯跟踪文件非 submodule）
```

每个子目录有自己的 CLAUDE.md，讲该目录的架构与约定。**改某部分前先读对应子目录的 CLAUDE.md。**

## Repository Structure

- `skill-tree/` — **主体**。详见 [skill-tree/CLAUDE.md](skill-tree/CLAUDE.md)
  - `backend/` — FastAPI。详见 [skill-tree/backend/CLAUDE.md](skill-tree/backend/CLAUDE.md)
  - `frontend/` — React+TS。详见 [skill-tree/frontend/CLAUDE.md](skill-tree/frontend/CLAUDE.md)
  - `data/users/<id>/` — 用户数据（方向树 + profile.json + achievements.json + llm_config.json）
  - `tools/render.py` — 旧单文件生成器，仅用于生成 `dist/PROGRESS.md`(GitHub 预览)
- `resume/` — **果实**。模块化 LaTeX 简历。详见 [resume/CLAUDE.md](resume/CLAUDE.md)
  - `shared/` 素材单一数据源 · `profiles/` 岗位组装 · `templates/` 7套模板 · `build/` 编译
- `projects/` — 搜广推开源项目（DeepCTR-Torch, DeepMatch, FuxiCTR 等），纯跟踪文件
- `docs/` — 学习笔记

## 启动

```bash
cd skill-tree && docker-compose up          # 一键（前端:5173 后端:8000）
# 或开发模式：backend `uvicorn main:app --reload --port 8000` + frontend `npm run dev`
```

## Key Conventions

### 数据流（状态驱动）
```
data/users/<id>/*.json ──GET /api/graph──▶ React state ──▶ DAG 节点+SVG 连线
        ▲                                      │
        └──PATCH /api/task(写盘)◀───勾选──────┘  → 重渲染：掌握度/连线/成就一起更新
```
- 节点位置和 SVG 连线同源于 `useMemo(layout)` → 展开/勾选时同步，永不错位
- 勾选 → `PATCH /api/task` → 后端写 JSON + 返回新图 → React 重渲染

### 多用户隔离
- `data/users/<user_id>/` 各自独立；user_id 来自 `X-User-Id` 请求头（前端存 localStorage）
- 现在是透传式（无鉴权），将来换 `Depends(get_current_user)` 做真鉴权，接口签名不变
- `llm_config.json` 含 API Key，**已 gitignore，永不入库**

### 知识点与掌握度（核心语义）
- 「知识点」= 一个学习任务。可带 `verify[]` 验收子任务
- 有验收的知识点：**勾完验收才算掌握**（学习任务勾选框置灰=清单）；无验收：勾选即掌握
- 节点点亮(done) = 所有知识点掌握。详见 backend/progress.py

## Common Tasks

- 加技能/方向/成就：改 `data/users/<id>/` 对应 JSON → 浏览器刷新（无需重启后端）
- 新用户：前端「⚙️设置」建用户，或 `POST /api/users`
- 编译简历：`cd resume/build && build_profile.cmd <profile>`
- 更新 GitHub 进度表：`python skill-tree/tools/render.py`

## What Not to Do

- 不要提交 `data/users/*/llm_config.json`（含 API Key，已 gitignore）
- 不要提交 `frontend/node_modules/`、`frontend/dist/`、`backend/__pycache__/`
- 不要删除 `projects/` 下源码（学习参考）
- 不要在 resume 模板填虚构经历
- 不要移动 `resume/` 或 `projects/`（技能树用相对路径引用）

## Tech Stack

- 前端：React 18 + TypeScript + Vite（玉青宝石工坊美学）
- 后端：FastAPI + Python 标准库（ai/layout/progress 零三方依赖）
- 简历：XeLaTeX + ctex
- 部署：docker-compose
