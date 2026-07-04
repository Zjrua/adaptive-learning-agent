import type { Graph, Profile, Template, Fruit, AgentEvent, ChatHistory, ChatSession, SearchHit, Provider, LlmConfig, NodeSpec, Task } from './types'

// Tauri 打包后由 shell 注入端口(window.__SKILLTREE_PORT__);开发期空串走 vite proxy
const PORT = (typeof window !== 'undefined' && (window as any).__SKILLTREE_PORT__) || ''
export const BASE = PORT ? `http://127.0.0.1:${PORT}` : ''

export async function applyNode(treeId: string, node: NodeSpec, branchId?: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/ai/apply-node`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tree_id: treeId, node, branch_id: branchId }),
  })
  return res.json()
}

export async function applyTasks(treeId: string, nodeId: string, tasks: Task[]): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/ai/apply-tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tree_id: treeId, node_id: nodeId, tasks }),
  })
  return res.json()
}

// ── 飞书知识库归档配置 ──
export async function listWikiSpaces(): Promise<{ ok: boolean; spaces: { space_id: string; name: string }[]; error?: string }> {
  const res = await fetch(`${BASE}/api/lark/spaces`)
  return res.json()
}

export async function setWikiSpace(spaceId: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/lark/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ wiki_space_id: spaceId }),
  })
  return res.json()
}

export async function getLarkConfig(): Promise<{ wiki_space_id: string | null }> {
  const res = await fetch(`${BASE}/api/lark/config`)
  return res.json()
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(BASE + url)
  if (!r.ok) throw new Error(`${url}: ${r.status} ${await r.text().catch(() => '')}`)
  return r.json()
}

async function postJson<T>(url: string, body: any): Promise<T> {
  const r = await fetch(BASE + url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const text = await r.text()
  if (!r.ok) throw new Error(`${url}: ${r.status} ${text}`)
  return text ? JSON.parse(text) : ({} as T)
}

// Provider/LlmConfig 类型已移至 types.ts（api.ts 内部从上方 import type 引用）

export const api = {
  graph: () => getJson<Graph>('/api/graph'),
  profile: () => getJson<Profile>('/api/profile'),
  templates: () => getJson<Template[]>('/api/templates'),
  fruits: () => getJson<Fruit[]>('/api/fruits'),

  patchTask(treeId: string, nodeId: string, taskId: string, done: boolean, isVerify: boolean): Promise<Graph> {
    return fetch(BASE + '/api/task', {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tree_id: treeId, node_id: nodeId, task_id: taskId, done, is_verify: isVerify }),
    }).then(r => r.json())
  },

  // ── LLM 配置 ──
  providers: () => getJson<Provider[]>('/api/providers'),
  getLlmConfig: () => getJson<LlmConfig>('/api/llm-config'),
  saveLlmConfig: (cfg: LlmConfig) =>
    fetch(BASE + '/api/llm-config', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg),
    }).then(r => r.json()),
  testLlmConfig: (cfg: LlmConfig) => postJson<{ ok: boolean; message: string }>('/api/llm-config/test', cfg),
  listModels: (cfg: LlmConfig) => postJson<{ ok: boolean; models: string[]; error?: string }>('/api/llm-config/models', cfg),

  // ── AI 生成 ──
  generateTree: (jd: string, extra: string) =>
    postJson<{ ok: boolean; data: { trees: any[]; profile: any } }>('/api/ai/generate-tree', { jd, extra }),
  generateDirection: (description: string, existingIds: string[]) =>
    postJson<{ ok: boolean; data: any }>('/api/ai/generate-direction', { description, existing_ids: existingIds }),
  generateNode: (description: string, nodeId: string, existingIds: string[]) =>
    postJson<{ ok: boolean; data: any }>('/api/ai/generate-node', { description, node_id: nodeId, existing_ids: existingIds }),
  applyTree: (trees: any[], profile: any) => postJson('/api/ai/apply-tree', { trees, profile }),
  applyDirection: (tree: any) => postJson('/api/ai/apply-direction', { tree }),

  // ── Agent 对话(SSE 流式,支持 AbortController 停止) ──
  agentChatStream(
    message: string,
    history: { role: 'user' | 'assistant'; content: string }[],
    onEvent: (ev: AgentEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    return fetch(BASE + '/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history }),
      signal,
    }).then(async (r) => {
      if (!r.ok) throw new Error(await r.text().catch(() => ''))
      const reader = r.body?.getReader()
      if (!reader) throw new Error('流式响应不可用(浏览器不支持或后端未正确返回 SSE)')
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() || ''
        for (const part of parts) {
          const line = part.trim()
          if (line.startsWith('data: ')) {
            try { onEvent(JSON.parse(line.slice(6)) as AgentEvent) } catch { /* ignore malformed */ }
          }
        }
      }
    })
  },

  publishDoc: (content: string, title: string) =>
    postJson<{ ok: boolean; url: string }>('/api/agent/publish-doc', { content, title }),

  buildIndex: () => postJson<{ ok: boolean; stats: unknown }>('/api/rag/build-index', {}),
  ragStatus: () => getJson<{ count: number; built_at: string; model: string }>('/api/rag/status'),

  // ── Chat 多会话管理 ──
  chatHistory: () => getJson<ChatHistory>('/api/chat/history'),
  chatSync: (sessions: ChatSession[], currentSessionId: string | null) =>
    postJson<{ ok: boolean }>('/api/chat/sync', { sessions, current_session_id: currentSessionId }),
  chatTitle: (message: string) =>
    postJson<{ title: string }>('/api/chat/title', { message }),
  chatSearch: (q: string) => getJson<{ hits: SearchHit[] }>(`/api/chat/search?q=${encodeURIComponent(q)}`),
  chatExport: (sessionId: string | null) =>
    getJson<unknown>(`/api/chat/export${sessionId ? `?session_id=${sessionId}` : ''}`),
  chatResolve: (refs: string) => getJson<{ resolved: { type: string; id: string; name: string; content: string }[] }>(`/api/chat/resolve?refs=${encodeURIComponent(refs)}`),
  chatSuggest: (type: string, q: string) =>
    getJson<{ items: { id: string; name: string }[] }>(`/api/chat/suggest?type=${type}&q=${encodeURIComponent(q)}`),
}
