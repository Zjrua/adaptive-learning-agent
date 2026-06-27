import { forwardRef } from 'react'
import type { GraphNode, Task } from './types'

interface Props {
  node: GraphNode
  x: number
  y: number
  open: boolean
  onPath: boolean
  dim: boolean
  onOpenToggle: () => void
  onHover: (h: boolean) => void
  onToggle: (treeId: string, nodeId: string, taskId: string, done: boolean, isVerify: boolean) => Promise<any>
  onChanged: () => void
}

const ORB = { done: '🍎', learning: '🌼', locked: '🌱' }

export const NodeCard = forwardRef<HTMLDivElement, Props>(function NodeCard(
  { node, x, y, open, onPath, dim, onOpenToggle, onHover, onToggle, onChanged }, ref
) {
  const treeId = node.dirs[0]?.id ?? ''

  const handleToggle = (taskId: string, done: boolean, isVerify: boolean) => {
    onToggle(treeId, node.id, taskId, !done, isVerify).then(onChanged)
  }

  return (
    <div
      ref={ref}
      className={`node s-${node.state} ${open ? 'open' : ''} ${onPath ? 'onpath' : ''} ${dim && !onPath ? 'fade' : ''}`}
      style={{ left: x, top: y }}
      onClick={onOpenToggle}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
    >
      <div className="node-top">
        <div>
          <div className="node-name">{node.name}</div>
          <div className="node-cat">{node.category}</div>
        </div>
        <div className="node-orb">{ORB[node.state]}</div>
      </div>
      <div className="nbar"><i style={{ width: `${node.pct}%` }} /></div>
      <div className="ncount">{node.mastered}/{node.total_points} · {node.pct}%</div>
      {node.dirs.length > 0 && (
        <div className="dir-dots">
          {node.dirs.map(d => (
            <i key={d.id} style={{ background: d.color }} title={d.id} />
          ))}
        </div>
      )}
      {open && (
        <div className="detail" onClick={e => e.stopPropagation()}>
          {node.tasks.map(tk => (
            <KnowledgePoint
              key={tk.id}
              task={tk}
              onCheck={(done) => handleToggle(tk.id, done, false)}
              onCheckVerify={(vId, done) => handleToggle(vId, done, true)}
            />
          ))}
          {node.depends_on.length > 0 && (
            <div className="ndeps">前置: {node.depends_on.join(', ')}</div>
          )}
        </div>
      )}
    </div>
  )
})

/** 一个知识点：学习任务 + 其下的验收子任务 */
function KnowledgePoint({
  task, onCheck, onCheckVerify,
}: {
  task: Task
  onCheck: (done: boolean) => void
  onCheckVerify: (vId: string, done: boolean) => void
}) {
  const hasVerify = (task.verify?.length ?? 0) > 0
  // 有验收时，学习任务勾选框是清单提示（disabled）
  return (
    <div className="kp">
      <div className={`task-row ${task.done ? 'done' : ''} ${hasVerify ? 'checklist' : ''}`}>
        <input
          type="checkbox"
          checked={!!task.done}
          disabled={hasVerify}
          onChange={(e) => !hasVerify && onCheck(e.target.checked)}
        />
        <label>
          {hasVerify && <span className="clist">清单</span>}
          {task.title}
        </label>
        {task.resource && (
          <a className="res" href={fixRes(task.resource)} target="_blank" rel="noopener" onClick={e => e.stopPropagation()}>🔗</a>
        )}
      </div>
      {task.verify?.map(v => (
        <div key={v.id} className={`task-row verify ${v.done ? 'done' : ''}`}>
          <input type="checkbox" checked={!!v.done} onChange={(e) => onCheckVerify(v.id, e.target.checked)} />
          <label>🎯 {v.title}</label>
        </div>
      ))}
    </div>
  )
}

// 后端 resource 是相对 skill-tree/ 的路径(../../projects/...)；前端走 /projects 代理
function fixRes(r: string): string {
  if (r.startsWith('http')) return r
  // ../../projects/DeepCTR-Torch/... → /projects/DeepCTR-Torch/...
  return r.replace(/^(\.\.\/)+projects\//, '/projects/')
}
