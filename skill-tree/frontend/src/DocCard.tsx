import { useState } from 'react'
import { api } from './api'

export function DocCard({ content, onPublished }: { content: string; onPublished: (url: string) => void }) {
  const [busy, setBusy] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [err, setErr] = useState('')

  const publish = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.publishDoc(content, '学习笔记')
      onPublished(r.url)
    } catch (e: any) { setErr(String(e.message || e)) }
    setBusy(false)
  }

  return (
    <div className="doc-card">
      <div className="doc-card-head">📄 学习文档已生成</div>
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
