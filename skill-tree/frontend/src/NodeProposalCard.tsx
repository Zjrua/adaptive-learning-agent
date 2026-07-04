import { useState, useEffect } from 'react'
import type { NodeSpec, Task, DirOrder } from './types'
import { applyNode, applyTasks, api } from './api'

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
  const [draftErr, setDraftErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [dirs, setDirs] = useState<DirOrder[]>([])
  const [treeId, setTreeId] = useState('')

  // 拉一次方向列表供选择(只在有 proposal 卡片时调一次)
  useEffect(() => {
    api.graph().then(g => { setDirs(g.dir_order); if (g.dir_order[0]) setTreeId(g.dir_order[0].id) }).catch(() => {})
  }, [])

  const apply = async () => {
    if (!treeId) { setMsg('请先选择方向'); return }
    setBusy(true); setMsg(''); setDraftErr('')
    try {
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
      // 区分 JSON 解析错(编辑态)和其他错
      if (e instanceof SyntaxError) {
        setDraftErr('JSON 格式错误: ' + e.message)
      } else {
        setMsg('✗ ' + String(e.message || e))
      }
    } finally {
      setBusy(false)
    }
  }

  const title = mode === 'new_node' ? `新节点《${node?.name || '?'}》` : `补充任务 → ${nodeId}`
  const count = mode === 'new_node' ? (node?.tasks.length ?? 0) : (tasks?.length ?? 0)

  return (
    <div className="doc-card node-proposal">
      <div className="np-title">🆕 {title}</div>
      <div className="np-sub">
        含 {count} 项{incomplete ? ' · ⚠ 校验不完整,建议编辑' : ''}
      </div>
      {editing && (
        <>
          <textarea value={draft} onChange={e => { setDraft(e.target.value); setDraftErr('') }} rows={8}
                    className="np-textarea" />
          {draftErr && <div className="np-err">{draftErr}</div>}
        </>
      )}
      <div className="np-row">
        <select className="np-select" value={treeId} onChange={e => setTreeId(e.target.value)} disabled={busy}>
          <option value="" disabled>选择方向…</option>
          {dirs.map(d => <option key={d.id} value={d.id}>{d.icon} {d.title}</option>)}
        </select>
        <button onClick={apply} disabled={busy} className="aibtn solid">{busy ? '应用中…' : '应用'}</button>
        <button onClick={() => setEditing(v => !v)} className="aibtn ghost">{editing ? '完成' : '编辑'}</button>
        <button onClick={onDiscard} className="aibtn ghost">丢弃</button>
      </div>
      {msg && <div className="np-msg">{msg}</div>}
    </div>
  )
}
