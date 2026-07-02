# 🌳 实习技能树

一个**状态驱动**的实习备战系统：用可视化的技能树规划学习路径、追踪掌握进度、解锁成就；简历和开源项目是这棵树结出的**果实**。

> 📄 **[系统设计文档（飞书）](https://my.feishu.cn/docx/M6FGdMITtoZenZxS8X5cRjXXnIQ)** — 完整设计思路与技术路线（Agent 三层架构 / RAG 混合检索 / Reflexion 自校验 / 飞书文档产出闭环 / 面试讲法）。本地 spec 与实现计划见 `docs/superpowers/`。

> Obsidian / Notion / 飞书是对**已有知识**的总结；技能树是对**未来学习路径**的规划，有明确的进度反馈。

```
   找一个实习方向 → AI 自动种一棵树 → 边学边点亮 → 结出简历果实
              │
   ┌──────────┼──────────┐
   ▼          ▼          ▼
 🎯推荐      🔍搜索      📢广告   🤖Agent    ← 方向(着色分支)
   │     共享基础汇成根系            │
   ▼                               ▼
 📄 简历(PDF)                    📦 开源项目      ← 果实
```

## 技术栈

**React + FastAPI + docker-compose 全栈应用**

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | React 18 + TypeScript + Vite | 单页应用，玉青宝石工坊美学，DAG 知识图谱 |
| 后端 | FastAPI (Python) | 多用户隔离 + AI 生成引擎，零三方依赖(ai/layout/progress 纯标准库) |
| 数据 | JSON 文件 | 每用户独立 `data/users/<id>/`，无数据库 |
| 部署 | docker-compose | 一键起 frontend(:5173) + backend(:8001) |

## 快速开始

### docker-compose（推荐）
```bash
cd skill-tree
docker-compose up          # 前端 http://localhost:5173  后端 http://localhost:8000
```

### 本地开发
```bash
# 终端 1：后端
cd skill-tree/backend
pip install -r requirements.txt
python -m uvicorn main:app --port 8000 --reload

# 终端 2：前端
cd skill-tree/frontend
npm install
npm run dev                # http://localhost:5173（代理 /api → :8000）
```

首次进入：**新用户自动跳初始化**（建用户 → 配模型 → 贴 JD → AI 生成技能树）。已有用户从侧栏底部「⚙️设置」进入。

## AI Agent（工具调用 + RAG + 飞书文档产出）

右下角 ✦ 悬浮按钮打开 **AI 学习助手**——它不是单轮生成器，而是一个会调工具、能检索知识、可产文档的 Agent：

- **工具调用**：自主决定读图谱进度 / 查节点 / 检索知识 / 加节点，混合协议（原生 function calling 优先，指令式回退）
- **RAG 知识检索**：把 `../projects` 开源项目源码建成向量索引（AST 切 chunk），混合检索（向量 + 图谱 + 论文），带引用编号
- **ReAct 推理循环**：Planner 意图分流 → Executor 工具循环 → Writer 文档产出，最大 6 步防发散
- **飞书文档产出**：一键把学习笔记 / 复习卡 / 周报发到飞书

**飞书文档产出配置**（首次使用需登录）：

```bash
lark-cli auth login        # 按提示完成飞书授权
lark-cli --version         # 确认已安装（≥1.0.60）
```

**构建 RAG 知识库索引**（让 Agent 能检索你的开源项目源码；配好 LLM 后）：

```bash
curl -X POST http://localhost:8000/api/rag/build-index -H "X-User-Id: default"
curl http://localhost:8000/api/rag/status -H "X-User-Id: default"   # 查索引状态
```

装 numpy 可加速向量检索（可选，不装也能跑，退化为纯标准库）：

```bash
pip install numpy
```

## 目录结构

```
├── skill-tree/              ← 【主体】技能树全栈应用
│   ├── backend/               FastAPI：main.py(API) + ai.py(大模型) + layout.py(DAG布局) + progress.py(掌握度)
│   ├── frontend/              React+TS：App.tsx(SPA) + SkillTree.tsx(DAG) + NodeCard.tsx + SetupPanel.tsx + AiModal.tsx
│   ├── data/users/<id>/       每用户独立数据：方向树JSON + profile.json + achievements.json + llm_config.json
│   ├── tools/render.py        旧单文件生成器（生成 PROGRESS.md 供 GitHub 预览）
│   └── docker-compose.yml
├── resume/                  ← 【果实】模块化 LaTeX 简历
│   ├── shared/                素材单一数据源(personal/education/experience/skills)
│   ├── profiles/              岗位 profile(推荐/搜索/广告/agent)
│   ├── templates/             7 套 LaTeX 模板
│   └── build/                 编译脚本 + PDF 输出
├── docs/                    学习笔记
│
../projects/                 ← 【果实】搜广推开源项目(已移出本仓库到父目录，与 Resume 同级)
```

## 核心功能

- **单画布 DAG 知识图谱**：所有方向合并去重成一张图，基础在上向下生长，贝塞尔曲线连线
- **清单驱动掌握度**：每个知识点配验收任务（能默写/讲清/手算），验收全勾才算掌握
- **悬停高亮学习路径**：悬停节点或方向标签 → 高亮上下游路径，其余淡化
- **AI 生成技能树**：支持 DeepSeek/MiMo/智谱/Qwen/Moonshot/自定义，输入 JD 自动生成
- **多用户隔离**：每用户独立数据目录，API Key 安全存储（gitignore 排除）
- **成就系统**：铜/银/金三级，按掌握度/分支完成自动解锁
- **侧栏 SPA**：技能树 / 个人信息 / 简历模板 / 果实展示 四板块 + 底部设置

## 编译简历

```cmd
cd resume\build
build_profile.cmd                    :: 编译所有 profile → build\<profile>.pdf
build_profile.cmd recommendation     :: 只编译推荐算法岗
```

详见 [resume/CLAUDE.md](resume/CLAUDE.md)。

## 设计原则

- **改数据只动 JSON**：加技能/方向/成就只改 `data/users/<id>/`，浏览器刷新即生效
- **零依赖后端**：ai/layout/progress 纯 Python 标准库，Windows 直接能跑
- **不填虚构技能**：节点默认 locked，由用户逐步推进
- **平滑演进**：用户抽象层预留鉴权/加密钩子，将来加登录不改业务代码

## 许可

技能树系统（`skill-tree/`）为本人原创；各模板和开源项目遵循其原始许可证。
