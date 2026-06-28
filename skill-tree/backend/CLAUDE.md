# CLAUDE.md — skill-tree/backend（FastAPI 后端）

零三方依赖（ai/layout/progress 纯标准库），仅 fastapi+uvicorn+pydantic。

## 文件

| 文件 | 职责 |
|------|------|
| `main.py` | FastAPI 应用：所有 API 端点 + 用户/存储抽象 + LLM 配置 |
| `ai.py` | 大模型引擎：OpenAI 兼容客户端 + 5 供应商预置 + 三级生成(树/方向/节点) + list_models |
| `layout.py` | DAG 布局纯函数：合并去重 + 拓扑分层 + 深度 + 居中 x/y 坐标 |
| `progress.py` | 掌握度纯函数：知识点 mastery + 节点状态 + 成就判定 |
| `requirements.txt` | fastapi, uvicorn, pydantic |
| `Dockerfile` | python:3.12-slim |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/graph` | 合并去重+布局+掌握度+成就+总览（按 X-User-Id 隔离） |
| PATCH | `/api/task` | 勾选任务（写回 JSON），返回新图 |
| GET | `/api/profile` | 个人信息 |
| GET | `/api/templates` | 简历模板列表（扫描 resume/templates/） |
| GET | `/api/fruits` | 果实（扫描 resume/profiles/ + build/*.pdf） |
| GET | `/api/users` | 列出用户 |
| POST | `/api/users` | 新建用户（初始化空 profile + 默认成就） |
| GET/PUT | `/api/llm-config` | 读/存该用户 LLM 配置 |
| POST | `/api/llm-config/test` | 测连通（发 hello） |
| POST | `/api/llm-config/models` | 拉取模型列表（/models 端点） |
| GET | `/api/providers` | 5 供应商预置 |
| POST | `/api/ai/generate-tree` | AI 生成整树 |
| POST | `/api/ai/generate-direction` | AI 生成单方向 |
| POST | `/api/ai/generate-node` | AI 生成/补充节点 |
| POST | `/api/ai/apply-tree` | 写回生成的树 |
| POST | `/api/ai/apply-direction` | 写回单方向 |
| 静态 | `/projects/*`, `/resume/*` | 托管源码链接、PDF |

## 用户与存储抽象

- `resolve_user(x_user_id)` → user_id（校验合法性，缺省 default）
- `user_dir(uid)` → `data/users/<uid>/`（自动创建）
- 所有 load_trees/load_achievements/get_profile/patch_task 接 `data_dir` 参数
- **平滑演进**：将来 `resolve_user` 换成 `Depends(get_current_user)` 做真鉴权，业务代码不变
- **API Key**：`data/users/<id>/llm_config.json`，已 gitignore。预留 secrets.py 加密钩子

## 布局算法（layout.py）

- `merge_nodes`：合并所有方向节点，按 id 去重（tasks 多者胜），建方向归属
- `normalize_deps`：depends_on 可填 node id 或分支 id（解析成分支末端节点）
- `compute_depths`：从根(无依赖)出发的最长路径，迭代松弛
- `compute_layout`：每行在画布内**居中**（start_x = (canvas_w - row_w)/2），基础(depth 0)在顶部
- 常量：NODE_W=180, NODE_H=92, COL_GAP=28, ROW_GAP=148, CANVAS_PAD=48（前端必须对应）

## 掌握度语义（progress.py）

- `point_mastered(task)`：有 verify→全勾才算掌握；无 verify→task.done
- `node_mastery(node)`：(已掌握知识点数, 总知识点数, pct)
- `node_status`：全掌握=done，有进展=learning，无=locked

## AI 引擎（ai.py）

- OpenAI 兼容 `/chat/completions`，urllib 零依赖
- 5 预置：DeepSeek/MiMo/智谱GLM(/v4)/Qwen(/compatible-mode)/Moonshot + 自定义
- 三级生成：`generate_tree`(整树) / `generate_direction`(单方向) / `generate_node`(节点)
- 健壮性：JSON 解析失败自动重试 + `_norm_*` schema 规范化 + 校验
- `list_models`：调 /models 端点拉模型列表（有些平台返回不全，前端用 combobox 可手输）

## 路径解析

- `DATA_ROOT` = `skill-tree/data`（env 可覆盖）
- `RESUME_DIR` / `PROJECTS_DIR` = 上级 resume / 父目录 projects（env 可覆盖，容器挂载用）
- **projects 已移出本仓库**：默认 `PROJECTS_DIR = HERE.parent.parent.parent / "projects"` = `D:/Projects/projects`（与 Resume 同级）

## 开发约定

- 改布局/掌握度逻辑：同时改 layout.py/progress.py 和 tools/render.py（保持一致）
- 加新 API：在 main.py 加路由，函数签名加 `x_user_id` 头参数
- 加供应商：ai.py 的 PROVIDER_PRESETS 列表加一项
