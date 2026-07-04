import { useEffect, useMemo, useRef, useState } from 'react'
import type { Graph, Edge } from './types'
import { NodeCard } from './NodeCard'

interface Props {
  graph: Graph
  onToggle: (treeId: string, nodeId: string, taskId: string, done: boolean, isVerify: boolean) => Promise<Graph>
  onChanged: () => void
}

/**
 * 技能树画布。
 * - 节点位置用 CSS transition 平滑过渡
 * - SVG 连线在每一帧从节点【实际 DOM 位置】(getBoundingClientRect) 重算 → 跟随过渡，不错位
 * - 展开避让：ResizeObserver 监听 openNode 实际渲染高度，高度变化即重算 push
 */
export function SkillTree({ graph, onToggle, onChanged }: Props) {
  const [openNode, setOpenNode] = useState<string | null>(null)
  const [hoverNode, setHoverNode] = useState<string | null>(null)
  const [hoverDir, setHoverDir] = useState<string | null>(null)
  const [push, setPush] = useState(0)
  const nodeRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  const svgRef = useRef<SVGSVGElement>(null)
  const canvasRef = useRef<HTMLDivElement>(null)

  const { nodes, edges, canvas, constants } = graph
  const { NODE_W, NODE_H, ROW_GAP } = constants

  // openNode 的实时渲染高度（含展开详情）。用 ResizeObserver 跟踪，过渡期间持续更新。
  const [openHeight, setOpenHeight] = useState(NODE_H)
  useEffect(() => {
    if (!openNode) { setOpenHeight(NODE_H); return }
    const el = nodeRefs.current.get(openNode)
    if (!el) return
    const update = () => setOpenHeight(el.offsetHeight)
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [openNode, NODE_H])

  // push：由 openHeight 驱动（不用 effect，直接在渲染时算，避免时序问题）
  const openBaseY = openNode ? nodes.find(n => n.id === openNode)?.y ?? Infinity : Infinity
  const openBottom = openNode ? openBaseY + openHeight : 0
  const pushComputed = openNode ? Math.max(0, openBottom + 16 - (openBaseY + ROW_GAP)) : 0
  useEffect(() => { setPush(pushComputed) }, [pushComputed])

  const placed = useMemo(() => {
    return nodes.map(n => ({ node: n, x: n.x, y: n.y > openBaseY ? n.y + push : n.y }))
  }, [nodes, openBaseY, push])
  const height = canvas.h + push

  // ── 悬停路径：节点→上游祖先+下游后代；方向 chip→该方向全部节点及其上下游 ──
  const pathSet = useMemo(() => {
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
    if (hoverDir) {
      // 该方向的全部节点 + 它们的直接前置(1跳，含共享基础)，呈现这条方向的学习路径
      const dirNodes = new Set(nodes.filter(n => n.dirs.some(d => d.id === hoverDir)).map(n => n.id))
      const withParents = new Set(dirNodes)
      dirNodes.forEach(id => (parents.get(id) ?? []).forEach(p => withParents.add(p)))
      return withParents
    }
    if (!hoverNode) return null
    return new Set([hoverNode, ...reach(hoverNode, parents), ...reach(hoverNode, children)])
  }, [hoverNode, hoverDir, edges, nodes])

  const dim = hoverNode !== null || hoverDir !== null
  const onEdge = (e: Edge) => pathSet?.has(e.from) && pathSet?.has(e.to)

  // ── 连线：每帧从节点实时 DOM 位置重算，跟随过渡 ──
  const drawEdges = () => {
    const svg = svgRef.current, canvasEl = canvasRef.current
    if (!svg || !canvasEl) return
    const cr = canvasEl.getBoundingClientRect()
    const rectOf = (id: string) => {
      const el = nodeRefs.current.get(id); if (!el) return null
      const r = el.getBoundingClientRect()
      return { x: r.left - cr.left + r.width / 2, bottom: r.bottom - cr.top, top: r.top - cr.top }
    }
    svg.querySelectorAll('path.edge').forEach(p => {
      const f = p.getAttribute('data-from')!, t = p.getAttribute('data-to')!
      const a = rectOf(f), b = rectOf(t)
      if (!a || !b) return
      const ax = a.x, ay = a.bottom, bx = b.x, by = b.top, cy = (ay + by) / 2
      p.setAttribute('d', `M ${ax},${ay} C ${ax},${cy} ${bx},${cy} ${bx},${by}`)
      const fromNode = nodes.find(n => n.id === f)
      const onPath = pathSet ? onEdge({ from: f, to: t }) : false
      const fromDone = fromNode?.state === 'done'
      const cls = dim ? (onPath ? 'onpath' : 'hide') : (fromDone ? 'active' : 'normal')
      p.setAttribute('class', `edge ${cls}`)
    })
  }

  useEffect(() => {
    drawEdges()
    let raf = 0, start = performance.now()
    const loop = (now: number) => { drawEdges(); if (now - start < 400) raf = requestAnimationFrame(loop) }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [placed, hoverNode, hoverDir, nodes, dim, openHeight])

  return (
    <section className="forest-card" style={{ marginTop: 22 }}>
      <div className="forest-head">
        <div className="dir-legend">
          {graph.dir_order.map(d => (
            <span
              key={d.id}
              className="dir-chip"
              style={{ ['--c' as any]: d.color }}
              role="button"
              tabIndex={0}
              aria-pressed={hoverDir === d.id}
              onMouseEnter={() => setHoverDir(d.id)}
              onMouseLeave={() => setHoverDir(null)}
              onFocus={() => setHoverDir(d.id)}
              onBlur={() => setHoverDir(null)}
              onClick={() => setHoverDir(hoverDir === d.id ? null : d.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setHoverDir(hoverDir === d.id ? null : d.id) } }}
            >
              <i />{d.icon} {d.title}
            </span>
          ))}
          <span className="dir-hint">· 悬停节点或方向标签看学习路径</span>
        </div>
      </div>
      <div className={`dag-wrap ${dim ? 'dim' : ''}`}>
        <div className="dag-canvas" ref={canvasRef} style={{ width: canvas.w, height }}>
          <svg className="edges" ref={svgRef} width={canvas.w} height={height} viewBox={`0 0 ${canvas.w} ${height}`}>
            {edges.map((e, i) => (
              <path key={i} className="edge normal" data-from={e.from} data-to={e.to} d="" />
            ))}
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
