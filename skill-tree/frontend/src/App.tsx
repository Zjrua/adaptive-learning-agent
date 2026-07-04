import { useEffect, useState, useCallback, useRef } from 'react'
import type { Graph, Profile, Template, Fruit, Provider, LlmConfig } from './types'
import { api } from './api'
import { SkillTree } from './SkillTree'
import { ProfilePanel } from './panels/ProfilePanel'
import { TemplatesPanel } from './panels/TemplatesPanel'
import { FruitPanel } from './panels/FruitPanel'
import { SetupPanel } from './panels/SetupPanel'
import { AgentChat } from './AgentChat'
import { Achievement } from './Achievement'

type Route = 'tree' | 'profile' | 'templates' | 'fruit' | 'setup' | 'settings'
const ROUTES: Route[] = ['tree', 'profile', 'templates', 'fruit', 'setup', 'settings']

function currentRoute(): Route {
  const h = (location.hash || '#tree').slice(1)
  return ROUTES.includes(h as Route) ? (h as Route) : 'tree'
}

const AI_WIDTH_KEY = 'ai_width'
const AI_OPEN_KEY = 'ai_open'

export default function App() {
  const [route, setRoute] = useState<Route>(currentRoute())
  const [graph, setGraph] = useState<Graph | null>(null)
  const [graphErr, setGraphErr] = useState(false)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [templates, setTemplates] = useState<Template[]>([])
  const [fruits, setFruits] = useState<Fruit[]>([])
  const [reloadKey, setReloadKey] = useState(0)

  // AI 右栏开合 + 宽度（可拖动）
  const [aiOpen, setAiOpen] = useState(() => localStorage.getItem(AI_OPEN_KEY) !== 'false')
  const [aiWidth, setAiWidth] = useState(() => {
    const w = Number(localStorage.getItem(AI_WIDTH_KEY))
    return (w && w >= 280 && w <= 600) ? w : 400
  })

  useEffect(() => {
    const onHash = () => setRoute(currentRoute())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const refreshGraph = useCallback(() => {
    setGraphErr(false)
    api.graph().then(setGraph).catch(e => { console.error('graph', e); setGraphErr(true) })
  }, [])
  useEffect(refreshGraph, [refreshGraph, reloadKey])

  // NodeProposalCard 应用后 dispatch 'refresh-graph' → 重载图谱
  useEffect(() => {
    const h = () => { refreshGraph() }
    window.addEventListener('refresh-graph', h)
    return () => window.removeEventListener('refresh-graph', h)
  }, [refreshGraph])

  useEffect(() => {
    if (graph?.is_new_user && route !== 'setup' && route !== 'settings') {
      location.hash = 'setup'
    }
  }, [graph, route])

  useEffect(() => {
    if (route === 'profile' && !profile) api.profile().then(setProfile).catch(() => {})
    if (route === 'templates' && templates.length === 0) api.templates().then(setTemplates).catch(() => {})
    if (route === 'fruit' && fruits.length === 0) api.fruits().then(setFruits).catch(() => {})
  }, [route]) // eslint-disable-line

  const go = (r: Route) => { location.hash = r }
  const toggleAi = () => {
    setAiOpen(v => {
      const next = !v
      localStorage.setItem(AI_OPEN_KEY, String(next))
      return next
    })
  }

  const ov = graph?.overview
  const ringDash = ov ? 163.4 * (1 - ov.overall_pct / 100) : 163.4

  // AI 右栏布局态：setup/settings 时隐藏 AI
  const showAi = aiOpen && route !== 'setup' && route !== 'settings'

  return (
    <div className="app">
      {/* 顶栏 */}
      <header className="topbar">
        <div className="topbar-brand">
          <span className="topbar-logo">🌳</span>
          <span className="topbar-name serif">{profile?.name ?? '实习生'}</span>
        </div>
        <nav className="topbar-nav">
          {([
            ['tree', '🌳', '技能树'],
            ['profile', '👤', '信息'],
            ['templates', '📄', '模板'],
            ['fruit', '🍎', '果实'],
          ] as [Route, string, string][]).map(([r, ico, label]) => (
            <button key={r} className={`tnav-item ${route === r ? 'active' : ''}`} onClick={() => go(r)}>
              <span className="tnav-ico">{ico}</span><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          <div className="topbar-prog" title={`整体掌握度 ${ov?.overall_pct ?? 0}%`}>
            <svg viewBox="0 0 60 60">
              <circle className="ring-bg" cx="30" cy="30" r="26" />
              <circle className="ring-fg" cx="30" cy="30" r="26" strokeDasharray={163.4} strokeDashoffset={ringDash} />
            </svg>
            <span className="ring-txt">{ov?.overall_pct ?? 0}%</span>
          </div>
          <button className={`tnav-item ai-toggle ${showAi ? 'active' : ''}`} onClick={toggleAi} title="AI 助手">
            <span className="tnav-ico">✦</span><span>AI</span>
          </button>
          <button className={`tnav-item ${route === 'settings' || route === 'setup' ? 'active' : ''}`} onClick={() => go('settings')} title="设置">
            <span className="tnav-ico">⚙️</span>
          </button>
        </div>
      </header>

      {/* 主体：主内容 + 可拖动 AI 右栏 */}
      <div className="body" style={{ '--ai-width': `${aiWidth}px` } as React.CSSProperties}>
        <main className="main">
          {route === 'tree' && graphErr && (
            <div className="panel active">
              <div className="empty-state">
                <p>⚠ 图谱加载失败,请检查后端是否运行。</p>
                <button className="btn primary" onClick={() => setReloadKey(k => k + 1)}>重试</button>
              </div>
            </div>
          )}
          {route === 'tree' && !graph && !graphErr && (
            <div className="panel active">
              <div className="empty-state"><p>加载中…</p></div>
            </div>
          )}
          {route === 'tree' && graph && (
            <>
              <div className="panel active">
                <div className="panel-head">
                  <h2 className="serif panel-title">知识图谱</h2>
                  <p className="panel-sub">所有方向汇于一棵树 · <b>基础在上，向下生长</b></p>
                </div>
                {graph.is_new_user ? (
                  <div className="empty-state">
                    <p>这个用户还没有技能树。</p>
                    <button className="btn primary" onClick={() => go('setup')}>🚀 去初始化生成 →</button>
                  </div>
                ) : (
                  <>
                    <div className="dashboard">
                      <Metric v={`${ov!.overall_pct}%`} l="整体掌握度" />
                      <Metric v={`${ov!.mastered_points}`} l="已掌握知识点" sub={`/ ${ov!.total_points}`} />
                      <Metric v={`${ov!.done_nodes}`} l="已点亮节点" sub={`/ ${ov!.total_nodes}`} />
                      <Metric v={`${ov!.achievements_unlocked}`} l="成就绽放" sub={`/ ${ov!.achievements_total}`} />
                    </div>
                    <SkillTree graph={graph} onToggle={api.patchTask} onChanged={refreshGraph} />
                    <Achievement achievements={graph.achievements} />
                  </>
                )}
              </div>
            </>
          )}
          {(route === 'setup' || route === 'settings') && <SetupPanel onDone={() => go('tree')} />}
          {route === 'profile' && <ProfilePanel profile={profile} />}
          {route === 'templates' && <TemplatesPanel templates={templates} />}
          {route === 'fruit' && <FruitPanel fruits={fruits} />}
        </main>

        {/* 可拖动分隔条 + AI 右栏 */}
        {showAi && (
          <>
            <div className="ai-resizer" onMouseDown={startResize(setAiWidth, aiWidth)} />
            <aside className="ai-aside">
              <AgentChat onClose={toggleAi} />
            </aside>
          </>
        )}
      </div>
    </div>
  )
}

/** 拖动分隔条：更新 AI 宽度，clamp 280~600 */
function startResize(setAiWidth: (f: (w: number) => number) => void, _initial: number) {
  return (e: React.MouseEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startW = _initial
    let raf = 0
    const onMove = (ev: MouseEvent) => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        // 向左拖（AI 变宽）：delta 负
        const w = Math.max(280, Math.min(600, startW + (startX - ev.clientX)))
        setAiWidth(() => w)
      })
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      // 存最终宽度
      setAiWidth(w => { localStorage.setItem(AI_WIDTH_KEY, String(w)); return w })
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }
}

function Metric({ v, l, sub }: { v: string; l: string; sub?: string }) {
  return (
    <div className="metric">
      <div className="v">{v}{sub && <span className="of">{sub}</span>}</div>
      <div className="l">{l}</div>
    </div>
  )
}
