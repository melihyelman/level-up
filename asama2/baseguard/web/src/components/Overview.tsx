import { useMemo, useState } from 'react'
import type { Action, Overview as OverviewData, FrameSummary } from '../lib/api'
import { ACTION_LABEL, ACTION_TONE, actionRank, km, zoneName } from '../lib/format'
import TacticalMap from './TacticalMap'

const toMin = (t: string) => +t.slice(0, 2) * 60 + +t.slice(3)
const T0 = 10 * 60
const T1 = 16 * 60

const color = (f: FrameSummary) => (f.assessment ? `var(--${ACTION_TONE[f.assessment.action]})` : 'var(--pending)')

export default function Overview({ data, onOpen }: { data: OverviewData; onOpen: (id: string) => void }) {
  const [hover, setHover] = useState<string | null>(null)
  const [filter, setFilter] = useState<Action | 'all'>('hemen teyit/müdahale')

  const queue = useMemo(
    () =>
      data.frames
        .filter((f) => filter === 'all' || f.assessment?.action === filter)
        .sort((a, b) => actionRank(a.assessment?.action) - actionRank(b.assessment?.action) || a.time.localeCompare(b.time)),
    [data, filter],
  )
  const counts = {
    'hemen teyit/müdahale': data.stats.urgent_frames,
    'izlemeye al': data.stats.watch_frames,
  }

  return (
    <div className="overview">
      <div className="overview-main">
        <div className="section-head">
          <h2>Günlük durum</h2>
          <span className="muted">{data.frames.length} kare · 10:10–15:50 · tüm kareler ajan tarafından değerlendirildi</span>
        </div>
        <TacticalMap overview={data} hover={hover} onHover={setHover} onOpen={onOpen} />
        <div className="timeline">
          <span className="eyebrow">Zaman çizelgesi</span>
          <div className="timeline-track">
            <div className="timeline-axis" />
            {[10, 11, 12, 13, 14, 15, 16].map((h) => (
              <span key={h} className="timeline-tick" style={{ left: `${((h * 60 - T0) / (T1 - T0)) * 100}%` }}>{h}:00</span>
            ))}
            {data.frames.map((f) => (
              <button
                key={f.id}
                className={`timeline-mark ${hover === f.id ? 'on' : ''}`}
                title={`${f.time} · ${zoneName(f.zone)}`}
                style={{ left: `${((toMin(f.time) - T0) / (T1 - T0)) * 100}%`, background: color(f) }}
                onMouseEnter={() => setHover(f.id)}
                onMouseLeave={() => setHover(null)}
                onClick={() => onOpen(f.id)}
              />
            ))}
          </div>
        </div>
      </div>

      <aside className="queue">
        <div className="queue-head">
          <h2>Öncelik kuyruğu</h2>
          <div className="muted" style={{ fontSize: 15 }}>Ajanın önerdiği eyleme göre sıralı. Bir kareyi açmak için tıklayın.</div>
          <div className="queue-filters">
            {(['hemen teyit/müdahale', 'izlemeye al', 'all'] as const).map((k) => (
              <button key={k} className={`chip ${filter === k ? 'on' : ''}`} onClick={() => setFilter(k)}>
                {k === 'all' ? `Tümü ${data.frames.length}` : `${ACTION_LABEL[k]} ${counts[k]}`}
              </button>
            ))}
          </div>
        </div>
        <div className="queue-list">
          {queue.map((f) => (
            <button
              key={f.id}
              className={`qcard ${hover === f.id ? 'hover' : ''}`}
              onMouseEnter={() => setHover(f.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onOpen(f.id)}
            >
              <span className="bar" style={{ background: color(f) }} />
              <span>
                <span className="qcard-top">
                  <span className="mono">{f.time}</span>
                  <span>{zoneName(f.zone)}</span>
                  <span className="faint">· üsse {km(f.dist_to_base_m)}</span>
                  {f.assessment && <span className={`pill ${ACTION_TONE[f.assessment.action]}`} style={{ marginLeft: 'auto' }}>{ACTION_LABEL[f.assessment.action]}</span>}
                </span>
                <span className="qcard-title">{f.assessment?.headline ?? 'Henüz değerlendirilmedi.'}</span>
                {f.assessment && (
                  <span className="qcard-meta">
                    <span>{f.assessment.urgent} müdahale</span>
                    <span>{f.assessment.watch} izle</span>
                    {f.assessment.contradicted > 0 && <span style={{ color: 'var(--urgent)' }}>{f.assessment.contradicted} çelişkili rapor</span>}
                    <span>{f.id}</span>
                  </span>
                )}
              </span>
            </button>
          ))}
          {queue.length === 0 && <div className="empty">Bu filtrede kare yok.</div>}
        </div>
      </aside>
    </div>
  )
}
