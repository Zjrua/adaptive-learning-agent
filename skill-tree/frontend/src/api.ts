import type { Graph, Profile, Template, Fruit } from './types'

const BASE = ''   // 同源(开发走 vite proxy /api → :8000)

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(BASE + url)
  if (!r.ok) throw new Error(`${url}: ${r.status}`)
  return r.json()
}

export const api = {
  graph: () => getJson<Graph>('/api/graph'),
  profile: () => getJson<Profile>('/api/profile'),
  templates: () => getJson<Template[]>('/api/templates'),
  fruits: () => getJson<Fruit[]>('/api/fruits'),

  /** 勾选/取消任务，返回更新后的整张图 */
  patchTask(treeId: string, nodeId: string, taskId: string, done: boolean, isVerify: boolean): Promise<Graph> {
    return fetch(BASE + '/api/task', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tree_id: treeId, node_id: nodeId, task_id: taskId, done, is_verify: isVerify }),
    }).then(r => r.json())
  },
}
