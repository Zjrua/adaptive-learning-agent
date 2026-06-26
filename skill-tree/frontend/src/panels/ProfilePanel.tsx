import type { Profile } from '../types'

export function ProfilePanel({ profile }: { profile: Profile | null }) {
  if (!profile) return <div className="panel active"><p className="panel-sub">加载中…</p></div>
  const c = profile.contact
  return (
    <section className="panel active">
      <div className="panel-head">
        <h2 className="serif panel-title">{profile.name} {profile.name_en && <span className="name-en">{profile.name_en}</span>}</h2>
        <p className="panel-sub">{profile.tagline}</p>
        <div className="contact-row">
          {c.email && <span className="ci">✉ <a href={`mailto:${c.email}`}>{c.email}</a></span>}
          {c.phone && <span className="ci">☎ {c.phone}</span>}
          {c.github && <span className="ci">⌥ <a href={c.github_url ?? '#'} target="_blank" rel="noopener">{c.github}</a></span>}
        </div>
      </div>
      <div className="pgrid">
        <div className="pcol">
          <h3 className="psec">教育背景</h3>
          {profile.education.map((e, i) => (
            <div className="edu-item" key={i}>
              <div className="edu-main">
                <span className="edu-school">{e.school}</span>
                <span className="edu-degree">{e.degree} · {e.major}</span>
              </div>
              <span className="edu-period">{e.period}</span>
            </div>
          ))}
          <h3 className="psec">技能</h3>
          {profile.skills.map((s, i) => (
            <div className="skill-row" key={i}>
              <span className="skill-group">{s.group}</span>
              <div className="chips">{s.items.map((it, j) => <span className="chip" key={j}>{it}</span>)}</div>
            </div>
          ))}
        </div>
        <div className="pcol">
          <h3 className="psec">项目经历</h3>
          {profile.experience.map((x, i) => (
            <div className="exp-card" key={i}>
              <div className="exp-head">
                <div>
                  <div className="exp-title">{x.title}</div>
                  <div className="exp-role">{x.role}</div>
                </div>
                <span className="exp-period">{x.period}</span>
              </div>
              {x.tech && <div className="chips">{x.tech.map((t, j) => <span className="chip sm" key={j}>{t}</span>)}</div>}
              {x.desc && <p className="exp-desc">{x.desc}</p>}
              {x.highlights && (
                <ul className="exp-hl">{x.highlights.map((h, j) => <li key={j}>{h}</li>)}</ul>
              )}
              {x.url && <a className="exp-link" href={x.url} target="_blank" rel="noopener">GitHub ↗</a>}
            </div>
          ))}
        </div>
      </div>
      <div className="pgrid">
        <div className="pcol">
          <h3 className="psec">竞赛获奖</h3>
          {profile.awards.map((a, i) => (
            <div className="award-item" key={i}>
              <span className="award-year">{a.year}</span>
              <span className="award-title">{a.title}{a.note && <span className="award-note"> {a.note}</span>}</span>
            </div>
          ))}
        </div>
        <div className="pcol">
          <h3 className="psec">学生工作</h3>
          <ul className="lead-list">{(profile.leadership ?? []).map((l, i) => <li key={i}>{l}</li>)}</ul>
        </div>
      </div>
    </section>
  )
}
