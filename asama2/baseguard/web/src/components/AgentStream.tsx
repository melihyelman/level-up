import { useEffect, useRef, useState } from 'react'
import type { TraceEvent } from '../lib/api'
import { api, getTrace } from '../lib/api'
import { ACTION_LABEL, ACTION_TONE, CLS_LABEL, km, num, zoneName } from '../lib/format'

type Mode = 'static' | 'replay' | 'live'

interface Step {
  kind: TraceEvent['kind']
  title?: string
  detail?: unknown
  result?: string
}

const TOOL_TR: Record<string, string> = {
  get_image_info: 'Kareyi aç',
  detect_vehicles: 'Araçları tespit et',
  match_tracks: 'Hareket kayıtlarıyla eşleştir',
  get_motion: 'Hareketi çıkar',
  get_reports: 'Saha raporlarını getir',
  view_region: 'Yakından bak',
  get_track_points: 'Kaydın ham noktaları',
  search_reports: 'Rapor havuzunda ara',
}

function summarize(name: string, text?: string): string {
  if (!text) return '…'
  let d: any
  try { d = JSON.parse(text) } catch { return text.slice(0, 140) }
  if (d.error) return `Hata: ${d.error}`
  switch (name) {
    case 'get_image_info':
      return `${d.width_px}×${d.height_px} px · çekim ${d.capture_time} · ${zoneName(d.nearest_zone)} · üsse ${km(d.dist_to_base_m)} (${d.direction_from_base})`
    case 'detect_vehicles': {
      const strong = d.detections.filter((x: any) => x.conf >= 0.3)
      const by: Record<string, number> = {}
      strong.forEach((x: any) => { by[x.cls] = (by[x.cls] ?? 0) + 1 })
      const parts = Object.entries(by).map(([c, n]) => `${n} ${CLS_LABEL[c] ?? c}`).join(', ')
      return `${d.count} kutu · ${strong.length} güvenli (${parts || '—'}) · ${d.count - strong.length} zayıf`
    }
    case 'match_tracks':
      return `${d.matches.filter((m: any) => m.track_id).length} tespit kayıtla eşleşti · ${d.tracks_in_frame_without_detection.length} kayıt tespitsiz · ${d.tracks_just_outside_frame.length} kayıt kare dışında`
    case 'get_motion': {
      const one = (m: any) => `${m.track_id}: ${km(m.start_dist_to_base_m)} → ${km(m.dist_to_base_now_m)}, ${num(m.speed_last_10m_ms)} m/s${m.eta_to_base_min ? `, varış ~${Math.round(m.eta_to_base_min)} dk` : ''}`
      return d.motions ? `${d.motions.length} kayıt · ${d.motions.slice(0, 3).map(one).join(' · ')}${d.motions.length > 3 ? ' …' : ''}` : one(d)
    }
    case 'get_reports': {
      const c = d.reports.filter((r: any) => r.scope === 'koordinat').length
      return `${c} koordinatlı, ${d.reports.length - c} bölge raporu · iddialar ölçümlerle yan yana`
    }
    case 'get_track_points':
      return `${d.points.length} nokta`
    case 'search_reports':
      return `${d.count} rapor bulundu`
    default:
      return text.slice(0, 140)
  }
}

function toSteps(events: TraceEvent[]): Step[] {
  const steps: Step[] = []
  for (const e of events) {
    if (e.kind === 'tool_result') {
      const s = [...steps].reverse().find((x) => x.kind === 'tool_call' && x.title === e.title && x.result === undefined)
      if (s) { s.result = e.detail as string; continue }
    }
    if (e.kind === 'start' || e.kind === 'done') continue
    steps.push({ kind: e.kind, title: e.title, detail: e.detail })
  }
  return steps
}

interface Props { frameId: string; llm: boolean; onFinished: () => void }

