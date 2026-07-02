"""ai.py — 大模型驱动的技能树生成引擎。

OpenAI 兼容客户端，5 个预置供应商通吃。三级生成：树 / 方向 / 节点。
健壮性：JSON 解析失败自动重试 + schema 校验 + id 去重/依赖修正。
"""
from __future__ import annotations
import json
import re
import urllib.request
import urllib.error
from typing import Any

# ─────────────────────────── 供应商预置 ───────────────────────────
PROVIDER_PRESETS = [
    {"id": "deepseek", "label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "json_mode": True},
    {"id": "mimo", "label": "小米 MiMo", "base_url": "https://api.xiaomimimo.com/v1", "model": "mimo-v2.5-pro", "json_mode": True},
    {"id": "zhipu", "label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4.6", "json_mode": True},
    {"id": "qwen", "label": "通义 Qwen", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus", "json_mode": True},
    {"id": "moonshot", "label": "Moonshot Kimi", "base_url": "https://api.moonshot.ai/v1", "model": "moonshot-v1-8k", "json_mode": False},
    {"id": "custom", "label": "自定义 (OpenAI 兼容)", "base_url": "", "model": "", "json_mode": True},
]

# ─────────────────────────── HTTP 调用（零依赖，标准库 urllib）───────────────────────────
def _chat(cfg: dict, system: str, user: str, json_mode: bool, retry_prompt: str = "") -> str:
    """调 OpenAI 兼容 /chat/completions，返回助手消息文本。"""
    base = cfg["base_url"].rstrip("/")
    url = f"{base}/chat/completions"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": (retry_prompt + "\n" + user) if retry_prompt else user},
    ]
    body: dict[str, Any] = {
        "model": cfg.get("model") or "gpt-3.5-turbo",
        "messages": messages,
        "temperature": 0.7,
    }
    if json_mode and cfg.get("json_mode", True):
        body["response_format"] = {"type": "json_object"}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {cfg['api_key']}")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"LLM HTTP {e.code}: {detail}")
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {e}")


def test_connection(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    """发一条 hello 测连通。"""
    if not base_url or not api_key:
        return False, "base_url 或 api_key 为空"
    try:
        reply = _chat({"base_url": base_url, "api_key": api_key, "model": model, "json_mode": False},
                      "You are a test echo. Reply briefly.", "说「连通成功」四个字。", json_mode=False)
        return True, reply[:80]
    except Exception as e:
        return False, str(e)


def list_models(base_url: str, api_key: str) -> list[str]:
    """调 OpenAI 兼容 /models 端点，返回模型 id 列表。所有预置供应商都支持。"""
    if not base_url or not api_key:
        return []
    base = base_url.rstrip("/")
    # 兼容：base_url 可能带或不带 /v1，统一指向 /models
    url = f"{base}/models"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # OpenAI 格式：{data: [{id: "model-name", ...}, ...]}
        items = data.get("data", data) if isinstance(data, dict) else data
        ids = [m.get("id", "") for m in items if isinstance(m, dict) and m.get("id")]
        return sorted(ids)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"HTTP {e.code}: {detail}")
    except Exception as e:
        raise RuntimeError(f"获取模型列表失败: {e}")


# ─────────────────────────── JSON 提取与校验 ───────────────────────────
def _extract_json(text: str) -> Any:
    """从模型输出里提取 JSON（容忍前后说明文字 + ```代码块）。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # 直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # 找第一个 { 到最后一个 } 之间
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # 找数组
    m = re.search(r"\[.*\]", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    raise ValueError("无法从模型输出解析出 JSON")


def _call_json(cfg: dict, system: str, user: str) -> Any:
    """调 LLM 并返回解析后的 JSON，失败自动重试一次。"""
    text = _chat(cfg, system, user, json_mode=True)
    try:
        return _extract_json(text)
    except ValueError:
        # 重试：提示上次格式错误
        text2 = _chat(cfg, system, user, json_mode=True,
                      retry_prompt="【注意】上一次返回的不是合法 JSON，请只返回一个 JSON 对象，不要任何额外文字。")
        return _extract_json(text2)


# ─────────────────────────── schema 规范化 ───────────────────────────
def _norm_task(t: Any) -> dict:
    if not isinstance(t, dict):
        return {"id": "t", "title": str(t), "done": False}
    out = {"id": str(t.get("id", "t")), "title": str(t.get("title", "")), "done": bool(t.get("done", False))}
    if t.get("resource"):
        out["resource"] = t["resource"]
    if t.get("verify"):
        out["verify"] = [_norm_task(v) for v in t["verify"]]
    return out


def _norm_node(n: Any) -> dict:
    if not isinstance(n, dict):
        return {"id": str(n), "name": str(n), "tasks": []}
    out = {
        "id": str(n.get("id", n.get("name", "node"))),
        "name": str(n.get("name", n.get("id", ""))),
        "category": str(n.get("category", "")),
        "status": n.get("status", "locked"),
        "depends_on": list(n.get("depends_on", [])),
        "tasks": [_norm_task(t) for t in n.get("tasks", [])],
    }
    if n.get("verify"):
        out["verify"] = [_norm_task(v) for v in n["verify"]]
    return out


def slugify_id(name: str) -> str:
    """把名字转成合法 node id(小写字母数字下划线)。如 'Light GCN!' → 'light_gcn'。"""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "node"


def validate_node(node: dict) -> tuple[bool, list[str]]:
    """轻量校验。返回 (ok, [错误信息])。必填:id(非空)、name(非空)、tasks(list)。"""
    errs = []
    if not isinstance(node, dict):
        return False, ["node 不是对象"]
    if not str(node.get("id", "")).strip():
        errs.append("缺少 id")
    if not str(node.get("name", "")).strip():
        errs.append("缺少 name")
    if not isinstance(node.get("tasks", None), list):
        errs.append("tasks 必须是列表")
    return (len(errs) == 0), errs


def _norm_tree(t: Any, fallback_id: str = "gen") -> dict:
    if not isinstance(t, dict):
        return {"tree_id": fallback_id, "title": str(t), "branches": []}
    branches = []
    for b in t.get("branches", []):
        if isinstance(b, dict):
            branches.append({
                "id": str(b.get("id", b.get("name", "branch"))),
                "name": str(b.get("name", b.get("id", ""))),
                "icon": b.get("icon", "•"),
                "description": str(b.get("description", "")),
                "nodes": [_norm_node(n) for n in b.get("nodes", [])],
            })
    return {
        "tree_id": str(t.get("tree_id", t.get("id", fallback_id))),
        "order": t.get("order", 99),
        "title": str(t.get("title", t.get("tree_id", "新方向"))),
        "subtitle": str(t.get("subtitle", "")),
        "icon": t.get("icon", "🌳"),
        "color": t.get("color", "#4ade80"),
        "branches": branches,
    }


# ─────────────────────────── 提示词 ───────────────────────────
_SYS = """你是一个资深的实习求职导师 + 技术学习路径规划专家。
你的任务：根据用户的求职方向/JD，生成结构化的「技能树」学习路径，输出严格的 JSON。

技能树 JSON 结构（必须严格遵守）：
{
  "trees": [   // 一个或多个方向
    {
      "tree_id": "英文短id", "order": 1, "title": "方向名", "subtitle": "一句话",
      "icon": "emoji", "color": "#hex",
      "branches": [
        { "id": "英文短id", "name": "分支名", "icon": "emoji", "description": "说明",
          "nodes": [
            { "id": "唯一英文短id", "name": "技能名", "category": "类别",
              "status": "locked",
              "depends_on": ["前置node的id"],
              "tasks": [
                { "id": "任务id", "title": "具体可执行的学习任务",
                  "verify": [ {"id":"v1","title":"能默写/讲清/手算...的验收标准"} ] }
              ]
            }
          ]
        }
      ]
    }
  ],
  "profile": { "name":"用户名(若JD有)", "tagline":"一句话定位", "contact":{}, "education":[], "skills":[{group,items}], "experience":[], "awards":[] }
}

关键原则：
1. 任务要具体可执行(读某论文/跑通某demo/读某源码文件)，不要空泛
2. 有验收价值的任务配 verify(能默写代码/能讲清原理/能白板画图/能手算)
3. depends_on 形成清晰的前后依赖路径，基础在前
4. 跨方向共享的基础(如 Python/PyTorch)用相同 id，便于去重合并
5. 只返回 JSON 对象，不要任何 markdown 代码块标记或额外说明文字"""


_SYS_DIRECTION = """你是技术学习路径规划专家。根据描述生成【单个方向】的技能树 JSON。
结构与原则同整树，但只输出一个 tree 对象：{tree_id, order, title, subtitle, icon, color, branches:[...]}。
现有的节点 id（可在 depends_on 中引用这些作为基础/前置）：{existing}。只返回 JSON。"""


_SYS_NODE = """你是技术学习规划专家。为指定技能生成【知识点(学习任务)】，输出 JSON。
若是补充已有节点，输出该节点新的 tasks/verify；若是新节点，输出完整 node 对象。
格式：{id, name, category, status, depends_on:[...], tasks:[{id,title,verify:[{id,title}]}]}
现有节点 id（depends_on 可引用）：{existing}。任务要具体，验收要可检验。只返回 JSON。"""


# ─────────────────────────── 三级生成 ───────────────────────────
def generate_tree(cfg: dict, jd: str, extra: str = "") -> dict:
    user = f"目标岗位 / JD：\n{jd}\n"
    if extra:
        user += f"\n补充说明：\n{extra}\n"
    user += "\n请生成完整的技能树（含 trees 和 profile）。"
    data = _call_json(cfg, _SYS, user)
    trees = [_norm_tree(t, f"gen{i}") for i, t in enumerate(data.get("trees", []))]
    profile = data.get("profile", {}) if isinstance(data.get("profile"), dict) else {}
    return {"trees": trees, "profile": profile}


def generate_direction(cfg: dict, description: str, existing_ids: list[str]) -> dict:
    sys2 = _SYS_DIRECTION.replace("{existing}", ", ".join(existing_ids) or "(无)")
    data = _call_json(cfg, sys2, f"方向描述：\n{description}\n\n请生成这个方向的技能树。")
    return _norm_tree(data, "gen_dir")


def generate_node(cfg: dict, description: str, node_id: str, existing_ids: list[str]) -> dict:
    sys2 = _SYS_NODE.replace("{existing}", ", ".join(existing_ids) or "(无)")
    prompt = f"描述：\n{description}\n"
    if node_id:
        prompt += f"\n这是为已有节点「{node_id}」补充知识点/验收。输出含 id={node_id} 的 node 对象。"
    else:
        prompt += "\n请生成一个新技能节点。"
    data = _call_json(cfg, sys2, prompt)
    return _norm_node(data)
