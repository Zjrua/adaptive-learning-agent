import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Graph, GraphNode, Edge } from './types'
import { NodeCard } from './NodeCard'

interface Props {
  graph: Graph
  onToggle: (treeId: string, nodeId: string, taskId: string, done: boolean, isVerify: boolean) => Promise<Graph>
  onChanged: () => void
}

/**
 * 技能树画布。布局单一来源：节点和 SVG 连线都从同一份 placed 派生 → 展开/勾选时同步，永不错位。
 * 展开避让：openNode 变化时用 useLayoutEffect 实测详情真实高度，算 push，下方节点下推。
 */
export function SkillTree({ graph, onToggle, onChanged }: Props) {
  const [openNode, setOpenNode] = useState<string | null>(null)
  const [hoverNode, setHoverNode] = useState<string | null>(null)
  const [push, setPush] = useState(0)
  const nodeRefs = useRef<Map<string, HTMLDivElement>>(new Map())

  const { nodes, edges, canvas, constants } = graph
  const { NODE_W, NODE_H, ROW_GAP } = constants

  // ── 展开避让：实测 openNode 真实高度，算 push ──
  useLayoutEffect(() => {
    if (!openNode) { setPush(0); return }
    const el = nodeRefs.current.get(openNode)
    if (!el) { setPush(0); return }
    const on = nodes.find(n => n.id === openNode)!
    const realH = el.offsetHeight           // 含详情的真实高度
    const openBottom = on.y + realH
    // 下一行原顶 = on.y + ROW_GAP；溢出行间隙的量即 push（留 16px 间距）
    setPush(Math.max(0, openBottom + 16 - (on.y + ROW_GAP)))
  }, [openNode, nodes, ROW_GAP])

  // placed：openNode 下方节点 + push，其余原位
  const placed = useMemo(() => {
    const openY = openNode ? nodes.find(n => n.id === openNode)?.y : Infinity
    return nodes.map(n => ({ node: n, x: n.x, y: n.y > (openY ?? Infinity) ? n.y + push : n.y }))
  }, [nodes, openNode, push])
  const height = canvas.h + push

  // ── 悬停路径：上游祖先 + 下游后代 ──
  const pathSet = useMemo(() => {
    if (!hoverNode) return null
    const parents = new Map<string, string[]>()
    const children = new Map<string, string[]>()
    edges.forEach(e => {
      parents.set(e.to, [...(parents.get(e.to) ?? []), e.from])
      children.set(e.from, [...(children.get(e.from) ?? []), e.to])
    })
    const reach = (start: string, g: Map<string, string[]>) => {
      const seen = new Set<string>()
      const q = [...(g.get(start) ?? [])]
      while (q.length) {
        const n = q.shift()!
        if (seen.has(n)) continue
        seen.add(n)
        q.push(...(g.get(n) ?? []))
      }
      return seen
    }
    return new Set([hoverNode, ...reach(hoverNode, parents), ...reach(hoverNode, children)])
  }, [hoverNode, edges])

  const placedById = new Map(placed.map(p => [p.node.id, p]))
  const dim = hoverNode !== null

  const onEdge = (e: Edge) => pathSet?.has(e.from) && pathSet?.has(e.to)
  // openNode 的真实底边（用于它自己向下出发的边）
  const openRealBottom = openNode && nodeRefs.current.get(openNode)
    ? (nodes.find(n => n.id === openNode)!.y + nodeRefs.current.get(openNode)!.offsetHeight)
    : null

  return (
    <section className="forest-card" style={{ marginTop: 22 }}>
      <div className="forest-head">
        <div className="dir-legend">
          {graph.dir_order.map(d => (
            <span key={d.id} className="dir-chip" style={{ ['--c' as any]: d.color }}>
              <i />{d.icon} {d.title}
            </span>
          ))}
          <span className="dir-hint">· 悬停节点看学习路径</span>
        </div>
      </div>
      <div className={`dag-wrap ${dim ? 'dim' : ''}`}>
        <div className="dag-canvas" style={{ width: canvas.w, height }}>
          <svg className="edges" width={canvas.w} height={height} viewBox={`0 0 ${canvas.w} ${height}`}>
            {edges.map((e, i) => {
              const a = placedById.get(e.from), b = placedById.get(e.to)
              if (!a || !b) return null
              const ax = a.x + NODE_W / 2
              // from 的底边：openNode 用实测真实底，其余用 NODE_H
              const ay = (e.from === openNode && openRealBottom !== null) ? openRealBottom : a.y + NODE_H
              const bx = b.x + NODE_W / 2
              const by = b.y
              const cy = (ay + by) / 2
              const onPath = pathSet ? onEdge(e) : false
              const fromDone = a.node.state === 'done'
              const cls = dim ? (onPath ? 'onpath' : 'hide') : (fromDone ? 'active' : 'normal')
              return (
                <path key={i} className={`edge ${cls}`} d={`M ${ax},${ay} C ${ax},${cy} ${bx},${cy} ${bx},${by}`} />
              )
            })}
          </svg>
          {placed.map(({ node, x, y }) => (
            <NodeCard
              key={node.id}
              ref={(el: HTMLDivElement | null) => { if (el) nodeRefs.current.set(node.id, el); else nodeRefs.current.delete(node.id) }}
              node={node}
              x={x}
              y={y}
              open={openNode === node.id}
              onPath={pathSet?.has(node.id) ?? false}
              dim={dim}
              onOpenToggle={() => setOpenNode(openNode === node.id ? null : node.id)}
              onHover={(h) => setHoverNode(h ? node.id : null)}
              onToggle={onToggle}
              onChanged={onChanged}
            />
          ))}
        </div>
      </div>
    </section>
  )
}
