import { useState } from 'react'
import { api } from './api'

const DOC_TYPE_ICON: Record<string, string> = { note: '📝', review: '🃏', weekly: '📊' }
const DOC_TYPE_LABEL: Record<string, string> = { note: '学习笔记', review: '复习卡', weekly: '周报' }

export function DocCard({ content, docType, title, onPublished }: {
  content: string
  docType?: string
  title?: string
  onPublished: (url: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [err, setErr] = useState('')

  const dt = docType || 'note'
  const icon = DOC_TYPE_ICON[dt] || '📄'
  const label = title || DOC_TYPE_LABEL[dt] || '文档'

  const publish = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.publishDoc(content, DOC_TYPE_LABEL[dt] || '学习笔记')
      onPublished(r.url)
    } catch (e: any) { setErr(String(e.message || e)) }
    setBusy(false)
  }

  return (
    <div className="doc-card">
      <div className="doc-card-head">{icon} {label}</div>
      {showPreview && <pre className="doc-preview">{content.slice(0, 800)}</pre>}
      <div className="doc-card-actions">
        <button className="aibtn ghost" onClick={() => setShowPreview(v => !v)}>
          {showPreview ? '收起' : '预览'}
        </button>
        <button className="aibtn solid" onClick={publish} disabled={busy}>
          {busy ? '发布中…' : '写飞书'}
        </button>
      </div>
      {err && <div className="ai-err">⚠ {err}</div>}
    </div>
  )
}
