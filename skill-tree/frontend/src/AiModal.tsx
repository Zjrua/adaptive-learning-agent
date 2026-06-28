import { useState } from 'react'
import { api } from './api'

interface Props {
  existingIds: string[]
  onClose: () => void
  onChanged: () => void
}

type Tab = 'direction' | 'node'

/**
 * 右下角悬浮的 AI 对话框。点击图标从圆点展开成对话面板。
 */
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
        await api.applyDirection({ tree_id: 'ai_node_' + Date.now(), title: result.name || 'AI 补充', icon: '✨', color: '#5eead4', order: 99, subtitle: 'AI 生成', branches: [{ id: 'b', name: '补充', icon: '✨', nodes: [result] }] })
      }
      onChanged()
      onClose()
    } catch (e: any) { setError(String(e.message || e)) }
    setBusy(false)
  }

  return (
    <div className="ai-fab-wrap">
      {/* 遮罩（点击外部关闭） */}
      <div className="ai-fab-mask" onClick={onClose} />
      {/* 对话面板：从右下角展开 */}
      <div className="ai-chat" role="dialog" aria-label="AI 生成">
        <div className="ai-chat-head">
          <div className="ai-chat-title">
            <span className="ai-orb">✦</span>
            <div>
              <div className="ai-name">AI 技能规划</div>
              <div className="ai-sub">描述需求，自动生成学习路径</div>
            </div>
          </div>
          <button className="ai-close" onClick={onClose} aria-label="关闭">✕</button>
        </div>

        <div className="ai-chat-tabs">
          <button className={`aitab ${tab === 'direction' ? 'active' : ''}`} onClick={() => { setTab('direction'); setResult(null) }}>🌿 新方向</button>
          <button className={`aitab ${tab === 'node' ? 'active' : ''}`} onClick={() => { setTab('node'); setResult(null) }}>🔬 补节点</button>
        </div>

        <div className="ai-chat-body">
          {tab === 'node' && (
            <div className="ai-field-row">
              <input className="ai-input" value={nodeId} onChange={e => setNodeId(e.target.value)} placeholder="补充到哪个节点 id？（留空=新节点）" list="nodelist" />
              <datalist id="nodelist">{existingIds.map(id => <option key={id} value={id} />)}</datalist>
            </div>
          )}

          <textarea
            className="ai-textarea"
            value={desc}
            onChange={e => setDesc(e.target.value)}
            rows={4}
            placeholder={tab === 'direction'
              ? '如：数据分析方向，学 SQL、Python 数据处理、可视化、统计建模…'
              : '如：给 deepfm 补充手推 FM 公式、白板画结构的验收'}
          />

          {error && <div className="ai-err">⚠ {error}</div>}

          {result ? (
            <div className="ai-result">
              <div className="ai-result-head">✅ 已生成 · 预览</div>
              <pre className="ai-result-json">{JSON.stringify(result, null, 2).slice(0, 500)}</pre>
              <div className="ai-result-actions">
                <button className="aibtn ghost" onClick={() => setResult(null)}>重新生成</button>
                <button className="aibtn solid" onClick={apply} disabled={busy}>{busy ? '写入中…' : '确认写入'}</button>
              </div>
            </div>
          ) : (
            <button className="aibtn solid block" onClick={run} disabled={busy || !desc.trim()}>
              {busy ? '⏳ 生成中…' : '✦ 生成'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
