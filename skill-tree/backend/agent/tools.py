"""agent/tools.py — 工具 JSON Schema 定义 + 分层注册表。"""
from __future__ import annotations

_OBJ = {"type": "object", "properties": {}}

# ── Executor 层工具 ──
TOOLS_EXECUTOR = [
    {"name": "get_progress", "description": "查看用户当前学习进度：整体掌握度、已点亮节点、卡住的节点。无参数。",
     "parameters": _OBJ},
    {"name": "get_node", "description": "读取某个节点的详情（任务、验收、依赖）。",
     "parameters": {"type": "object",
                    "properties": {"node_id": {"type": "string", "description": "节点 id"}},
                    "required": ["node_id"]}},
    {"name": "get_next", "description": "查询某节点学完后建议学的下一个节点（基于 depends_on 反向）。",
     "parameters": {"type": "object",
                    "properties": {"node_id": {"type": "string", "description": "当前节点 id"}},
                    "required": ["node_id"]}},
    {"name": "get_direction", "description": "查询某个学习方向（如 agent/recommendation/search/ads）的所有节点、各自掌握度和下一步建议。用户提到 $某方向 或问某方向学什么时用这个，不要用全局 get_progress。",
     "parameters": {"type": "object",
                    "properties": {"dir_id": {"type": "string", "description": "方向 id 或名称（如 agent/推荐）"}},
                    "required": ["dir_id"]}},
    {"name": "search_knowledge", "description": "在知识库（开源项目源码、论文、简历素材）中检索与查询相关的内容，返回带来源引用的片段。涉及客观知识时优先用这个，不要凭空编造。",
     "parameters": {"type": "object",
                    "properties": {"query": {"type": "string", "description": "检索关键词或问题"},
                                   "top_k": {"type": "integer", "description": "返回条数，默认5", "default": 5}},
                    "required": ["query"]}},
    {"name": "add_node", "description": "生成一个「新增节点」的建议（不直接写入，需用户确认）。返回建议内容供用户审核。",
     "parameters": {"type": "object",
                    "properties": {"description": {"type": "string", "description": "要新增的技能/节点描述"}},
                    "required": ["description"]}},
    {"name": "add_tasks", "description": "给已有节点补充学习任务/验收（生成建议，需用户确认）。",
     "parameters": {"type": "object",
                    "properties": {"node_id": {"type": "string"},
                                   "description": {"type": "string", "description": "想补充的任务描述"}},
                    "required": ["node_id", "description"]}},
    {"name": "toggle_task", "description": "勾选/取消勾选某个学习任务或验收（直接执行）。",
     "parameters": {"type": "object",
                    "properties": {"tree_id": {"type": "string"}, "node_id": {"type": "string"},
                                   "task_id": {"type": "string"}, "done": {"type": "boolean"}},
                    "required": ["tree_id", "node_id", "task_id", "done"]}},
]

# ── Writer 层工具 ──
TOOLS_WRITER = [
    {"name": "write_doc", "description": "把收集到的素材整理成飞书文档（学习笔记/复习卡/周报）。返回文档内容供发布。",
     "parameters": {"type": "object",
                    "properties": {"doc_type": {"type": "string", "description": "note|review|weekly",
                                                 "default": "note"},
                                   "topic": {"type": "string", "description": "文档主题"}},
                    "required": ["doc_type", "topic"]}},
]


def tool_schema_text(tools: list[dict]) -> str:
    """把工具列表序列化成指令式 prompt 文本。"""
    lines = []
    for t in tools:
        params = t.get("parameters", {}).get("properties", {})
        args = ", ".join(params.keys()) or "（无参数）"
        lines.append(f"- {t['name']}({args}): {t['description']}")
    return "\n".join(lines)
