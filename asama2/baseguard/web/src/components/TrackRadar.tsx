import type { Motion } from '../lib/api'
import { toLocal } from '../lib/format'

// A track drawn around the base: rings in km, start (hollow), long stops, current position with heading.
export default function TrackRadar({ motion, base, color }: { motion: Motion; base: { lat: number; lon: number }; color: string }) {
  const pts = motion.polyline.map(([t, la, lo]) => ({ t, p: toLocal(la, lo, base.lat, base.lon) }))
  const maxR = Math.max(...pts.map(({ p }) => Math.hypot(p[0], p[1])), 1000) * 1.12
  const rings = [1000, 2000, 4000, 6000, 8000].filter((r) => r < maxR)
  const S = 200 // half-size of the viewBox
  const k = S / maxR
  const xy = (p: [number, number]) => [p[0] * k, -p[1] * k] as const
  const path = pts.map(({ p }, i) => `${i ? 'L' : 'M'}${xy(p)[0].toFixed(1)},${xy(p)[1].toFixed(1)}`).join(' ')
  const [cx, cy] = xy(pts[pts.length - 1].p)
  const [sx, sy] = xy(pts[0].p)
  const prev = pts.slice(0, -1).reverse().find(({ p }) => Math.hypot(p[0] - pts[pts.length - 1].p[0], p[1] - pts[pts.length - 1].p[1]) > 40)
  const ang = prev ? Math.atan2(cy - xy(prev.p)[1], cx - xy(prev.p)[0]) : null

  return (
    <svg className="radar" viewBox={`${-S} ${-S} ${2 * S} ${2 * S}`} role="img" aria-label={`${motion.track_id} hareket izi`}>
      {rings.map((r) => (
        <g key={r}>
          <circle className="ring" r={r * k} />
          <text className="ring-label" x={r * k * 0.707 + 3} y={-r * k * 0.707 - 3}>{r / 1000} km</text>
        </g>
      ))}
      <text className="ring-label" x={3} y={-S + 12}>K</text>
      <path d={path} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" opacity={0.9} />
      {pts.map(({ p, t }) => {
        const [x, y] = xy(p)
        return <circle key={t} cx={x} cy={y} r={1.6} fill={color} opacity={0.6} />
      })}
      {motion.stops.filter((s) => s.minutes >= 20).map((s) => {
        const at = pts.find(({ t }) => t === s.start)
        if (!at) return null
        const [x, y] = xy(at.p)
        return (
          <g key={s.start}>
            <circle cx={x} cy={y} r={5} fill="none" stroke="var(--ink-3)" strokeWidth={1.2} />
            <text x={x + 7} y={y + 3} fill="var(--ink-3)" style={{ font: '12px var(--mono)' }}>{s.start} · {s.minutes} dk</text>
          </g>
        )
      })}
      <circle cx={sx} cy={sy} r={4} fill="var(--bg)" stroke={color} strokeWidth={1.5} />
      <text x={sx + 7} y={sy - 6} fill="var(--ink-3)" style={{ font: '12px var(--mono)' }}>{motion.start}</text>
      {ang !== null && (
        <path d="M0,-5 L10,0 L0,5 Z" fill={color} transform={`translate(${cx},${cy}) rotate(${(ang * 180) / Math.PI}) translate(6,0)`} />
      )}
      <circle cx={cx} cy={cy} r={5} fill={color} stroke="var(--bg)" strokeWidth={2} />
      <text x={cx + 8} y={cy + 14} fill="var(--ink)" style={{ font: '500 13px var(--mono)' }}>{motion.end}</text>
      <rect x={-6} y={-6} width={12} height={12} fill="var(--bg)" stroke="var(--ink)" strokeWidth={1.5} />
      <circle r={2} fill="var(--ink)" />
      <text y={20} textAnchor="middle" fill="var(--ink-2)" style={{ font: '500 12px var(--mono)' }}>ÜS</text>
    </svg>
  )
}
