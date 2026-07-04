# CLAUDE.md — skill-tree（技能树全栈应用）

本目录是项目的**主体**：React + FastAPI 全栈应用 + AI Agent。可作本地 web 双进程跑，也可打包成 Tauri 桌面应用。

## 架构

```
skill-tree/
├── backend/      FastAPI 后端（见 backend/CLAUDE.md）
│   ├── agent/    AI Agent 内核（Planner→Executor→Writer + Reflexion，见下）
│   ├── rag/      混合检索（源码 AST + 论文 + 图谱/简历）
│   ├── main.py   API + Agent 对话(SSE)+ 数据落点
│   ├── entry.py  PyInstaller sidecar 入口（桌面打包用）
│   └── larkpub.py 飞书文档产出(lark-cli subprocess)
├── frontend/     React+TS 前端（见 frontend/CLAUDE.md）
├── desktop/      Tauri 桌面 shell（见 desktop/README.md，打包成 .msi/.dmg）
├── data/
│   └── users/default/    单用户数据（dev 源；桌面应用复制到 ~/.skill-tree/data）
│       ├── *.json            方向树（recommendation/search/ads/agent...，目录驱动自动发现）
│       ├── profile.json      个人信息（⚠️ 须与 resume/shared/*.tex 同步）
│       ├── achievements.json 成就定义
│       └── llm_config.json   大模型配置（含 API Key，已 gitignore）
├── tools/
│   └── render.py            旧单文件生成器 → dist/PROGRESS.md（GitHub 预览用，主流程已不用）
├── docker-compose.yml       一键起 frontend(:5173) + backend(:8000)（dev 用）
└── README.md
```

## 启动

```bash
# 开发（本地 web 双进程）:
cd backend && python -m uvicorn main:app --port 8000 --reload
cd frontend && npm run dev            # :5173，代理 /api → :8000

# 桌面应用打包（详见 desktop/README.md）:
bash scripts/build-desktop.sh         # 前端 build → PyInstaller 冻结 → Tauri 打包
```

## 数据落点（重要）

- **开发**：`DATA_ROOT` env 或默认 `data/users/default`（项目内）
- **桌面应用**：`~/.skill-tree/data`（用户主目录，升级/卸载不丢）
- 首次启动若空，从打包内置 seed 复制初始技能树/profile/成就（排除 chat_history）
- env 覆盖：`DATA_ROOT` / `RESUME_DIR` / `PROJECTS_DIR` / `SEED_DIR`
- **已去掉多用户隔离**（单机应用）：无 `X-User-Id` 头、无 `/api/users`

## 数据流

1. 前端 `GET /api/graph` → 后端读 `DATA_ROOT/*.json`
2. 后端 `layout.compute_layout` 合并去重所有方向 + 算 DAG 布局 → 返回节点+边+画布尺寸
3. 后端 `progress.node_mastery` 算每个节点掌握度 → 附到节点上
4. 前端 React 渲染 DAG（节点绝对定位 + SVG 贝塞尔连线，同源于 useMemo(layout)）
5. 勾选 → `PATCH /api/task` → 后端写回 JSON + 失效 graph 快照缓存 + 返回新图 → 重渲染

## AI Agent（核心特性）

三层架构 + 六个设计点（详见 `docs/superpowers/specs/2026-07-02-agent-depth-design.md`）：
- **记忆**：前端发最近 12 条历史，后端无状态注入 Executor
- **短路**：Planner 分类后 chat 单步直答，不滥用 ReAct
- **提案闭环**：add_node/add_tasks 产 node_proposal 卡片，用户确认才 apply
- **Reflexion**：ReAct 出草稿后自我校验，遗漏续跑 1 轮（仅 query/produce）
- **Prompt 工程**：三套分层 prompt 带 few-shot + ReAct 解析正则化 + 回归测试
- **飞书产出**：笔记/复习卡/周报 → docs+create → wiki+move 归档知识库

## 关键约定

- **数据是唯一真相**：所有内容存 JSON，改 JSON 即改应用
- **目录驱动泛化**：`DATA_ROOT` 下每个 `*.json`（除 profile/achievements/llm_config/chat_history/lark_config）自动识别为一个方向
- **跨方向共享**：同名 node id（python/pytorch 等）在多方向 JSON 用同 id，后端自动去重
- **布局在后端算**：`backend/layout.py` 算定 x/y/depth，前端只渲染
- **掌握度在后端算**：`backend/progress.py`，验收语义（有验收→勾完验收才算掌握）
- **graph 快照缓存**：`SessionStore` 缓存 graph，写操作（patch_task/apply_*）失效

## 不动的部分

- `data/users/default/` 是 owner 的真实数据（搜广推+agent），也是桌面应用的 seed 源，不要覆盖
- `tools/render.py` 保留作 GitHub 进度表生成，逻辑与 backend/layout.py + progress.py 平行（改动需同步两边）
