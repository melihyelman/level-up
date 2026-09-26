import { useEffect, useRef } from 'react'
import type { FrameDetail, Vehicle } from '../lib/api'
import { api } from '../lib/api'
import { ACTION_LABEL, ACTION_TONE, CLS_LABEL, actionRank, km, num } from '../lib/format'
import { vehicleColor } from './ImageViewer'
import TrackRadar from './TrackRadar'

interface Props {
  detail: FrameDetail
  selected: string | null
  hover: string | null
  showWeak: boolean
  onSelect: (id: string | null) => void
  onHover: (id: string | null) => void
}

export default function VehiclesPanel({ detail, selected, hover, showWeak, onSelect, onHover }: Props) {
  const list = detail.vehicles
    .filter((v) => showWeak || v.required)
    .sort((a, b) => actionRank(a.decision?.action) - actionRank(b.decision?.action)
      || (a.decision?.confidence === 'düşük' ? 1 : 0) - (b.decision?.confidence === 'düşük' ? 1 : 0)
      || a.dist_to_base_m - b.dist_to_base_m)
  const refs = useRef<Record<string, HTMLDivElement | null>>({})
  useEffect(() => {
    if (selected) refs.current[selected]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selected])

  return (
    <div>
      {list.map((v) => (
        <div key={v.id} ref={(el) => { refs.current[v.id] = el }} className={`vrow ${selected === v.id || hover === v.id ? 'sel' : ''}`}>
          <button className="vrow-head" onClick={() => onSelect(selected === v.id ? null : v.id)}
            onMouseEnter={() => onHover(v.id)} onMouseLeave={() => onHover(null)}>
            <span className="bar" style={{ background: vehicleColor(v) }} />
            <span>
              <span className="vid">{v.id}</span>
              <div className="vsub">{v.cls ? CLS_LABEL[v.cls] ?? v.cls : 'sınıf yok'}</div>
            </span>
            <span className="vsub">
              {v.kind === 'track_only' ? 'Model görmedi · yalnız hareket kaydı' : `güven ${num(v.conf ?? 0, 2)}${v.track_id ? ` · ${v.track_id}` : ' · kayıt yok'}`}
              <div>üsse {km(v.dist_to_base_m)}{v.motion?.eta_to_base_min ? ` · varış ~${Math.round(v.motion.eta_to_base_min)} dk` : ''}</div>
            </span>
            {v.decision ? (
              <span style={{ textAlign: 'right' }}>
                <span className={`pill ${ACTION_TONE[v.decision.action]}`}>{ACTION_LABEL[v.decision.action]}</span>
                <div className="conf" style={{ marginTop: 4 }}>güven {v.decision.confidence}</div>
              </span>
            ) : <span className="pill pending">bekliyor</span>}
          </button>
          {selected === v.id && <VehicleBody v={v} detail={detail} />}
        </div>
      ))}
    </div>
  )
}

function VehicleBody({ v, detail }: { v: Vehicle; detail: FrameDetail }) {
  const m = v.motion
  const color = vehicleColor(v)
  return (
    <div className="vrow-body appear">
      {v.decision ? (
        <>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Ajanın gerekçesi</div>
          <p className="reason">{v.decision.reason}</p>
          {!!v.decision.evidence?.length && (
            <div className="evidence">{v.decision.evidence.map((e, i) => <span key={i}>{e}</span>)}</div>
          )}
        </>
      ) : <p className="reason muted">Ajan bu kareyi henüz değerlendirmedi.</p>}

      <div className="eyebrow" style={{ margin: '4px 0 8px' }}>Ölçümler</div>
      {m ? (
        <>
          <div className="metrics">
            <Metric v={km(m.start_dist_to_base_m)} l={`üsse ${m.start}`} />
            <Metric v={km(m.dist_to_base_now_m)} l={`üsse ${m.end}`} />
            <Metric v={km(m.min_dist_to_base_m)} l={`en yakın · ${m.min_dist_time}`} />
            <Metric v={`${num(m.speed_last_10m_ms)} m/s`} l="son 10 dk hız" />
            <Metric v={`${m.closing_rate_30m_ms > 0 ? '+' : ''}${num(m.closing_rate_30m_ms, 2)} m/s`} l="30 dk yaklaşma" />
            <Metric v={m.eta_to_base_min ? `${Math.round(m.eta_to_base_min)} dk` : '—'} l="tahmini varış" />
            <Metric v={`${Math.abs(m.base_sweep_deg)}°`} l="üs etrafında tarama" />
            <Metric v={`${m.stopped_minutes_total} dk`} l="toplam duraklama" />
            <Metric v={km(m.path_len_m)} l="2 saatlik yol" />
          </div>
          <div className="vis-row">
            <div style={{ flex: 1 }}><TrackRadar motion={m} base={detail.info.base} color={color} /></div>
          </div>
          {m.moving_together_with.length > 0 && (
            <div className="muted" style={{ fontSize: 14.5, marginBottom: 10 }}>
              Son 1 saatte yakın seyreden: {m.moving_together_with.map((c) => `${c.track_id} (ort. ${c.mean_sep_m} m)`).join(', ')}
            </div>
          )}
        </>
      ) : (
        <p className="muted" style={{ fontSize: 15 }}>Hareket kaydı yok. Görev tanımına göre park halindeki araçların kaydı olmayabilir.</p>
      )}
      <div className="vis-row">
        <img className="crop" src={api.cropUrl(detail.info.image_id, v.id)} alt={`${v.id} yakın plan`} />
        <div className="faint" style={{ fontSize: 14, lineHeight: 1.6 }}>
          {v.kind === 'detection' ? (
            <>Tespit {v.id} · {v.cls ? CLS_LABEL[v.cls] : ''} · güven {num(v.conf ?? 0, 2)}<br />
              {v.track_id ? <>Hareket kaydı {v.track_id} ile {num(v.match_dist_m ?? 0)} m mesafede eşleşti</> : 'Eşleşen hareket kaydı yok'}</>
          ) : <>Tespit modeli bu konumda araç bulamadı; konum {v.track_id} kaydının son noktasından.</>}
          <br />{v.lat.toFixed(5)}, {v.lon.toFixed(5)}
        </div>
      </div>
    </div>
  )
}

const Metric = ({ v, l }: { v: string; l: string }) => (
  <div className="metric"><b>{v}</b><span>{l}</span></div>
)
