# CLAUDE.md — skill-tree/frontend（React + TypeScript + Vite）

单页应用，玉青宝石工坊美学。无路由库/状态库，全手写 hash 路由 + useState。

## 文件结构

```
src/
├── main.tsx          入口，挂载 App，引入 index.css + tree.css
├── App.tsx           侧栏 SPA + hash 路由 + 全局状态(graph/profile/templates/fruits) + 悬浮AI按钮
├── api.ts            fetch 封装 + 所有 API 方法 + X-User-Id 头 + getUserId/setUserId
├── types.ts          TS 类型(Graph/Node/Task/Profile/Template/Fruit/Achievement)
├── SkillTree.tsx     DAG 画布：useMemo(layout) + 节点+SVG连线 + 展开避让 + 悬停路径高亮
├── NodeCard.tsx      节点卡片 + 知识点/验收(清单语义) + forwardRef
├── AiModal.tsx       右下角悬浮对话面板(新方向/补节点)
├── Achievement.tsx   成就花田
├── panels/
│   ├── SetupPanel.tsx     设置/初始化(用户选择→模型配置→AI生成树)
│   ├── ProfilePanel.tsx   个人信息
│   ├── TemplatesPanel.tsx 简历模板
│   └── FruitPanel.tsx     果实展示
├── index.css         全局样式(玉青调色板 + 玻璃质感 + 按钮/表单/侧栏/仪表盘/设置/AI对话框)
└── tree.css          DAG 专属样式(节点/连线/详情/知识点/验收)
```

## 路由

hash 路由，无库。`type Route = 'tree'|'profile'|'templates'|'fruit'|'setup'|'settings'`
- `currentRoute()` 读 `location.hash`，`go(r)` 设 hash，`hashchange` 事件驱动
- 加路由：扩展 Route 联合 + ROUTES 数组 + 侧栏 nav + main 渲染分支
- 新用户(is_new_user)自动跳 `#setup`；老用户手动从侧栏底部「⚙️设置」进

## 全局状态（App.tsx）

- `graph`/`profile`/`templates`/`fruits` 四个 useState
- `refreshGraph` (useCallback)：拉 /api/graph，勾选/用户切换后调用
- `onUserChanged`：清缓存 + reloadKey++ 触发重拉
- 懒加载：profile/templates/fruits 首次进对应路由才拉
- 全部 props 下传，无 Context/Redux

## 数据流（状态驱动，解决历史 bug 的核心）

- 勾选 → `api.patchTask` → 后端写盘返回新 Graph → `setGraph` → React 重渲染
- 节点位置和 SVG 连线**同源于 `useMemo(layout)`** → 展开/勾选同步，永不错位
- 展开避让：`ResizeObserver` 监听 openNode 实际高度 → 算 push → 下方节点下推 + 连线跟随（rAF 每帧重画）

## api.ts

- `getJson/postJson` 封装，所有请求带 `X-User-Id` 头（getUserId 从 localStorage 读）
- 方法：graph/profile/templates/fruits/patchTask/users/createUser/providers/getLlmConfig/saveLlmConfig/testLlmConfig/listModels/generateTree/generateDirection/generateNode/applyTree/applyDirection

## 关键组件

### SkillTree.tsx（DAG 画布，最复杂）
- `pathSet` useMemo：悬停节点→上下游祖先后代；悬停方向标签→该方向节点+直接前置
- `drawEdges`：rAF 循环每帧从节点 getBoundingClientRect 实时重算 path（跟随过渡动画）
- 展开避让：useLayoutEffect + ResizeObserver 实测详情高度 → push → placed 重算
- 常量 NODE_W/NODE_H 等必须与 backend/layout.py 一致

### NodeCard.tsx
- forwardRef（SkillTree 用 ref 量高度）
- 知识点：有验收→勾选框 disabled(清单)；验收勾完=掌握
- `.detail onClick stopPropagation`：点详情不触发卡片折叠

### AiModal.tsx
- 右下角悬浮，从圆点 scale 展开成对话面板
- 标签：🌿新方向 / 🔬补节点

### SetupPanel.tsx
- 三步：选/建用户 → 配模型(供应商预设+URL+Key+获取模型列表combobox+测连通) → 贴JD生成树→预览确认
- 模型字段：input + datalist（combobox，可列表选也可手输）

## 设计系统（index.css）

- 调色板：`--jade #5eead4`(主) / `--bud #fbbf24`(学习中) / 暖墨底 + 噪点
- 玻璃质感：`backdrop-filter: blur` 用于卡片/节点/chip
- 字体：Fraunces(衬线标题) + Manrope(正文) + JetBrains Mono(细节)
- 玉青统一：进度环/按钮/连线/聚焦光晕/激活态

## 开发约定

- 改 API：api.ts 加方法 + types.ts 加类型 + 后端 main.py 加端点
- 改 DAG 布局常量：必须同步 backend/layout.py
- 改样式：全局在 index.css，DAG 专属在 tree.css
- 构建验证：`npm run build`（tsc 类型检查 + vite 打包）
