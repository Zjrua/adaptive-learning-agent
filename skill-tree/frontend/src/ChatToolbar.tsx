import { useState, useEffect } from 'react'
import type { ChatSession, SearchHit, Provider, LlmConfig } from './types'
import { api } from './api'

interface Props {
  sessions: ChatSession[]
  currentId: string | null
  collapsed: boolean
  onToggleCollapse: () => void
  onClose?: () => void              // 收起 AI 栏
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

  // 供应商切换
  const [providers, setProviders] = useState<Provider[]>([])
  const [cfg, setCfg] = useState<LlmConfig>({ provider: '', base_url: '', api_key: '', model: '' })

  useEffect(() => {
    api.providers().then(setProviders).catch(() => {})
    api.getLlmConfig().then(setCfg).catch(() => {})
  }, [])

  const current = props.sessions.find(s => s.id === props.currentId)

  const switchProvider = async (pid: string) => {
    const p = providers.find(x => x.id === pid)
    if (!p) return
    const newCfg: LlmConfig = { ...cfg, provider: pid, base_url: p.base_url, model: p.model }
    setCfg(newCfg)
    try { await api.saveLlmConfig(newCfg) } catch { /* ignore */ }
  }

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
        <button className="tbtn ico" onClick={props.onToggleCollapse} title="展开">▢</button>
        {props.onClose && <button className="tbtn ico" onClick={props.onClose} title="收起">✕</button>}
      </div>
    )
  }

  return (
    <div className="chat-toolbar">
      {/* 第一行：标题 + 收起/关闭 */}
      <div className="ct-row ct-head">
        <div className="ct-title"><span className="ai-orb">✦</span> AI 助手</div>
        <div className="ct-actions">
          <button className="tbtn ico" onClick={props.onToggleCollapse} title="折叠工具条">▢</button>
          {props.onClose && <button className="tbtn ico" onClick={props.onClose} title="收起">✕</button>}
        </div>
      </div>

      {/* 第二行：供应商切换(下拉,直选目标) */}
      <div className="ct-row ct-provider">
        <span className="provider-dot" style={{ background: 'var(--jade)' }} />
        <select
          className="provider-select"
          value={cfg.provider}
          onChange={e => switchProvider(e.target.value)}
          title="切换 LLM 供应商"
        >
          <option value="" disabled>未配置</option>
          {providers.map(p => (
            <option key={p.id} value={p.id}>{p.label}</option>
          ))}
        </select>
      </div>

      {/* 第三行：会话/搜索/导出 */}
      <div className="ct-row ct-tools">
        <button className="tbtn sm" onClick={() => setShowSessions(v => !v)}>
          ▾ {current?.title?.slice(0, 8) || '新会话'}
        </button>
        <button className="tbtn ico" onClick={props.onNewSession} title="新对话">＋</button>
        <button className="tbtn ico" onClick={() => setShowSearch(v => !v)} title="搜索">🔍</button>
        <button className="tbtn ico" onClick={doExport} title="导出 JSON">⤓</button>
      </div>

      {showSessions && (
        <div className="dropdown">
          {props.sessions.map(s => (
            <div key={s.id} className={`dd-item ${s.id === props.currentId ? 'active' : ''}`}>
              <span className="dd-label" onClick={() => { props.onSelectSession(s.id); setShowSessions(false) }}>{s.title}</span>
              <button className="dd-del" onClick={() => setConfirmDel(s.id)}>✕</button>
            </div>
          ))}
          {props.sessions.length === 0 && <div className="dd-empty">暂无会话</div>}
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
            <div className="confirm-actions">
              <button className="aibtn ghost" onClick={() => setConfirmDel(null)}>取消</button>
              <button className="aibtn solid" onClick={() => { props.onDeleteSession(confirmDel); setConfirmDel(null) }}>删除</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