export default function AgentStream({ frameId, llm, onFinished }: Props) {
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [mode, setMode] = useState<Mode>('static')
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [usage, setUsage] = useState<any>(null)
  const es = useRef<EventSource | null>(null)
  const end = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setMode('static'); setRunning(false); setUsage(null)
    getTrace(frameId).then(setEvents).catch(() => setEvents([]))
    return () => es.current?.close()
  }, [frameId])

  useEffect(() => {
    if (!running) return
    const t0 = Date.now()
    const id = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 500)
    return () => clearInterval(id)
  }, [running])

  useEffect(() => { if (running) end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }) }, [events, running])

  const start = (m: 'replay' | 'live') => {
    es.current?.close()
    setEvents([]); setMode(m); setRunning(true); setElapsed(0); setUsage(null)
    const src = new EventSource(api.streamUrl(frameId, m, 6))
    es.current = src
    src.onmessage = (msg) => {
      const ev: TraceEvent = JSON.parse(msg.data)
      if (ev.kind === 'done' || ev.kind === 'error') {
        src.close(); setRunning(false)
        if (ev.kind === 'done') { setUsage((ev as any).usage); if (m === 'live') onFinished() }
      }
      setEvents((prev) => [...prev, ev])
    }
    src.onerror = () => { src.close(); setRunning(false) }
  }

  const steps = toSteps(events)
  return (
    <div>
      <div className="stream-controls">
        <button className="btn" onClick={() => start('replay')} disabled={running}>Kayıttan oynat</button>
        <button className="btn btn-primary" onClick={() => start('live')} disabled={running || !llm}
          title={llm ? 'Ajanı bu kare için şimdi çalıştır (~2–4 dk)' : 'LLM anahtarı yok'}>Canlı çalıştır</button>
        <span style={{ marginLeft: 'auto' }}>
          {running && mode === 'live' && <span className="live">CANLI · {elapsed} sn</span>}
          {mode === 'replay' && <span className="replay-tag">KAYIT · 6× HIZ</span>}
          {mode === 'static' && steps.length > 0 && <span className="faint" style={{ fontSize: 14 }}>son çalıştırmanın kaydı</span>}
        </span>
      </div>
      <div className="stream">
        {steps.length === 0 && !running && <div className="empty" style={{ padding: '8px 0' }}>Bu kare için kayıt yok. Ajanı canlı çalıştırın.</div>}
        {steps.map((s, i) => <StepView key={i} s={s} frameId={frameId} />)}
        {running && <div className="step"><span className="step-dot" /><div className="step-sub">çalışıyor…</div></div>}
        {usage && (
          <div className="faint mono" style={{ fontSize: 13, marginTop: 6 }}>
            {usage.calls} LLM çağrısı · {usage.seconds} sn · {Math.round(usage.prompt_tokens / 1000)}k girdi · {Math.round(usage.reasoning_tokens / 1000)}k düşünme token'ı
          </div>
        )}
        <div ref={end} />
      </div>
    </div>
  )
}

function StepView({ s, frameId }: { s: Step; frameId: string }) {
  const [open, setOpen] = useState(false)
  if (s.kind === 'user')
    return <div className="step appear"><span className="step-dot" /><div className="step-title"><b>Görev</b></div><div className="step-sub">{String(s.detail)}</div></div>
  if (s.kind === 'say')
    return <div className="step appear"><span className="step-dot" /><div className="step-say">{String(s.detail)}</div></div>
  if (s.kind === 'thought')
    return (
      <div className="step appear"><span className="step-dot" />
        <div className="thought" onClick={() => setOpen(!open)}>{open ? '▾' : '▸'} Düşünce ({String(s.detail).length} karakter)</div>
        {open && <div className="thought"><pre>{String(s.detail)}</pre></div>}
      </div>
    )
  if (s.kind === 'tool_call') {
    const args = s.detail as Record<string, unknown>
    const argText = Object.entries(args ?? {}).filter(([k]) => k !== 'question')
      .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(', ') : v}`).join(' ')
    return (
      <div className="step tool appear"><span className="step-dot" />
        <div className="step-title"><b>{TOOL_TR[s.title!] ?? s.title}</b><span className="mono faint">{s.title}({argText})</span></div>
        <div className="step-sub">
          {s.title === 'view_region' ? (typeof args?.question === 'string' ? `Soru: ${args.question}` : 'Görsel kontrol') : summarize(s.title!, s.result)}
        </div>
        {s.title === 'view_region' && typeof args?.target === 'string' && (
          <img className="step-img" src={api.cropUrl(frameId, args.target)} alt={`${args.target} yakın plan`} />
        )}
      </div>
    )
  }
  if (s.kind === 'warn')
    return <div className="step warn appear"><span className="step-dot" /><div className="step-title"><b>Şema düzeltmesi</b></div><div className="step-sub">{String(s.detail)}</div></div>
  if (s.kind === 'audit') {
    const issues = (s.detail as string[]) ?? []
    return (
      <div className={`step audit ${issues.length ? 'fix' : ''} appear`}><span className="step-dot" />
        {issues.length > 0 && <ul className="step-sub" style={{ margin: '4px 0 0', paddingLeft: 18 }}>{issues.map((x, i) => <li key={i}>{x}</li>)}</ul>}
        {!issues.length && <div className="step-sub">Kapsam, kimlikler, "birlikte hareket" iddiaları ve sayılar araç çıktılarıyla tutarlı.</div>}
      </div>
    )
  }
  if (s.kind === 'final') {
    const b = s.detail as any
    return (
      <div className="step final appear"><span className="step-dot" />
        <div className="step-title"><b>Değerlendirme gönderildi</b><span className={`pill ${ACTION_TONE[b.action as keyof typeof ACTION_TONE]}`}>{ACTION_LABEL[b.action as keyof typeof ACTION_LABEL]}</span></div>
        <div className="step-sub">{b.headline}</div>
      </div>
    )
  }
  if (s.kind === 'error')
    return <div className="step warn appear"><span className="step-dot" /><div className="step-title"><b>Hata</b></div><div className="step-sub">{String(s.detail)}</div></div>
  return null
}
