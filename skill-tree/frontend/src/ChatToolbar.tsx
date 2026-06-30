import { useState } from 'react'
import type { ChatSession, SearchHit } from './types'
import { api } from './api'

interface Props {
  sessions: ChatSession[]
  currentId: string | null
  collapsed: boolean
  onToggleCollapse: () => void
  onSelectSession: (id: string) => void
  onNewSession: () => void
  onDeleteSession: (id: string) => void
  onJumpToMessage: (sessionId: string, msgIndex: number) => void
}

export function ChatToolbar(props: Props) {
  const [showSessions, setShowSessions] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [hits, setHits] = useState<SearchHit[]>([])
  const [confirmDel, setConfirmDel] = useState<string | null>(null)

  const current = props.sessions.find(s => s.id === props.currentId)
  const doSearch = async () => {
    if (!searchQ.trim()) return
    const r = await api.chatSearch(searchQ)
    setHits(r.hits)
  }

  const doExport = async () => {
    const data = await api.chatExport(props.currentId)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${current?.title || '对话'}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  if (props.collapsed) {
    return (
      <div className="chat-toolbar collapsed">
        <button className="tbtn ico" onClick={props.onToggleCollapse} title="展开">✦</button>
      </div>
    )
  }

  return (
    <div className="chat-toolbar">
      <button className="tbtn" onClick={() => setShowSessions(v => !v)} title="会话列表">
        ▾ {current?.title || '新会话'}
      </button>
      <div className="tbtn-group">
        <button className="tbtn ico" onClick={() => setShowSearch(v => !v)} title="搜索">🔍</button>
        <button className="tbtn ico" onClick={doExport} title="导出 JSON">⤓</button>
        <button className="tbtn ico" onClick={props.onToggleCollapse} title="折叠">▸</button>
      </div>

      {showSessions && (
        <div className="dropdown">
          <button className="dd-item new" onClick={() => { props.onNewSession(); setShowSessions(false) }}>+ 新会话</button>
          {props.sessions.map(s => (
            <div key={s.id} className={`dd-item ${s.id === props.currentId ? 'active' : ''}`}>
              <span onClick={() => { props.onSelectSession(s.id); setShowSessions(false) }}>{s.title}</span>
              <button className="dd-del" onClick={() => setConfirmDel(s.id)}>✕</button>
            </div>
          ))}
        </div>
      )}

      {showSearch && (
        <div className="search-box">
          <input value={searchQ} onChange={e => setSearchQ(e.target.value)}
                 onKeyDown={e => e.key === 'Enter' && doSearch()} placeholder="搜索所有会话…" />
          <div className="search-hits">
            {hits.map((h, i) => (
              <div key={i} className="hit" onClick={() => { props.onJumpToMessage(h.session_id, h.message_index); setShowSearch(false) }}>
                <div className="hit-title">{h.session_title}</div>
                <div className="hit-snip">{h.snippet}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {confirmDel && (
        <div className="confirm-mask" onClick={() => setConfirmDel(null)}>
          <div className="confirm-box" onClick={e => e.stopPropagation()}>
            <p>删除此会话？不可恢复。</p>
            <button className="aibtn ghost" onClick={() => setConfirmDel(null)}>取消</button>
            <button className="aibtn solid" onClick={() => { props.onDeleteSession(confirmDel); setConfirmDel(null) }}>删除</button>
          </div>
        </div>
      )}
    </div>
  )
}
