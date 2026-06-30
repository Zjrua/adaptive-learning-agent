import type { ChatMessage as Msg, AgentEvent } from './types'
import { Markdown } from './Markdown'

export function ChatMessageView({ msg, streaming }: { msg: Msg; streaming?: boolean }) {
  if (msg.role === 'user') {
    return <div className="chat-msg user">{renderRefs(msg.content)}</div>
  }
  return (
    <div className="chat-msg assistant">
      {msg.events?.map((ev, i) => <EventView key={i} ev={ev} />)}
      {msg.content && (
        streaming
          ? <div className="chat-answer streaming">{msg.content}<span className="cursor">▌</span></div>
          : <div className="chat-answer"><Markdown content={msg.content} /></div>
      )}
    </div>
  )
}

// 把 #id @id $id 渲染成玉青 chip（用户消息用，纯文本消息）
function renderRefs(text: string) {
  const parts = text.split(/([#@$][^\s#@$，。、]+)/g)
  return parts.map((p, i) => {
    const m = p.match(/^([#@$])(.+)/)
    if (m) return <span key={i} className="ref-chip">{m[1]}{m[2]}</span>
    return <span key={i}>{p}</span>
  })
}

function EventView({ ev }: { ev: AgentEvent }) {
  switch (ev.type) {
    case 'thinking': return <div className="chat-thinking">💭 {ev.content}</div>
    case 'tool_call': return <div className="chat-tool">🔧 调用 {ev.action}</div>
    case 'tool_result': return <div className="chat-toolres">{ev.content}</div>
    case 'doc_card': return null   // 由 DocCard 渲染
    default: return null
  }
}
