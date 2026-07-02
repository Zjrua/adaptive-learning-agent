import type { Graph, Profile, Template, Fruit, AgentEvent, ChatHistory, ChatSession, SearchHit, Provider, LlmConfig, NodeSpec, Task } from './types'

const BASE = ''   // 同源(开发走 vite proxy /api → :8000)

export async function applyNode(treeId: string, node: NodeSpec, branchId?: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/ai/apply-node`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-User-Id': getUserId() },
    body: JSON.stringify({ tree_id: treeId, node, branch_id: branchId }),
  })
  return res.json()
}

export async function applyTasks(treeId: string, nodeId: string, tasks: Task[]): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/ai/apply-tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-User-Id': getUserId() },
    body: JSON.stringify({ tree_id: treeId, node_id: nodeId, tasks }),
  })
  return res.json()
}

const USER_KEY = 'skilltree_user_id'
export const getUserId = () => localStorage.getItem(USER_KEY) || 'default'
export const setUserId = (id: string) => localStorage.setItem(USER_KEY, id)

// ── 飞书知识库归档配置 ──
export async function listWikiSpaces(): Promise<{ ok: boolean; spaces: { space_id: string; name: string }[]; error?: string }> {
  const res = await fetch(`${BASE}/api/lark/spaces`, { headers: { 'X-User-Id': getUserId() } })
  return res.json()
}

export async function setWikiSpace(spaceId: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/lark/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-User-Id': getUserId() },
    body: JSON.stringify({ wiki_space_id: spaceId }),
  })
  return res.json()
}

export async function getLarkConfig(): Promise<{ wiki_space_id: string | null }> {
  const res = await fetch(`${BASE}/api/lark/config`, { headers: { 'X-User-Id': getUserId() } })
  return res.json()
}

/** 带 X-User-Id 头的 fetch */
function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return { 'X-User-Id': getUserId(), ...extra }
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(BASE + url, { headers: authHeaders() })
  if (!r.ok) throw new Error(`${url}: ${r.status} ${await r.text().catch(() => '')}`)
  return r.json()
}

async function postJson<T>(url: string, body: any): Promise<T> {
  const r = await fetch(BASE + url, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  const text = await r.text()
  if (!r.ok) throw new Error(`${url}: ${r.status} ${text}`)
  return text ? JSON.parse(text) : ({} as T)
}

// Provider/LlmConfig 类型已移至 types.ts（api.ts 内部从上方 import type 引用）
export interface UserInfo { id: string; name: string }

export const api = {
  graph: () => getJson<Graph>('/api/graph'),
  profile: () => getJson<Profile>('/api/profile'),
  templates: () => getJson<Template[]>('/api/templates'),
  fruits: () => getJson<Fruit[]>('/api/fruits'),

  patchTask(treeId: string, nodeId: string, taskId: string, done: boolean, isVerify: boolean): Promise<Graph> {
    return fetch(BASE + '/api/task', {
      method: 'PATCH', headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ tree_id: treeId, node_id: nodeId, task_id: taskId, done, is_verify: isVerify }),
    }).then(r => r.json())
  },

  // ── 用户管理 ──
  users: () => getJson<UserInfo[]>('/api/users'),
  createUser: (userId: string) => postJson<UserInfo>('/api/users', { user_id: userId }),

  // ── LLM 配置 ──
  providers: () => getJson<Provider[]>('/api/providers'),
  getLlmConfig: () => getJson<LlmConfig>('/api/llm-config'),
  saveLlmConfig: (cfg: LlmConfig) =>
    fetch(BASE + '/api/llm-config', {
      method: 'PUT', headers: authHeaders({ 'Content-Type': 'application/json' }),
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

  // ── Agent 对话(SSE 流式) ──
  agentChatStream(
    message: string,
    history: { role: 'user' | 'assistant'; content: string }[],
    onEvent: (ev: AgentEvent) => void,
  ): Promise<void> {
    return fetch(BASE + '/api/agent/chat', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ message, history }),
    }).then(async (r) => {
      if (!r.ok) throw new Error(await r.text().catch(() => ''))
      const reader = r.body?.getReader()
      if (!reader) return
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
