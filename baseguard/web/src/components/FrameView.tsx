import { useCallback, useEffect, useState } from 'react'
import type { FrameDetail, Overview } from '../lib/api'
import { api } from '../lib/api'
import { ACTION_LABEL, ACTION_TONE, km, zoneName } from '../lib/format'
import AgentStream from './AgentStream'
import ChatPanel from './ChatPanel'
import ImageViewer, { type Layers } from './ImageViewer'
import ReportsPanel from './ReportsPanel'
import VehiclesPanel from './VehiclesPanel'

type Tab = 'vehicles' | 'reports' | 'agent' | 'chat'

interface Props {
  id: string
  overview: Overview
  onBack: () => void
  onNav: (delta: number) => void
  onChanged: () => void
}

export default function FrameView({ id, overview, onBack, onNav, onChanged }: Props) {
  const [detail, setDetail] = useState<FrameDetail | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  const [layers, setLayers] = useState<Layers>({ boxes: true, weak: false, reports: true })
  const [tab, setTab] = useState<Tab>('vehicles')

  const load = useCallback(() => api.frame(id).then(setDetail), [id])
  useEffect(() => { setDetail(null); setSelected(null); load() }, [id, load])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === 'INPUT') return
      if (e.key === 'ArrowRight') onNav(1)
      else if (e.key === 'ArrowLeft') onNav(-1)
      else if (e.key === 'Escape') selected ? setSelected(null) : onBack()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onNav, onBack, selected])

  const idx = overview.frames.findIndex((f) => f.id === id)
  if (!detail) return <div className="loading">Kare yükleniyor…</div>
  const { info, assessment } = detail
  const b = assessment?.brief
  const select = (v: string | null) => { setSelected(v); if (v) setTab('vehicles') }
  const nReq = detail.vehicles.filter((v) => v.required).length
  const nCoord = detail.reports.filter((r) => r.scope === 'koordinat').length
  const nBad = detail.reports.filter((r) => r.agent?.verdict === 'tespitle çelişiyor').length

  return (
    <div className="frame-view">
      <div className="frame-main">
        <div className="frame-head">
          <button className="btn btn-ghost" onClick={onBack}>← Genel durum</button>
          <span className="sep" />
          <h1>{info.capture_time} · {zoneName(info.nearest_zone)}</h1>
          <span className="muted" style={{ fontSize: 15 }}>
            üssün {info.direction_from_base}sunda {km(info.dist_to_base_m)} · {info.footprint_m[0]}×{info.footprint_m[1]} m · <span className="mono">{info.image_id}</span>
          </span>
          <span className="spacer" />
          <span className="faint mono" style={{ fontSize: 14 }}>{idx + 1}/{overview.frames.length}</span>
          <button className="btn btn-ghost" onClick={() => onNav(-1)} title="Önceki kare">← <span className="kbd">←</span></button>
          <button className="btn btn-ghost" onClick={() => onNav(1)} title="Sonraki kare"><span className="kbd">→</span> →</button>
        </div>

        <div className="viewer-tools">
          <button className={`toggle ${layers.boxes ? 'on' : ''}`} onClick={() => setLayers({ ...layers, boxes: !layers.boxes })}>Araçlar</button>
          <button className={`toggle ${layers.weak ? 'on' : ''}`} onClick={() => setLayers({ ...layers, weak: !layers.weak })}>Zayıf tespitler</button>
          <button className={`toggle ${layers.reports ? 'on' : ''}`} onClick={() => setLayers({ ...layers, reports: !layers.reports })}>Rapor noktaları</button>
          <span className="viewer-hint">Bir araca tıklayın · kesikli = düşük güven · daire = model görmedi, yalnız hareket kaydı</span>
        </div>
        <ImageViewer detail={detail} layers={layers} selected={selected} hover={hover} onSelect={select} onHover={setHover} />

        <section className="brief">
          {b ? (
            <>
              <div className="brief-top">
                <span className="eyebrow">Ajanın değerlendirmesi</span>
                <span className={`pill ${ACTION_TONE[b.action]}`}>{ACTION_LABEL[b.action]}</span>
              </div>
              <h3>{b.headline}</h3>
              <p>{b.brief}</p>
              {b.uncertainties.length > 0 && (
                <div className="uncertain">
                  <span className="eyebrow">Belirsizlikler</span>
                  <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{b.uncertainties.map((u, i) => <li key={i}>{u}</li>)}</ul>
                </div>
              )}
              <div className="brief-foot">
                <span>{assessment!.steps} araç çağrısı</span>
                <span>{assessment!.usage.calls} LLM turu · {Math.round(assessment!.usage.seconds)} sn</span>
                <span>{assessment!.model} · düşünme {assessment!.effort}</span>
              </div>
              {b.audit.map((a, i) => <div key={i} className="pill mixed" style={{ marginTop: 8 }}>{a}</div>)}
            </>
          ) : (
            <p className="brief-empty">Bu kare henüz ajan tarafından değerlendirilmedi. Sağdaki <b>Ajan akışı</b> sekmesinden canlı çalıştırabilirsiniz.</p>
          )}
        </section>
      </div>

      <aside className="side">
        <div className="tabs">
          <button className={`tab ${tab === 'vehicles' ? 'on' : ''}`} onClick={() => setTab('vehicles')}>Araçlar <span className="count">{nReq}</span></button>
          <button className={`tab ${tab === 'reports' ? 'on' : ''}`} onClick={() => setTab('reports')}>
            Raporlar <span className="count">{nCoord}</span>{nBad > 0 && <i className="dot" style={{ background: 'var(--urgent)' }} />}
          </button>
          <button className={`tab ${tab === 'agent' ? 'on' : ''}`} onClick={() => setTab('agent')}>Ajan akışı</button>
          <button className={`tab ${tab === 'chat' ? 'on' : ''}`} onClick={() => setTab('chat')}>Soru sor</button>
        </div>
        <div className="side-body">
          {tab === 'vehicles' && <VehiclesPanel detail={detail} selected={selected} hover={hover} showWeak={layers.weak} onSelect={setSelected} onHover={setHover} />}
          {tab === 'reports' && <ReportsPanel reports={detail.reports} />}
          {tab === 'agent' && <AgentStream frameId={id} llm={overview.llm.available} onFinished={() => { load(); onChanged() }} />}
          {tab === 'chat' && <ChatPanel detail={detail} />}
        </div>
      </aside>
    </div>
  )
}
