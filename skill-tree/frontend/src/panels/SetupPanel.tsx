import { useEffect, useState } from 'react'
import { api, getUserId, setUserId, getLarkConfig, listWikiSpaces, setWikiSpace, type UserInfo } from '../api'
import type { Provider, LlmConfig } from '../types'

interface Props {
  onUserChanged: () => void   // 用户切换后重载所有数据
  onDone: () => void          // 完成初始化，跳转技能树
}

const STEPS = ['选择用户', '配置模型', '生成技能树'] as const

export function SetupPanel({ onUserChanged, onDone }: Props) {
  const [step, setStep] = useState(0)
  const [users, setUsers] = useState<UserInfo[]>([])
  const [newName, setNewName] = useState('')
  const [providers, setProviders] = useState<Provider[]>([])
  const [cfg, setCfg] = useState<LlmConfig>({ provider: '', base_url: '', api_key: '', model: '' })
  const [testing, setTesting] = useState(false)
  const [testMsg, setTestMsg] = useState<{ ok: boolean; msg: string } | null>(null)
  const [models, setModels] = useState<string[]>([])
  const [fetchingModels, setFetchingModels] = useState(false)
  const [modelErr, setModelErr] = useState('')
  const [jd, setJd] = useState('')
  const [generating, setGenerating] = useState(false)
  const [genResult, setGenResult] = useState<{ trees: any[]; profile: any } | null>(null)
  const [error, setError] = useState('')
  const [spaces, setSpaces] = useState<{ space_id: string; name: string }[]>([])
  const [curSpace, setCurSpace] = useState<string | null>(null)
  const [spaceErr, setSpaceErr] = useState('')
  const [spaceBusy, setSpaceBusy] = useState(false)

  // 加载用户列表 + 供应商 + 当前 LLM 配置
  useEffect(() => {
    api.users().then(setUsers).catch(() => {})
    api.providers().then(setProviders).catch(() => {})
    api.getLlmConfig().then(setCfg).catch(() => {})
    getLarkConfig().then(c => setCurSpace(c.wiki_space_id)).catch(() => {})
    listWikiSpaces().then(r => {
      if (r.ok) setSpaces(r.spaces || [])
      else setSpaceErr(r.error || '无法获取空间列表')
    }).catch(e => setSpaceErr(String(e)))
  }, [])

  const onPickSpace = async (id: string) => {
    setSpaceBusy(true)
    try { await setWikiSpace(id); setCurSpace(id) }
    finally { setSpaceBusy(false) }
  }

  const pickUser = (id: string) => { setUserId(id); onUserChanged() }
  const createAndPick = async () => {
    if (!newName.trim()) return
    try {
      await api.createUser(newName.trim())
      setUserId(newName.trim())
      onUserChanged()
      setUsers(await api.users())
      setStep(1)
    } catch (e: any) { setError(String(e.message || e)) }
  }

  const pickProvider = (p: Provider) => {
    setCfg(c => ({ ...c, provider: p.id, base_url: p.base_url, model: p.model }))
    setModels([])   // 切供应商清空已拉取的模型列表
    setModelErr('')
  }
  const saveCfg = async () => {
    await api.saveLlmConfig(cfg)
    setStep(2)
  }
  const testCfg = async () => {
    setTesting(true); setTestMsg(null)
    try {
      const r = await api.testLlmConfig(cfg)
      setTestMsg({ ok: r.ok, msg: r.message })
    } catch (e: any) { setTestMsg({ ok: false, msg: String(e.message || e) }) }
    setTesting(false)
  }
  const fetchModels = async () => {
    if (!cfg.base_url || !cfg.api_key) { setModelErr('请先填 Base URL 和 API Key'); return }
    setFetchingModels(true); setModelErr('')
    try {
      const r = await api.listModels(cfg)
      if (r.ok && r.models.length) {
        setModels(r.models)
        // 若当前 model 不在列表里，默认选第一个
        if (!cfg.model || !r.models.includes(cfg.model)) {
          setCfg(c => ({ ...c, model: r.models[0] }))
        }
      } else {
        setModelErr(r.error || '未获取到模型')
      }
    } catch (e: any) { setModelErr(String(e.message || e)) }
    setFetchingModels(false)
  }

  const generate = async () => {
    if (!jd.trim()) return
    setGenerating(true); setError(''); setGenResult(null)
    try {
      const r = await api.generateTree(jd, '')
      setGenResult(r.data)
    } catch (e: any) { setError(String(e.message || e)) }
    setGenerating(false)
  }
  const apply = async () => {
    if (!genResult) return
    await api.applyTree(genResult.trees, genResult.profile)
    onUserChanged()
    onDone()
  }

  return (
    <section className="panel active">
      <div className="panel-head">
        <h2 className="serif panel-title">⚙️ 设置</h2>
        <p className="panel-sub">用户切换 · 大模型配置 · AI 生成/重建技能树</p>
      </div>

      <div className="setup-steps">
        {STEPS.map((s, i) => (
          <div key={s} className={`setup-step ${i === step ? 'active' : ''} ${i < step ? 'done' : ''}`}>
            <span className="step-num">{i < step ? '✓' : i + 1}</span>
            <span className="step-label">{s}</span>
          </div>
        ))}
      </div>

      {error && <div className="setup-error">⚠ {error}</div>}

      {/* Step 0: 用户 */}
      {step === 0 && (
        <div className="setup-card">
          <h3 className="psec">选择已有用户</h3>
          <div className="user-grid">
            {users.map(u => (
              <button key={u.id} className={`user-chip ${getUserId() === u.id ? 'active' : ''}`} onClick={() => pickUser(u.id)}>
                {u.name} <span className="uid">{u.id}</span>
                {getUserId() === u.id && <span className="cur">当前</span>}
              </button>
            ))}
          </div>
          <h3 className="psec" style={{ marginTop: 24 }}>或新建用户</h3>
          <div className="inline-form">
            <input className="field" value={newName} onChange={e => setNewName(e.target.value)} placeholder="用户名（字母/数字/中文）" />
            <button className="btn" onClick={createAndPick} disabled={!newName.trim()}>新建并进入 →</button>
          </div>
          <div className="setup-hint">当前用户：<b>{getUserId()}</b>。选好或建好后点「下一步」。</div>
          <button className="btn primary" style={{ marginTop: 16 }} onClick={() => setStep(1)}>下一步：配置模型 →</button>
        </div>
      )}

      {/* Step 1: LLM 配置 */}
      {step === 1 && (
        <div className="setup-card">
          <h3 className="psec">选择供应商</h3>
          <div className="provider-grid">
            {providers.map(p => (
              <button key={p.id} className={`provider-chip ${cfg.provider === p.id ? 'active' : ''}`} onClick={() => pickProvider(p)}>
                <span className="p-label">{p.label}</span>
                {p.model && <span className="p-model">{p.model}</span>}
              </button>
            ))}
          </div>
          <h3 className="psec" style={{ marginTop: 20 }}>配置详情</h3>
          <label className="field-label">Base URL</label>
          <input className="field" value={cfg.base_url} onChange={e => setCfg({ ...cfg, base_url: e.target.value })} placeholder="https://api.deepseek.com/v1" />
          <label className="field-label">API Key</label>
          <input className="field" type="password" value={cfg.api_key} onChange={e => setCfg({ ...cfg, api_key: e.target.value })} placeholder="sk-..." />
          <label className="field-label">模型 {models.length > 0 && <span className="model-count">（{models.length} 个可选，也可手输）</span>}</label>
          <input className="field" value={cfg.model} onChange={e => setCfg({ ...cfg, model: e.target.value })} placeholder="deepseek-chat / glm-5.2 / kimi-k2.7-code…" list="modellist" />
          <datalist id="modellist">{models.map(m => <option key={m} value={m} />)}</datalist>
          <button className="btn" onClick={fetchModels} disabled={fetchingModels} style={{ marginTop: models.length > 0 ? 0 : -4, fontSize: 13 }}>
            {fetchingModels ? '⏳ 获取中…' : models.length > 0 ? '🔄 刷新模型列表' : '🔍 获取模型列表'}
          </button>
          {modelErr && <div className="test-msg fail" style={{ marginTop: 10 }}>{modelErr}</div>}
          <div className="inline-form" style={{ marginTop: 16 }}>
            <button className="btn" onClick={testCfg} disabled={testing || !cfg.api_key}>{testing ? '测试中…' : '🔍 测连通'}</button>
            <button className="btn primary" onClick={saveCfg}>保存并下一步 →</button>
          </div>
          {testMsg && <div className={`test-msg ${testMsg.ok ? 'ok' : 'fail'}`}>{testMsg.ok ? '✓ ' : '✗ '}{testMsg.msg}</div>}

          <h3 className="psec" style={{ marginTop: 24 }}>飞书知识库归档</h3>
          <div className="setup-hint">选择一个知识库空间，Agent 产出的笔记/复习卡/周报会自动归档到这里。</div>
          {spaceErr && <div className="test-msg fail" style={{ marginTop: 8 }}>{spaceErr}（请先执行 lark-cli auth login）</div>}
          <select className="field" value={curSpace || ''} onChange={e => onPickSpace(e.target.value)} disabled={spaceBusy} style={{ marginTop: 8 }}>
            <option value="">不归档（仅生成单篇文档）</option>
            {spaces.map(s => <option key={s.space_id} value={s.space_id}>{s.name}</option>)}
          </select>
        </div>
      )}

      {/* Step 2: 生成树 */}
      {step === 2 && (
        <div className="setup-card">
          <h3 className="psec">描述你的目标岗位 / 粘贴 JD</h3>
          <textarea className="field ta" value={jd} onChange={e => setJd(e.target.value)} rows={8}
            placeholder="例：我想投推荐算法实习，需要学召回、精排、大模型推荐… 或直接粘贴招聘JD" />
          <div className="inline-form" style={{ marginTop: 12 }}>
            <button className="btn primary" onClick={generate} disabled={generating || !jd.trim()}>
              {generating ? '⏳ 生成中（模型可能需 30-60 秒）…' : '✨ AI 生成技能树'}
            </button>
          </div>
          {genResult && (
            <div className="gen-preview">
              <h3 className="psec">✅ 生成预览（{genResult.trees.length} 个方向）</h3>
              {genResult.trees.map((t, i) => (
                <div key={i} className="gen-tree">
                  <b>{t.icon} {t.title}</b> — {t.subtitle}
                  <span className="gen-count">{t.branches.reduce((a: number, b: any) => a + b.nodes.length, 0)} 节点</span>
                </div>
              ))}
              <button className="btn primary" style={{ marginTop: 14 }} onClick={apply}>确认写入，进入技能树 →</button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
