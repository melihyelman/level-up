import type { FrameDetail, Vehicle } from '../lib/api'
import { api } from '../lib/api'
import { ACTION_TONE, CLS_LABEL } from '../lib/format'

export interface Layers { boxes: boolean; weak: boolean; reports: boolean }

export const vehicleColor = (v: Vehicle) =>
  v.decision ? `var(--${ACTION_TONE[v.decision.action]})` : 'var(--pending)'

interface Props {
  detail: FrameDetail
  layers: Layers
  selected: string | null
  hover: string | null
  onSelect: (id: string) => void
  onHover: (id: string | null) => void
}

export default function ImageViewer({ detail, layers, selected, hover, onSelect, onHover }: Props) {
  const { info } = detail
  const W = info.width_px
  const H = info.height_px
  const u = W / 960 // scale labels with image resolution
  const focus = selected ?? hover
  const shown = detail.vehicles.filter((v) => layers.boxes && (layers.weak || v.required))

  return (
    <div className="viewer" style={{ aspectRatio: `${W} / ${H}`, width: `min(calc(100% - 40px), calc((100vh - 200px) * ${W / H}))` }}>
      <img src={api.imageUrl(info.image_id)} alt={`${info.image_id} drone görüntüsü`} width={W} height={H} />
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        {shown.map((v) => {
          const c = vehicleColor(v)
          const dim = focus && focus !== v.id
          const label = `${v.id}${v.cls ? ' · ' + (CLS_LABEL[v.cls] ?? v.cls) : ' · kayıt'}`
          const tw = label.length * 8.4 * u + 12 * u
          if (!v.box) {
            const [x, y] = v.center_px
            return (
              <g key={v.id} opacity={dim ? 0.35 : 1} onMouseEnter={() => onHover(v.id)} onMouseLeave={() => onHover(null)} onClick={() => onSelect(v.id)} style={{ cursor: 'pointer' }}>
                <circle cx={x} cy={y} r={16 * u} fill="transparent" stroke={c} strokeWidth={2} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
                <rect className="tag-bg" x={x + 18 * u} y={y - 29 * u} width={tw} height={21 * u} rx={3 * u} fill="rgba(11,12,14,.85)" />
                <text className="tag" x={x + 23 * u} y={y - 13 * u} fill={c} style={{ fontSize: 16 * u }}>{label}</text>
              </g>
            )
          }
          const [x, y, w, h] = v.box
          const weak = (v.conf ?? 1) < 0.3
          const ty = y - 25 * u < 0 ? y + h + 4 * u : y - 25 * u
          return (
            <g key={v.id} opacity={dim ? 0.35 : 1} onMouseEnter={() => onHover(v.id)} onMouseLeave={() => onHover(null)} onClick={() => onSelect(v.id)}>
              <rect className={`box ${weak ? 'weak' : ''} ${selected === v.id ? 'sel' : ''}`} x={x} y={y} width={w} height={h} stroke={c} rx={2 * u} />
              <rect className="tag-bg" x={x} y={ty} width={tw} height={21 * u} rx={3 * u} fill="rgba(11,12,14,.85)" />
              <text className="tag" x={x + 5 * u} y={ty + 15 * u} fill={c} style={{ fontSize: 16 * u }}>{label}</text>
            </g>
          )
        })}
        {layers.reports && detail.reports.filter((r) => r.point_px && r.dist_point_to_frame_m === 0).map((r) => {
          const [x, y] = r.point_px!
          const s = 9 * u
          return (
            <g key={r.rid} pointerEvents="none">
              <path className="rpin" d={`M${x - s},${y - s} L${x + s},${y + s} M${x - s},${y + s} L${x + s},${y - s}`} />
              <text x={x + s + 3 * u} y={y + s + 10 * u} fill="var(--report)" style={{ font: `500 ${13 * u}px var(--mono)` }}>{r.rid}</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
