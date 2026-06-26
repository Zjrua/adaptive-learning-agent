import type { Template } from '../types'

export function TemplatesPanel({ templates }: { templates: Template[] }) {
  return (
    <section className="panel active">
      <div className="panel-head">
        <h2 className="serif panel-title">简历模板</h2>
        <p className="panel-sub">{templates.length} 套 LaTeX 模板</p>
      </div>
      <div className="tcard-grid">
        {templates.map(t => (
          <a className="tcard" key={t.id} href={`/projects/../resume/templates/${t.id}/`} target="_blank" rel="noopener"
             onClick={e => { e.preventDefault(); alert('模板源码在 resume/templates/' + t.id + '/') }}>
            <div className="tcard-top">
              <span className="tname serif">{t.name}</span>
              {t.star && <span className="tstar">★ 当前在用</span>}
            </div>
            <div className="tmeta"><span>{t.style}</span><span>·</span><span>{t.lang}</span></div>
            <div className="tscene">{t.scene}</div>
            <div className="tcard-cta">查看模板 →</div>
          </a>
        ))}
      </div>
    </section>
  )
}
