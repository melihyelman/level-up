import { useMemo, useState } from 'react'
import type { Overview, FrameSummary } from '../lib/api'
import { ACTION_LABEL, ACTION_TONE, km, toLocal, zoneName } from '../lib/format'

const EXTENT = 6800 // metres from the base shown in each direction
const RINGS = [1000, 2000, 4000, 6000]

const toneColor = (f: FrameSummary) =>
  f.assessment ? `var(--${ACTION_TONE[f.assessment.action]})` : 'var(--pending)'

interface Props {
  overview: Overview
  hover: string | null
  onHover: (id: string | null) => void
  onOpen: (id: string) => void
}

export default function TacticalMap({ overview, hover, onHover, onOpen }: Props) {
  const { base } = overview
  const [tip, setTip] = useState<{ f: FrameSummary; x: number; y: number } | null>(null)
  const pts = useMemo(
    () => overview.frames.map((f) => ({ f, p: toLocal(f.center[0], f.center[1], base.lat, base.lon) })),
    [overview, base],
  )
  // draw urgent last so they sit on top
  const order = [...pts].sort((a, b) => rank(b.f) - rank(a.f))

  return (
    <div className="map-wrap" onMouseLeave={() => { setTip(null); onHover(null) }}>
      <svg className="map" viewBox={`${-EXTENT} ${-EXTENT} ${EXTENT * 2} ${EXTENT * 2}`} preserveAspectRatio="xMidYMid meet">
        {RINGS.map((r) => (
          <g key={r}>
            <circle className="ring" cx={0} cy={0} r={r} />
            <text className="ring-label" x={80} y={-r - 90} style={{ fontSize: 240 }}>{r / 1000} km</text>
          </g>
        ))}
        <line className="axis" x1={0} y1={-EXTENT} x2={0} y2={EXTENT} />
        <line className="axis" x1={-EXTENT} y1={0} x2={EXTENT} y2={0} />
        <text x={40} y={-EXTENT + 220} fill="var(--ink-3)" style={{ font: '500 260px var(--mono)' }}>K</text>

        {overview.zones.map((z) => {
          const [x, y] = toLocal(z.lat, z.lon, base.lat, base.lon)
          return (
            <g key={z.name}>
              <circle className="zone-dot" cx={x} cy={-y} r={45} />
              <text className="zone-label" x={x} y={-y - 140} textAnchor="middle" style={{ fontSize: 270 }}>
                {zoneName(z.name)}
              </text>
            </g>
          )
        })}

        {order.map(({ f, p }) => {
          const on = hover === f.id
          const urgent = f.assessment?.action === 'hemen teyit/müdahale'
          const r = urgent ? 125 : 95
          return (
            <g
              key={f.id}
              className="frame"
              onMouseEnter={(e) => {
                onHover(f.id)
                const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
                const c = (e.currentTarget as SVGGElement).getBoundingClientRect()
                setTip({ f, x: c.left - box.left + c.width / 2, y: c.top - box.top })
              }}
              onClick={() => onOpen(f.id)}
            >
              {(urgent || on) && (
                <circle className="frame-halo" cx={p[0]} cy={-p[1]} r={r + 110} stroke={toneColor(f)} opacity={on ? 0.9 : 0.35} strokeWidth={22} />
              )}
              <circle cx={p[0]} cy={-p[1]} r={on ? r + 35 : r} fill={toneColor(f)} stroke="var(--bg)" strokeWidth={30} />
            </g>
          )
        })}

        <g>
          <rect x={-150} y={-150} width={300} height={300} fill="var(--bg)" stroke="var(--ink)" strokeWidth={28} />
          <circle cx={0} cy={0} r={50} fill="var(--ink)" />
          <text x={0} y={420} textAnchor="middle" fill="var(--ink)" style={{ font: '600 280px var(--sans)' }}>{zoneName(base.name)}</text>
        </g>
      </svg>

      {tip && (
        <div className="map-tip" style={{ left: Math.min(tip.x + 14, 9999), top: tip.y - 8, transform: 'translateY(-100%)' }}>
          <div className="row">
            <span className="mono">{tip.f.time}</span>
            <span className="muted">{zoneName(tip.f.zone)} · üsse {km(tip.f.dist_to_base_m)}</span>
          </div>
          {tip.f.assessment ? (
            <>
              <div className="row"><span className={`pill ${ACTION_TONE[tip.f.assessment.action]}`}>{ACTION_LABEL[tip.f.assessment.action]}</span></div>
              <div>{tip.f.assessment.headline}</div>
            </>
          ) : (
            <span className="pill pending">Değerlendirilmedi</span>
          )}
        </div>
      )}

      <div className="map-legend">
        <span><i className="dot" style={{ background: 'var(--urgent)' }} /> Müdahale</span>
        <span><i className="dot" style={{ background: 'var(--watch)' }} /> İzle</span>
        <span><i className="dot" style={{ background: 'var(--clear)' }} /> İşlem yok</span>
        <span><i className="dot" style={{ background: 'var(--pending)' }} /> Değerlendirilmedi</span>
        <span className="faint">Merkez: üs · halkalar 1 · 2 · 4 · 6 km</span>
      </div>
    </div>
  )
}

function rank(f: FrameSummary) {
  const a = f.assessment?.action
  return a === 'hemen teyit/müdahale' ? 0 : a === 'izlemeye al' ? 1 : a ? 2 : 3
}
