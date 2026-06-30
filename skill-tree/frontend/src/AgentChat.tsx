import { useState, useRef, useEffect, useCallback } from 'react'
import { api, getUserId } from './api'
import type { ChatMessage as Msg, ChatSession, AgentEvent } from './types'
import { ChatMessageView } from './ChatMessage'
import { ChatToolbar } from './ChatToolbar'
import { MentionInput } from './MentionInput'
import { DocCard } from './DocCard'

interface Props {
  variant?: 'dock' | 'page'
}

const CACHE_KEY = (uid: string) => `chat_${uid}`

/**
 * AI 对话区：桌面端常驻右侧 dock，移动端 #chat 全屏 page。
 * 多会话(/new + 下拉切换) + 流式渲染(delta) + 双写持久化 + 符号引用。
 */
export function AgentChat({ variant = 'dock' }: Props) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const uid = getUserId()
  const current = sessions.find(s => s.id === currentId)

  // 首屏加载：localStorage 缓存秒开 → 后端校正
  useEffect(() => {
    const cached = localStorage.getItem(CACHE_KEY(uid))
    if (cached) {
      try {
        const c = JSON.parse(cached)
        setSessions(c.sessions || []); setCurrentId(c.current_session_id)
      } catch { /* ignore */ }
    }
    api.chatHistory().then(h => {
      setSessions(h.sessions); setCurrentId(h.current_session_id)
      if (h.sessions.length === 0) newSession()
    }).catch(() => {})
    // eslint-disable-next-line
  }, [uid])

  // 双写：sessions 变化时同步后端 + 缓存
  const sync = useCallback((newSessions: ChatSession[], newCurrent: string | null) => {
    localStorage.setItem(CACHE_KEY(uid), JSON.stringify({ sessions: newSessions, current_session_id: newCurrent }))
    api.chatSync(newSessions, newCurrent).catch(() => {})
  }, [uid])

  const newSession = useCallback(() => {
    const sid = `s_${Date.now()}`
    const s: ChatSession = {
      id: sid, title: '新会话',
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(), messages: [],
    }
    setSessions(prev => {
      const next = [...prev, s]
      sync(next, sid)
      return next
    })
    setCurrentId(sid)
  }, [sync])

  const updateCurrent = useCallback((updater: (s: ChatSession) => ChatSession) => {
    setSessions(prev => {
      const next = prev.map(s => s.id === currentId ? updater(s) : s)
      return next
    })
  }, [currentId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [current?.messages])

  const send = async () => {
    const text = input.trim()
    if (!text || busy || !currentId) return
    setInput('')
    const userMsg: Msg = { role: 'user', content: text, ts: new Date().toISOString() }
    const asstMsg: Msg = { role: 'assistant', content: '', events: [], ts: new Date().toISOString() }
    let isFirstMsg = current?.messages.length === 0
    updateCurrent(s => ({ ...s, messages: [...s.messages, userMsg, asstMsg] }))
    setBusy(true); setStreaming(true)

    // 异步生成标题（首条消息后）
    if (isFirstMsg) {
      api.chatTitle(text).then(r => {
        setSessions(prev => {
          const next = prev.map(s => s.id === currentId ? { ...s, title: r.title } : s)
          sync(next, currentId)
          return next
        })
      }).catch(() => {})
    }

    try {
      await api.agentChatStream(text, (ev: AgentEvent) => {
        setSessions(prev => {
          const next = prev.map(s => {
            if (s.id !== currentId) return s
            const msgs = [...s.messages]
            const last = { ...msgs[msgs.length - 1] }
            if (ev.type === 'delta') {
              last.content = (last.content || '') + ev.content
            } else if (ev.type === 'final_done') {
              // 流式结束，content 已完整
            } else if (ev.type === 'final_answer') {
              last.content = ev.content   // 降级兜底
            } else {
              last.events = [...(last.events || []), ev]
            }
            msgs[msgs.length - 1] = last
            return { ...s, messages: msgs }
          })
          return next
        })
      })
      // 流式结束后同步后端
      setSessions(prev => { sync(prev, currentId); return prev })
    } catch (e: any) {
      updateCurrent(s => {
        const msgs = [...s.messages]
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: '⚠ ' + String(e.message || e) }
        return { ...s, messages: msgs }
      })
    }
    setBusy(false); setStreaming(false)
  }

  const handleCommand = (cmd: string) => {
    if (cmd === '/new') newSession()
  }

  const deleteSession = (id: string) => {
    setSessions(prev => {
      const next = prev.filter(s => s.id !== id)
      const newCurrent = id === currentId ? (next[0]?.id ?? null) : currentId
      sync(next, newCurrent)
      return next
    })
    if (id === currentId) {
      // currentId 用 setSessions 后的状态计算
      setSessions(prev => {
        setCurrentId(prev[0]?.id ?? null)
        return prev
      })
    }
  }

  const jumpToMessage = (sessionId: string, _msgIndex: number) => {
    setCurrentId(sessionId)
    setTimeout(() => {
      const el = scrollRef.current
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }, 100)
  }

  return (
    <div className={`agent-chat ${variant}`}>
      <ChatToolbar
        sessions={sessions} currentId={currentId} collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(v => !v)}
        onSelectSession={setCurrentId}
        onNewSession={newSession}
        onDeleteSession={deleteSession}
        onJumpToMessage={jumpToMessage}
      />
      {!collapsed && (
        <>
          <div className="chat-msgs" ref={scrollRef}>
            {(current?.messages.length ?? 0) === 0 && (
              <div className="chat-empty">问我学到哪了、下一步学啥…<br />用 #节点 @资源 $方向 引用，/new 开新会话</div>
            )}
            {current?.messages.map((m, i) => (
              <div key={i}>
                <ChatMessageView msg={m}
                  streaming={streaming && i === (current.messages.length - 1) && m.role === 'assistant'} />
                {m.events?.some(e => e.type === 'doc_card') && (
                  <DocCard content={(m.events!.find(e => e.type === 'doc_card') as any)?.content || ''} onPublished={() => {}} />
                )}
              </div>
            ))}
          </div>
          <MentionInput value={input} onChange={setInput} onSend={send}
                        onCommand={handleCommand} placeholder="问我… #节点 @资源 $方向 /new" />
        </>
      )}
    </div>
  )
}
