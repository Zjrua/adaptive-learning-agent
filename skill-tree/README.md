# 🌳 技能树系统（Skill Tree）

> 本仓库的**主体**。React + FastAPI 全栈应用：可视化知识图谱 + 清单驱动掌握度 + 成就反馈。
> 简历（`resume/`）和开源项目（`projects/`）是这棵树结出的**果实**，被节点按路径引用。

## 技术架构

```
skill-tree/
├── backend/                    FastAPI (Python)
│   ├── main.py                 API: /api/graph, /api/task, /api/profile, /api/templates, /api/fruits
│   ├── layout.py               DAG 布局纯函数（合并去重 + 拓扑分层 + x/y 坐标）
│   ├── progress.py             掌握度/成就计算（验收勾选=掌握该知识点）
│   ├── requirements.txt        fastapi, uvicorn, pydantic
│   └── Dockerfile
├── frontend/                   React + TypeScript (Vite)
│   ├── src/
│   │   ├── App.tsx             侧栏 SPA + hash 路由(4 板块)
│   │   ├── SkillTree.tsx       DAG 画布：useMemo(layout) 驱动节点+SVG连线（同源→不错位）
│   │   ├── NodeCard.tsx        节点卡片 + 知识点/验收（清单语义）
│   │   ├── panels/             Profile / Templates / Fruit 三板块
│   │   └── Achievement.tsx     成就花田
│   └── Dockerfile
├── data/                       ✏️ 数据源（后端读写，见下）
├── tools/render.py             旧的单文件生成器（仍生成 PROGRESS.md 给 GitHub 预览）
└── docker-compose.yml          一键起 backend(8000) + frontend(5173)
```

## 快速开始

### 方式一：docker-compose（推荐）
```bash
cd skill-tree
docker-compose up              # 前端 http://localhost:5173  后端 http://localhost:8000
```

### 方式二：本地分别启动（开发热更新）
```bash
# 终端 1：后端
cd skill-tree/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 终端 2：前端
cd skill-tree/frontend
npm install
npm run dev                    # 自动代理 /api → :8000
```

## 飞书文档归档(可选)

Agent 产出的学习笔记/复习卡/周报可发布并归档到飞书知识库:

1. 安装并登录 lark-cli:`lark-cli auth login`
2. 在「设置」→「飞书知识库归档」选择一个 wiki 空间(或留空,仅生成单篇文档)
3. 对话里说「整理个 X 的笔记」「生成复习卡」「本周周报」,Agent 产出文档卡片,点「写飞书」即归档

> 文档通过 `docs +create` 生成后用 `wiki +move` 移入选定知识库空间;未配置空间时仅生成单篇飞书文档。

## 数据源（`data/`）

```
data/
├── recommendation.json   推荐方向节点（含验收子任务）
├── search.json           搜索方向节点
├── ads.json              广告方向节点
├── profile.json          个人信息（⚠️ 须与 resume/shared/*.tex 同步）
└── achievements.json     成就定义
```

**知识点与验收**：每个学习任务可带 `verify[]` 子任务。
- 有验收的知识点：**勾完验收才算掌握**（学习任务勾选框置灰，仅清单提示）
- 无验收的知识点：勾学习任务本身即掌握
- 节点点亮(done) = 所有知识点都掌握

```jsonc
{"id":"nn","title":"nn.Module 搭模型 / 训练循环","done":true,
 "verify":[
   {"id":"v1","title":"能默写一个完整训练循环","done":false}
 ]}
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/graph` | 合并去重 + 布局 + 掌握度 + 成就 + 总览 |
| PATCH | `/api/task` | 勾选/取消任务（写回 JSON），返回更新后的图 |
| GET | `/api/profile` | 个人信息 |
| GET | `/api/templates` | 简历模板列表 |
| GET | `/api/fruits` | 果实（简历成品） |
| `/projects/*`, `/resume/*` | 静态托管 | 源码链接、PDF 打开 |

## 泛化与设计

- **目录驱动**：`data/` 丢一个方向 JSON 即自动并入图谱，无需改代码
- **单画布 DAG**：所有方向合并去重成一张图，跨方向同名节点(python/pytorch 等)只画一次
- **基础在上**：depth 0 的根节点在画布顶部，向下生长
- **悬停高亮路径**：鼠标悬停节点 → 上游祖先 + 下游后代高亮，其余淡化
- **展开避让**：点开节点详情 → 下方节点下推，**节点和连线同源于一份 layout → 永不错位**

详见 [CLAUDE.md](../CLAUDE.md)。
