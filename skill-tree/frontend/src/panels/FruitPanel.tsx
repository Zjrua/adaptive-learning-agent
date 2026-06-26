import type { Fruit } from '../types'

export function FruitPanel({ fruits }: { fruits: Fruit[] }) {
  return (
    <section className="panel active">
      <div className="panel-head">
        <h2 className="serif panel-title">🍎 果实 · 简历成品</h2>
        <p className="panel-sub">技能树结出的果实 · 点「打开 PDF」在新标签查看编译好的简历</p>
      </div>
      <div className="fcard-grid">
        {fruits.map(f => (
          <div className="fcard" key={f.id} style={{ ['--c' as any]: f.color }}>
            <div className="fcard-top">
              <span className="fico">{f.icon}</span>
              <span className={`fstatus ${f.has_pdf ? 'ok' : 'no'}`}>{f.has_pdf ? '已编译' : '未编译'}</span>
            </div>
            <div className="fname serif">{f.title}</div>
            <div className="fsub">{f.subtitle}</div>
            <div className="fbar"><i style={{ width: `${f.pct}%` }} /></div>
            <div className="fpct">技能掌握度 {f.pct}%</div>
            <div className="fbtns">
              {f.has_pdf
                ? <a className="fbtn primary" href={`/resume/build/${f.id}.pdf`} target="_blank" rel="noopener">📄 打开 PDF</a>
                : <span className="fbtn disabled">未编译</span>}
              <span className="fbtn">源码</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
