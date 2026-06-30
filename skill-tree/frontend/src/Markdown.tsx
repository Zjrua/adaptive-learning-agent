import { useMemo } from 'react'
import { marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/common'

// 配置 marked：代码块用 highlight.js 高亮（marked v18 需用 marked-highlight 扩展）
marked.use(markedHighlight({
  langPrefix: 'hljs language-',
  highlight(code, lang) {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext'
    try {
      return hljs.highlight(code, { language }).value
    } catch {
      return code
    }
  },
}))

/**
 * Markdown 渲染组件：marked 解析 → DOMPurify 防 XSS → dangerouslySetInnerHTML。
 * 用于 Agent final_answer 和文档预览。样式由 .md 类（玉青宝石工坊）控制。
 */
export function Markdown({ content }: { content: string }) {
  const html = useMemo(() => {
    const raw = marked.parse(content || '', { async: false }) as string
    return DOMPurify.sanitize(raw)
  }, [content])
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
}
