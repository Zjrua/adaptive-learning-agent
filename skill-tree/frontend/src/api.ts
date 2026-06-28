import type { Graph, Profile, Template, Fruit } from './types'

const BASE = ''   // 同源(开发走 vite proxy /api → :8000)

const USER_KEY = 'skilltree_user_id'
export const getUserId = () => localStorage.getItem(USER_KEY) || 'default'
export const setUserId = (id: string) => localStorage.setItem(USER_KEY, id)

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

export interface Provider { id: string; label: string; base_url: string; model: string; json_mode: boolean }
export interface LlmConfig { provider: string; base_url: string; api_key: string; model: string; configured?: boolean }
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
}
