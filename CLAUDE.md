# CLAUDE.md — Internship Preparation

This file provides context for AI coding agents (Claude, Copilot, etc.) working in this repository.

## Project Overview

实习准备项目。Owner: ***REMOVED*** (Zjrua)，***REMOVED***应用统计研究生(2025-2028)。
目标岗位: 推荐算法/搜索算法/广告算法实习。

**架构核心：技能树是主体，简历和项目是果实。**
- `skill-tree/` — 主体：可视化学习路径 + 进度 + 成就（JSON 数据源 + 生成器）
- `resume/` — 果实：模块化 LaTeX 简历（节点达成后更新素材 = 结实）
- `projects/` — 果实：搜广推开源项目（被技能树节点按路径引用）

## Repository Structure

- `skill-tree/` — **主体**。React(Frontend) + FastAPI(Backend) 全栈：`data/*.json` 数据源 → `/api/graph` 合并去重布局 → 单画布 DAG。`backend/`(layout/progress 纯函数 + API) + `frontend/`(React SPA) + `docker-compose.yml`。详见 `skill-tree/README.md`
- `resume/templates/` — 7套 LaTeX 简历模板（sb2nov, jakegut, billryan, hijiangtao, luooofan, deedy, awesome-cv）
- `resume/shared/` — **模块化素材层**（单一数据源，所有 profile 共用，见下文）
- `resume/profiles/` — **岗位 profile**（每个岗位一个目录，组装+裁剪素材）
- `resume/build/` — 编译脚本 `build_profile.cmd` + PDF 输出
- `projects/` — 搜广推方向开源项目（DeepCTR-Torch, DeepMatch, FuxiCTR, RecSystem-Pytorch, OpenOneRec, generative-recommenders, HLLM）——纯跟踪文件(非 submodule)，技能树节点用相对路径引用
- `docs/` — 学习笔记

## Key Conventions

### Skill Tree（主体）

React + FastAPI 全栈应用。**JSON 是唯一数据源**，前端状态驱动渲染，彻底告别手写 DOM 的时序/错位 bug。

#### 启动
```bash
cd skill-tree && docker-compose up     # 前端 :5173  后端 :8000
# 或开发：后端 uvicorn main:app --reload  +  前端 npm run dev（vite 代理 /api→:8000）
```

#### 架构
- `backend/` FastAPI：`main.py`(API) + `layout.py`(DAG 布局纯函数) + `progress.py`(掌握度/成就)。读写 `data/*.json`，勾选落盘。
- `frontend/` React+TS(Vite)：`App.tsx`(侧栏 SPA, hash 路由) + `SkillTree.tsx`(DAG 画布) + `NodeCard.tsx`(节点/知识点/验收) + `panels/`(其余板块)
- `data/` 数据源；`tools/render.py` 旧单文件生成器，保留用于生成 `dist/PROGRESS.md`(GitHub 预览)

#### 数据流（状态驱动，解决历史 bug）
```
data/*.json ──GET /api/graph──▶ React state ──▶ 节点+SVG连线 同源于 useMemo(layout)
     ▲                              │
     └──PATCH /api/task(写盘)◀──勾选──┘  → 重渲染：进度/删除线/连线一起更新，不错位
```
**连线不错位的根因**：节点位置和 SVG 连线都从同一份 `useMemo(computeLayout)` 派生；展开避让改变 layout，两者同步。

#### 四板块（侧栏 hash 路由 `#tree`/`#profile`/`#templates`/`#fruit`）
- 🌳 技能树：DAG + 仪表盘 + 成就花田
- 👤 个人信息：读 `data/profile.json`
- 📄 简历模板：扫描 `resume/templates/`（`TEMPLATE_META` 在 main.py）
- 🍎 果实展示：扫描 `resume/profiles/` + `resume/build/*.pdf`，「打开 PDF」走 `/resume/build/<id>.pdf`

#### 数据格式
- 节点(node)：`{id, name, category, status, depends_on, tasks[]}`
- **知识点与验收**：学习任务可带 `verify[]`。有验收→勾完验收才算掌握（学习任务勾选框置灰=清单）；无验收→勾学习任务即掌握。节点 done = 所有知识点掌握
- `resource` 相对路径链论文或 `projects/` 源码
- **跨方向共享**：同名 node id 在多方向 JSON 用同 id，后端 merge_nodes 自动去重
- `depends_on` 可填节点 id 或分支 id（layout.py normalize_deps 解析成分支末端节点）
- **profile.json**：⚠️ 与 `resume/shared/*.tex` 是同一信息两份表达，改一处同步另一处

#### 布局算法（backend/layout.py: compute_layout）
- 合并去重 → 拓扑分层 → 深度=从根出发最长路径 → **基础(depth 0)在顶部**向下生长
- 常量 NODE_W/ROW_GAP 等在 layout.py 顶部（前端 SkillTree.tsx 必须与之对应）

#### 关键约定
- **改技能/成就/个人信息只动 `data/*.json`**，后端实时读写，无需重新生成
- **`frontend/dist`、`backend/__pycache__` 是产物**，不提交
- **新增方向**：往 `data/` 丢 JSON（目录驱动自动发现）
- **不填虚构技能**：节点 status 默认 locked，由 owner 推进
- **resource 用相对路径引用 `projects/`/`resume/`**，不移动这些目录
- 改前端组件后 `npm run build` 重新构建（开发模式热更新免此步）

