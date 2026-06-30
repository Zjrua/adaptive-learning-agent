import { useState, useRef, useEffect } from 'react'
import { api } from './api'
import type { ChatMessage as Msg, AgentEvent } from './types'
import { ChatMessageView } from './ChatMessage'
import { DocCard } from './DocCard'

interface Props {
  onClose: () => void
}

/**
 * 右下角悬浮的 AI 对话面板。取代旧 AiModal，消费后端 SSE 事件流，
 * 渲染多轮对话 + 工具调用气泡 + 思考过程 + 文档卡片。
 */
export function AgentChat({ onClose }: Props) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    const userMsg: Msg = { role: 'user', content: text }
    const asstMsg: Msg = { role: 'assistant', content: '', events: [] }
    setMessages(m => [...m, userMsg, asstMsg])
    setBusy(true)
    try {
      await api.agentChatStream(text, (ev: AgentEvent) => {
        setMessages(m => {
          const copy = [...m]
          const last = { ...copy[copy.length - 1] }
          if (ev.type === 'final_answer') {
            last.content = (last.content || '') + ev.content
          } else {
            last.events = [...(last.events || []), ev]
          }
          copy[copy.length - 1] = last
          return copy
        })
      })
    } catch (e: any) {
      setMessages(m => {
        const copy = [...m]
        copy[copy.length - 1] = { ...copy[copy.length - 1], content: '⚠ ' + String(e.message || e) }
        return copy
      })
    }
    setBusy(false)
  }

  return (
    <div className="ai-fab-wrap">
      {/* 遮罩（点击外部关闭） */}
      <div className="ai-fab-mask" onClick={onClose} />
      {/* 对话面板：从右下角展开 */}
      <div className="ai-chat" role="dialog" aria-label="AI 学习助手">
        <div className="ai-chat-head">
          <div className="ai-chat-title">
            <span className="ai-orb">✦</span>
            <div>
              <div className="ai-name">AI 学习助手</div>
              <div className="ai-sub">会调工具、能查知识、可产笔记</div>
            </div>
          </div>
          <button className="ai-close" onClick={onClose} aria-label="关闭">✕</button>
        </div>
        <div className="ai-chat-body" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="chat-empty">问我学到哪了、下一步学啥、整理个笔记…</div>
          )}
          {messages.map((m, i) => (
            <div key={i}>
              <ChatMessageView msg={m} />
              {m.events?.some(e => e.type === 'doc_card') && (
                <DocCard
                  content={(m.events!.find(e => e.type === 'doc_card') as any)?.content || ''}
                  onPublished={() => {}}
                />
              )}
            </div>
          ))}
        </div>
        <div className="ai-input-row">
          <textarea
            className="ai-textarea"
            value={input}
            onChange={e => setInput(e.target.value)}
            rows={2}
            placeholder="问我学到哪了、下一步学啥、整理个笔记…"
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          />
          <button className="aibtn solid" onClick={send} disabled={busy || !input.trim()}>
            {busy ? '⏳' : '发送 ▸'}
          </button>
        </div>
      </div>
    </div>
  )
}
