import type { ChatMessage as Msg, AgentEvent } from './types'

export function ChatMessageView({ msg }: { msg: Msg }) {
  if (msg.role === 'user') {
    return <div className="chat-msg user">{msg.content}</div>
  }
  return (
    <div className="chat-msg assistant">
      {msg.events?.map((ev, i) => <EventView key={i} ev={ev} />)}
      {msg.content && <div className="chat-answer">{msg.content}</div>}
    </div>
  )
}

function EventView({ ev }: { ev: AgentEvent }) {
  switch (ev.type) {
    case 'thinking':
      return <div className="chat-thinking">💭 {ev.content}</div>
    case 'tool_call':
      return <div className="chat-tool">🔧 调用 {ev.action}</div>
    case 'tool_result':
      return <div className="chat-toolres">{ev.content}</div>
    case 'doc_card':
      return null  // 由 DocCard 渲染（上层处理）
    default:
      return null
  }
}