#### 常见任务
- 加节点/验收：改 `data/<方向>.json`（浏览器刷新即生效，无需重建）
- 加新方向：复制现有方向 JSON → 改内容 → 刷新（自动发现）
- 加成就：改 `data/achievements.json` → 刷新
- 改个人信息：改 `data/profile.json`（⚠️ 同步 `resume/shared/*.tex`）→ 刷新
- 新增 PDF：`build_profile.cmd` 编译后，果实板块自动发现
- 更新 GitHub 进度表：`python skill-tree/tools/render.py`（生成 PROGRESS.md）

### LaTeX Resume

#### 模块化简历架构（重要）
简历采用 **素材与呈现分离** 的模块化设计：

```
resume/
├── shared/                  ← 素材单一数据源（改这里，所有 profile 同步）
│   ├── personal.tex         ← 姓名/邮箱/手机（占位符集中于此！）
│   ├── education.tex        ← 教育背景
│   ├── skills_base.tex      ← 技能碎片（\skillLang 等可复用命令）
│   └── experience/          ← 经历素材库（每条经历一个文件，带标签注释）
│       ├── physical_data.tex
│       ├── stats_modeling.tex
│       └── awards.tex
└── profiles/                ← 岗位 profile（只做组装+裁剪）
    ├── recommendation/      ← 推荐算法（build.tex + skills.tex + summary.tex）
    ├── search/              ← 搜索算法
    ├── ads/                 ← 广告算法
    └── agent/               ← 预留（AI Agent 方向，未实现）
```

**核心原则**：
- **个人信息只在 `shared/personal.tex` 改一处**，所有 profile 自动同步（避免多份简历信息不一致）
- 经历素材放 `shared/experience/`，profile 用 `\input{experience/xxx}` 按需引用
- 新增岗位 = 在 `profiles/` 下建目录，不动素材

#### 编译方式
- 编译用 **XeLaTeX**（中文模板必须）
- **统一用 `build/build_profile.cmd`** 一键编译（处理了 cls 字体路径 + TEXINPUTS 注入）：
  ```
  cd resume/build
  build_profile.cmd                    # 编译所有 profile
  build_profile.cmd recommendation     # 只编译推荐 profile
  ```
- PDF 输出到 `resume/build/<profile>.pdf`
- 编译机制：从 `templates/billryan/` 目录运行 xelatex（因 cls 用相对路径引用字体），通过 `TEXINPUTS` 把 `shared/` 和 profile 目录注入 LaTeX 搜索路径

#### 字体说明
- `billryan`、`hijiangtao`、`luooofan`、`deedy` 的 `fonts/` 目录均**未纳入版本控制**（体积大）
- `billryan/fonts/` 已在本地补全（Main 西文 + zh_CN-Adobe 中文 + fontawesome），克隆后需重新获取
- 获取方式：`git clone -b zh_CN git@github.com:billryan/resume.git` 后复制其 `fonts/` 目录

#### 占位符（待替换）
- 邮箱 `your.email@example.com`、手机 `(+86) xxx-xxxx-xxxx` 在 `shared/personal.tex`
- 收到真实信息后只改这一个文件，重新编译即可

#### 旧的单文件简历
- 各模板目录下的 `zhang_junrui.tex` 是**早期的单文件版本**（内容已迁移到模块化架构）
- 模块化 profile 是当前主推方式，旧文件保留作参考

### Personal Info (for resume)
- **姓名**: ***REMOVED***
- **学校**: ***REMOVED*** (HIT)
- **学历**: 本科 信息与计算科学 (2020-2024) → 研究生 应用统计 (2025-2028)
- **技能**: Python, PyTorch, LaTeX, C++(基础)
- **邮箱/手机**: 占位符，待替换
- **竞赛**: 2022美赛M奖, 2023国赛黑龙江省二等奖
- **项目**: physical_data论文投《体育科学》, 2026统计建模大赛研究生组(***REMOVED***)
- **GitHub**: Zjrua

## What Not to Do

- 不要删除 `projects/` 下的源代码文件（这些是学习参考）
- 不要修改各开源项目的代码逻辑（如需实验改动，另建分支或副本）
- 不要在 resume 模板中填入虚构的经历或数据
- 不要将编译产物（.aux, .log, .fls 等）提交到 git
- 不要手动改 `skill-tree/dist/`（生成产物，已 gitignore）；改技能树只动 `skill-tree/data/*.json` 再跑 render.py
- 不要移动 `resume/` 或 `projects/`（技能树用相对路径引用它们）

## Common Tasks

### 编译简历
```cmd
cd resume\build
build_profile.cmd                    REM 编译所有 profile，输出到 build\<profile>.pdf
build_profile.cmd recommendation     REM 只编译推荐 profile
```

### 更新个人信息
**只改 `resume/shared/personal.tex` 一个文件**（邮箱/手机/姓名），所有 profile 自动同步。

### 新增一个岗位 profile
1. 在 `resume/profiles/<new-role>/` 下建目录
2. 复制 `recommendation/` 的 `build.tex` / `skills.tex` / `summary.tex`
3. 修改 `summary.tex`（针对该岗位的自我评价）和 `skills.tex`（重组技能排序）
4. 运行 `build_profile.cmd <new-role>` 验证

### 查看项目代码
直接在 `projects/` 下阅读源码，无需安装（除非要运行实验）。

## Tech Stack

- **LaTeX**: XeLaTeX + ctex (中文模板)
- **Python**: 3.x + PyTorch (projects/ 下的模型代码)
- **Git**: SSH protocol (git@github.com:Zjrua/)
