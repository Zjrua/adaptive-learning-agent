# CLAUDE.md — Internship Preparation

This file provides context for AI coding agents (Claude, Copilot, etc.) working in this repository.

## Project Overview

搜广推（搜索/广告/推荐系统）实习准备项目。Owner: 张钧瑞 (Zjrua)，哈工大应用统计研究生(2025-2028)。
目标岗位: 推荐算法/搜索算法/广告算法实习。

## Repository Structure

- `resume/templates/` — 7套 LaTeX 简历模板（sb2nov, jakegut, billryan, hijiangtao, luooofan, deedy, awesome-cv）
- `projects/` — 搜广推方向开源项目（DeepCTR-Torch, DeepMatch, FuxiCTR, RecSystem-Pytorch, OpenOneRec, generative-recommenders, HLLM）
- `docs/` — 学习笔记和文档

## Key Conventions

### LaTeX Resume
- 编译用 **XeLaTeX**（中文模板必须）
- 当前简历文件名: `zhang_junrui.tex`（各模板目录下）
- `hijiangtao` 和 `luooofan` 模板的 `fonts/` 目录未纳入版本控制，编译时需从原项目获取字体
- `deedy` 模板字体路径可能需要调整
- 个人信息占位符: 邮箱和手机号仍为占位符，需等用户提供后统一替换
- 修改简历后需编译验证 PDF 输出正确

### Personal Info (for resume)
- **姓名**: 张钧瑞
- **学校**: 哈尔滨工业大学 (HIT)
- **学历**: 本科 信息与计算科学 (2020-2024) → 研究生 应用统计 (2025-2028)
- **技能**: Python, PyTorch, LaTeX, C++(基础)
- **邮箱/手机**: 占位符，待替换
- **竞赛**: 2022美赛M奖, 2023国赛黑龙江省二等奖
- **项目**: physical_data论文投《体育科学》, 2026统计建模大赛研究生组(TJJM20260414180979)
- **GitHub**: Zjrua

## What Not to Do

- 不要删除 `projects/` 下的源代码文件（这些是学习参考）
- 不要修改各开源项目的代码逻辑（如需实验改动，另建分支或副本）
- 不要在 resume 模板中填入虚构的经历或数据
- 不要将编译产物（.aux, .log, .fls 等）提交到 git

## Common Tasks

### 编译简历
```bash
cd resume/templates/<template-name>
xelatex zhang_junrui.tex
```

### 更新个人信息
修改对应模板目录下的 `zhang_junrui.tex`，同步更新所有模板中相同的个人信息。

### 查看项目代码
直接在 `projects/` 下阅读源码，无需安装（除非要运行实验）。

## Tech Stack

- **LaTeX**: XeLaTeX + ctex (中文模板)
- **Python**: 3.x + PyTorch (projects/ 下的模型代码)
- **Git**: SSH protocol (git@github.com:Zjrua/)
