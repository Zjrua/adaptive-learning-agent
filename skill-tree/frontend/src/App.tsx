import { useEffect, useState, useCallback } from 'react'
import type { Graph, Profile, Template, Fruit } from './types'
import { api, getUserId } from './api'
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

export default function App() {
  const [route, setRoute] = useState<Route>(currentRoute())
  const [graph, setGraph] = useState<Graph | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [templates, setTemplates] = useState<Template[]>([])
  const [fruits, setFruits] = useState<Fruit[]>([])
  const [showAi, setShowAi] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const onHash = () => setRoute(currentRoute())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // 拉取主图（用户切换/数据变更后重拉）
  const refreshGraph = useCallback(() => {
    api.graph().then(setGraph).catch(e => console.error('graph', e))
  }, [])
  useEffect(refreshGraph, [refreshGraph, reloadKey])

  // 新用户首次访问：自动跳初始化（已进入 setup/settings 时不重复跳）
  useEffect(() => {
    if (graph?.is_new_user && route !== 'setup' && route !== 'settings') {
      location.hash = 'setup'
    }
  }, [graph, route])

  // 用户切换：清缓存 + 重拉所有
  const onUserChanged = useCallback(() => {
    setProfile(null); setTemplates([]); setFruits([])
    setReloadKey(k => k + 1)
  }, [])

  // 各板块懒加载
  useEffect(() => {
    if (route === 'profile' && !profile) api.profile().then(setProfile).catch(() => {})
    if (route === 'templates' && templates.length === 0) api.templates().then(setTemplates).catch(() => {})
    if (route === 'fruit' && fruits.length === 0) api.fruits().then(setFruits).catch(() => {})
  }, [route]) // eslint-disable-line

  const go = (r: Route) => { location.hash = r }

  const ov = graph?.overview
  const ringDash = ov ? 163.4 * (1 - ov.overall_pct / 100) : 163.4

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sb-brand">
          <div className="sb-logo">🌳</div>
          <div className="sb-name serif">{profile?.name ?? '实习生'}</div>
          <div className="sb-tag">{profile?.tagline ?? ''}</div>
        </div>
        <nav className="sb-nav">
          {([
            ['tree', '🌳', '技能树'],
            ['profile', '👤', '个人信息'],
            ['templates', '📄', '简历模板'],
            ['fruit', '🍎', '果实展示'],
          ] as [Route, string, string][]).map(([r, ico, label]) => (
            <button key={r} className={`sb-item ${route === r ? 'active' : ''}`} onClick={() => go(r)}>
              <span className="sb-ico">{ico}</span><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sb-bottom">
          <button className={`sb-item settings-link ${route === 'settings' || route === 'setup' ? 'active' : ''}`} onClick={() => go('settings')}>
            <span className="sb-ico">⚙️</span><span>设置</span>
          </button>
        <div className="sb-foot">
          <div className="sb-prog-ring">
            <svg viewBox="0 0 60 60">
              <circle className="ring-bg" cx="30" cy="30" r="26" />
              <circle
                className="ring-fg"
                cx="30" cy="30" r="26"
                strokeDasharray={163.4}
                strokeDashoffset={ringDash}
              />
            </svg>
            <span className="ring-txt">{ov?.overall_pct ?? 0}%</span>
          </div>
          <div className="sb-stats">
            <b>{ov?.achievements_unlocked ?? 0}</b> 成就<br />
            <b>{ov?.mastered_points ?? 0}/{ov?.total_points ?? 0}</b> 知识点
          </div>
        </div>
        </div>
      </aside>

      <main className="main">
        {route === 'tree' && graph && (
          <>
            <div className="panel active">
              <div className="panel-head">
                <h2 className="serif panel-title">知识图谱</h2>
                <p className="panel-sub">所有方向汇于一棵树 · <b>基础在上，向下生长</b> · 当前用户 <b>{getUserId()}</b></p>
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
        {(route === 'setup' || route === 'settings') && <SetupPanel onUserChanged={onUserChanged} onDone={() => go('tree')} />}
        {route === 'profile' && <ProfilePanel profile={profile} />}
        {route === 'templates' && <TemplatesPanel templates={templates} />}
        {route === 'fruit' && <FruitPanel fruits={fruits} />}
      </main>

      {showAi && (
        <AgentChat onClose={() => setShowAi(false)} />
      )}

      {/* 右下角悬浮 AI 按钮（任意页面可见，树板块下点开对话） */}
      {graph && !graph.is_new_user && !showAi && route !== 'setup' && route !== 'settings' && (
        <button className="ai-fab" onClick={() => setShowAi(true)} aria-label="AI 生成">
          <span className="ai-fab-icon">✦</span>
          <span className="ai-fab-pulse" />
        </button>
      )}
    </div>
  )
}

function Metric({ v, l, sub }: { v: string; l: string; sub?: string }) {
  return (
    <div className="metric">
      <div className="v">{v}{sub && <span className="of">{sub}</span>}</div>
      <div className="l">{l}</div>
    </div>
  )
}
