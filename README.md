# Internship Preparation

搜广推（搜索/广告/推荐系统）实习准备项目，包含简历模板和开源项目复现参考。

## 目录结构

```
├── resume/templates/     # LaTeX 简历模板（7套）
│   ├── sb2nov/           # 极简单栏，ATS友好
│   ├── jakegut/          # 现代单栏，硅谷风
│   ├── billryan/         # 中英混合，FontAwesome图标
│   ├── hijiangtao/       # 纯中文，BAT入职款
│   ├── luooofan/         # 纯中文，billryan改良版
│   ├── deedy/            # 双栏高密度
│   └── awesome-cv/       # 彩色精致，Font Awesome
├── projects/             # 搜广推开源项目（学习/复现参考）
│   ├── DeepCTR-Torch/    # CTR预估模型（DeepFM/DCN/xDeepFM等20+）
│   ├── DeepMatch/        # 召回模型（DSSM/YouTube DNN/MIND）
│   ├── FuxiCTR/          # 50+ CTR模型，学术级benchmark
│   ├── RecSystem-Pytorch/# 序列推荐（DIN/DIEN/SIM）
│   ├── OpenOneRec/       # 快手大模型+推荐（Qwen backbone）
│   ├── generative-recommenders/  # Meta生成式推荐（HSTU）
│   └── HLLM/             # 字节层次化LLM推荐
├── docs/                 # 学习笔记和文档
└── CLAUDE.md             # 项目说明（AI Agent 阅读）
```

## 模板对比

| 模板 | 风格 | 语言 | 适合场景 |
|------|------|------|----------|
| sb2nov | 极简单栏 | 英文 | ATS投递，外企 |
| jakegut | 现代单栏 | 英文 | 科技公司，硅谷风 |
| billryan | 中英混合 | 中英文 | 国内大厂 |
| hijiangtao | 纯中文 | 中文 | 国内互联网，栏目措辞成熟 |
| luooofan | 纯中文 | 中文 | 模块化结构，易维护 |
| deedy | 双栏高密度 | 英文 | 经历多，一页塞满 |
| awesome-cv | 彩色精致 | 英文 | 视觉美观 |

## 学习路线

### 方案A — CTR专精（面广告/搜索）
DeepCTR-Torch → FuxiCTR → 对比20+模型在Criteo上的AUC

### 方案B — 大模型+推荐（面最前沿岗）
OpenOneRec → generative-recommenders → HLLM

### 方案C — 全链路系统（面推荐系统岗）
DeepMatch（召回）→ RecSystem-Pytorch（序列精排）→ DeepCTR-Torch（CTR）

## 编译简历

```bash
cd resume/templates/<template-name>
xelatex zhang_junrui.tex   # 或 latexmk -xelatex zhang_junrui.tex
```

## 注意事项

- `hijiangtao` 和 `luooofan` 模板需单独安装字体包（已排除在仓库外），编译时如报字体缺失需从原项目 fonts/ 获取
- `deedy` 模板使用 OpenFonts，需根据本地字体路径调整
- 编译推荐使用 XeLaTeX（中文支持）

## 许可

各模板和项目遵循其原始开源许可证。
