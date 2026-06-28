# CLAUDE.md — skill-tree（技能树全栈应用）

本目录是项目的**主体**：React + FastAPI 全栈应用。

## 架构

```
skill-tree/
├── backend/      FastAPI 后端（见 backend/CLAUDE.md）
├── frontend/     React+TS 前端（见 frontend/CLAUDE.md）
├── data/
│   └── users/<user_id>/    每用户独立数据目录
│       ├── *.json            方向树（recommendation/search/ads/agent...，目录驱动自动发现）
│       ├── profile.json      个人信息（⚠️ 须与 resume/shared/*.tex 同步）
│       ├── achievements.json 成就定义
│       └── llm_config.json   大模型配置（含 API Key，已 gitignore）
├── tools/
│   └── render.py            旧单文件生成器 → dist/PROGRESS.md（GitHub 预览用，主流程已不用）
├── docker-compose.yml       一键起 frontend(:5173) + backend(:8000)
├── Dockerfile（backend / frontend 各一个）
└── README.md
```

## 启动

```bash
docker-compose up                    # 生产/一键
# 开发：
cd backend && python -m uvicorn main:app --port 8000 --reload
cd frontend && npm run dev            # :5173，代理 /api → :8000
```

## 数据流

1. 前端 `GET /api/graph`（带 `X-User-Id` 头）→ 后端读 `data/users/<id>/*.json`
2. 后端 `layout.compute_layout` 合并去重所有方向 + 算 DAG 布局 → 返回节点+边+画布尺寸
3. 后端 `progress.node_mastery` 算每个节点掌握度 → 附到节点上
4. 前端 React 渲染 DAG（节点绝对定位 + SVG 贝塞尔连线，同源于 useMemo(layout)）
5. 勾选 → `PATCH /api/task` → 后端写回 JSON + 返回新图 → 重渲染

## 关键约定

- **数据是唯一真相**：所有内容（技能/方向/成就/个人信息）存 JSON，改 JSON 即改应用
- **目录驱动泛化**：`data/users/<id>/` 下每个 `*.json`（除 profile/achievements/llm_config）自动识别为一个方向
- **跨方向共享**：同名 node id（python/pytorch/ml_basics 等）在多方向 JSON 用同 id，后端 merge_nodes 自动去重
- **布局在后端算**：`backend/layout.py` 算定 x/y/depth，前端只渲染。常量 NODE_W/ROW_GAP 等在 layout.py 顶部，前端 SkillTree 必须对应
- **掌握度在后端算**：`backend/progress.py`，验收语义（有验收→勾完验收才算掌握）
- **旧 render.py 仅用于 PROGRESS.md**：主流程（前端 SPA）不依赖它；改前端/后端不用跑它

## 不动的部分

- `data/users/default/` 是 owner 的真实数据（搜广推+agent），不要覆盖
- `tools/render.py` 保留作 GitHub 进度表生成，逻辑与 backend/layout.py + progress.py 平行（改动需同步两边）
