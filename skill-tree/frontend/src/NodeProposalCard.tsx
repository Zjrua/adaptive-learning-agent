import { useState } from 'react'
import type { NodeSpec, Task } from './types'
import { applyNode, applyTasks } from './api'

interface Props {
  mode: 'new_node' | 'add_tasks'
  node?: NodeSpec
  nodeId?: string
  tasks?: Task[]
  incomplete?: boolean
  onApplied?: () => void
  onDiscard?: () => void
}

export function NodeProposalCard({ mode, node, nodeId, tasks, incomplete, onApplied, onDiscard }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<string>(JSON.stringify(mode === 'new_node' ? node : tasks, null, 2))
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const apply = async () => {
    setBusy(true); setMsg('')
    try {
      const treeId = prompt('写入哪个方向(tree_id)?例如 agent / recommendation') || ''
      if (!treeId) { setMsg('已取消'); setBusy(false); return }
      if (mode === 'new_node' && node) {
        const n = editing ? JSON.parse(draft) : node
        await applyNode(treeId, n)
      } else if (mode === 'add_tasks' && nodeId) {
        const ts = editing ? JSON.parse(draft) : tasks
        await applyTasks(treeId, nodeId, ts || [])
      }
      setMsg('✓ 已应用,图谱已更新')
      onApplied?.()
    } catch (e: any) {
      setMsg('✗ ' + String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  const title = mode === 'new_node' ? `新节点《${node?.name || '?'}》` : `补充任务 → ${nodeId}`
  const count = mode === 'new_node' ? (node?.tasks.length ?? 0) : (tasks?.length ?? 0)

  return (
    <div className="doc-card" style={{ margin: '8px 0', border: '1px solid #38bdf8', borderRadius: 8, padding: 10 }}>
      <div style={{ fontWeight: 600 }}>🆕 {title}</div>
      <div style={{ fontSize: 13, color: '#94a3b8' }}>
        含 {count} 项{incomplete ? ' · ⚠ 校验不完整,建议编辑' : ''}
      </div>
      {editing && (
        <textarea value={draft} onChange={e => setDraft(e.target.value)} rows={8}
                  style={{ width: '100%', marginTop: 6, fontFamily: 'monospace', fontSize: 12 }} />
      )}
      <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
        <button onClick={apply} disabled={busy} className="btn-primary">{busy ? '应用中…' : '应用'}</button>
        <button onClick={() => setEditing(v => !v)}>{editing ? '完成编辑' : '编辑'}</button>
        <button onClick={onDiscard}>丢弃</button>
      </div>
      {msg && <div style={{ fontSize: 12, marginTop: 6 }}>{msg}</div>}
    </div>
  )
}
