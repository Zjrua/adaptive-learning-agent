# CLAUDE.md — resume（模块化 LaTeX 简历）

简历是技能树的**果实**。采用「素材与呈现分离」的模块化设计。

## 架构

```
resume/
├── shared/                  ← 素材单一数据源（改这里，所有 profile 同步）
│   ├── personal.tex           姓名/邮箱/手机（占位符集中于此）
│   ├── education.tex          教育背景
│   ├── skills_base.tex        技能碎片(\skillLang 等可复用命令)
│   ├── layout_compact.tex     紧凑排版
│   └── experience/            经历素材库（每条一个文件，带标签注释）
│       ├── harbin_route.tex     RouteTransformer(核心算法项目)
│       ├── physical_data.tex    体质数据建模(科研)
│       ├── media_equipment.tex  器材管理系统(工程)
│       ├── stats_modeling.tex   统计建模大赛
│       ├── awards.tex           美赛+国赛
│       └── leadership.tex       学生工作
├── profiles/                ← 岗位 profile（只做组装+裁剪）
│   ├── recommendation/         推荐算法（build.tex + skills.tex + summary.tex）
│   ├── search/                 搜索算法
│   ├── ads/                    广告算法
│   └── agent/                  AI Agent（预留）
├── templates/               ← 7 套 LaTeX 模板
│   └── billryan/ ★当前在用（中英混合）；其余 sb2nov/jakegut/hijiangtao/luooofan/deedy/awesome-cv
└── build/                   ← 编译脚本 + PDF 输出
    └── build_profile.cmd       一键编译
```

## 核心原则

- **个人信息只在 `shared/personal.tex` 改一处**，所有 profile 自动同步（避免多份简历信息不一致）
- 经历素材放 `shared/experience/`，profile 用 `\input{experience/xxx}` 按需引用
- 新增岗位 = 在 `profiles/` 下建目录，不动素材

## 编译

```cmd
cd resume\build
build_profile.cmd                    REM 编译所有 profile → build\<profile>.pdf
build_profile.cmd recommendation     REM 只编译推荐 profile
```
- 用 **XeLaTeX**（中文模板必须）
- 机制：从 `templates/billryan/` 运行 xelatex，`TEXINPUTS` 注入 shared/ 和 profile 目录
- PDF 输出到 `resume/build/<profile>.pdf`

## 字体

- billryan/hijiangtao/luooofan/deedy 的 `fonts/` **未纳入 git**（体积大）
- `billryan/fonts/` 本地已补全；克隆后需重新获取（见顶层 README）

## 占位符

- 邮箱 `25S112072@stu.hit.edu.cn`、手机 `(+86) 188-0461-8723` 在 `shared/personal.tex`
- 改个人信息只改这一个文件，重新编译即可

## 与技能树的关系

- 技能树节点的 `resource` 用相对路径引用 `../../projects/` 源码（projects 已移出本仓库到 `../projects/`，后端 PROJECTS_DIR 指向那里，前端 fixRes 走 /projects 代理）
- 果实展示板块读 `profiles/` + `build/*.pdf`，技能树 API `/api/templates` `/api/fruits` 扫描本目录
- `data/users/<id>/profile.json` 是前端个人信息板块的数据源，⚠️ 须与 `shared/*.tex` 同步

## Personal Info (for resume)

- **姓名**: 张钧瑞 (Junrui Zhang)
- **学校**: 哈尔滨工业大学 (HIT)
- **学历**: 本科 信息与计算科学 (2020-2024) → 研究生 应用统计 (2025-2028)
- **竞赛**: 2022美赛M奖, 2023国赛黑龙江省二等奖
- **项目**: RouteTransformer推荐路线生成, 体质数据建模(投《体育科学》), 器材管理系统
- **GitHub**: Zjrua

## What Not to Do

- 不要在 resume 模板填虚构经历或数据
- 不要提交编译产物（.aux/.log/.fls 等，已 gitignore）
- 不要改各开源项目代码（projects/ 已移出本仓库到 `../projects/`，是学习参考）
