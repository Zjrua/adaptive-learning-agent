import type { Achievement as Ach } from './types'

export function Achievement({ achievements }: { achievements: Ach[] }) {
  return (
    <div className="block">
      <div className="section-title">
        <h2 className="serif">成就花田</h2>
        <span className="hint">每完成一组目标，便绽放一朵</span>
      </div>
      <div className="bloom-grid">
        {achievements.map((a, i) => (
          <div key={i} className={`bloom ${a.unlocked ? 'unlocked' : ''}`} title={a.def.desc}>
            <span className="petal">{a.def.icon}</span>
            <span className="meta">
              <span className="n">{a.def.name}</span>
              <span className="d">{a.def.desc}</span>
            </span>
            <span className={`tier tier-${a.def.tier}`}>{a.def.tier}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
