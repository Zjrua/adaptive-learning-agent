import { useState } from 'react'
import { api } from './api'

interface Props {
  existingIds: string[]
  onClose: () => void
  onChanged: () => void
}

type Tab = 'direction' | 'node'

export function AiModal({ existingIds, onClose, onChanged }: Props) {
  const [tab, setTab] = useState<Tab>('direction')
  const [desc, setDesc] = useState('')
  const [nodeId, setNodeId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<any>(null)

  const run = async () => {
    if (!desc.trim()) return
    setBusy(true); setError(''); setResult(null)
    try {
      if (tab === 'direction') {
        const r = await api.generateDirection(desc, existingIds)
        setResult(r.data)
      } else {
        const r = await api.generateNode(desc, nodeId, existingIds)
        setResult(r.data)
      }
    } catch (e: any) { setError(String(e.message || e)) }
    setBusy(false)
  }

  const apply = async () => {
    if (!result) return
    setBusy(true)
    try {
      if (tab === 'direction') {
        await api.applyDirection(result)
      } else {
        // 节点：需要挂到某棵树。简化：若 result 是完整 node，提示需选方向——这里作为新独立方向写入
        await api.applyDirection({ tree_id: 'ai_node_' + Date.now(), title: result.name || 'AI 补充', icon: '✨', color: '#a78bfa', order: 99, subtitle: 'AI 生成', branches: [{ id: 'b', name: '补充', icon: '✨', nodes: [result] }] })
      }
      onChanged()
      onClose()
    } catch (e: any) { setError(String(e.message || e)) }
    setBusy(false)
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3 className="serif">✨ AI 生成</h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-tabs">
          <button className={`mtab ${tab === 'direction' ? 'active' : ''}`} onClick={() => { setTab('direction'); setResult(null) }}>新方向</button>
          <button className={`mtab ${tab === 'node' ? 'active' : ''}`} onClick={() => { setTab('node'); setResult(null) }}>补节点</button>
        </div>

        {tab === 'node' && (
          <>
            <label className="field-label">补充到节点 id（留空=新节点）</label>
            <input className="field" value={nodeId} onChange={e => setNodeId(e.target.value)} placeholder="如 deepfm（从列表选或手填）" list="nodelist" />
            <datalist id="nodelist">{existingIds.map(id => <option key={id} value={id} />)}</datalist>
          </>
        )}
        <label className="field-label">描述</label>
        <textarea className="field ta" value={desc} onChange={e => setDesc(e.target.value)} rows={5}
          placeholder={tab === 'direction' ? '如：数据分析方向，学 SQL、Python 数据处理、可视化、统计建模…' : '如：给 deepfm 补充手推 FM 公式、白板画结构的验收'} />

        <button className="btn primary" onClick={run} disabled={busy || !desc.trim()} style={{ marginTop: 12 }}>
          {busy ? '⏳ 生成中…' : '✨ 生成'}
        </button>

        {error && <div className="setup-error">⚠ {error}</div>}
        {result && (
          <div className="gen-preview">
            <h4 className="psec">✅ 预览</h4>
            <pre className="gen-json">{JSON.stringify(result, null, 2).slice(0, 600)}</pre>
            <button className="btn primary" onClick={apply} disabled={busy}>{busy ? '写入中…' : '确认写入 →'}</button>
          </div>
        )}
      </div>
    </div>
  )
}
