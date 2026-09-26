import { useCallback, useEffect, useState } from 'react'
import type { Overview as OverviewData } from './lib/api'
import { api } from './lib/api'
import FrameView from './components/FrameView'
import Overview from './components/Overview'

const frameFromHash = () => (location.hash.match(/^#\/kare\/(img_\d+)/) || [])[1] ?? null

export default function App() {
  const [data, setData] = useState<OverviewData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [frame, setFrame] = useState<string | null>(frameFromHash())

  const load = useCallback(() => api.overview().then(setData).catch((e) => setError(String(e))), [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    const on = () => setFrame(frameFromHash())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])

  const open = (id: string | null) => { location.hash = id ? `#/kare/${id}` : '' }
  const nav = useCallback((d: number) => {
    if (!data || !frame) return
    const i = data.frames.findIndex((f) => f.id === frame)
    const next = data.frames[(i + d + data.frames.length) % data.frames.length]
    location.hash = `#/kare/${next.id}`
  }, [data, frame])

  if (error) return <div className="loading">API'ye ulaşılamadı ({error}). Backend çalışıyor mu? <span className="mono">uvicorn server.api:app --port 8000</span></div>
  if (!data) return <div className="loading">Yükleniyor…</div>
  const s = data.stats

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand btn-ghost" style={{ border: 0, background: 'none', cursor: 'pointer', padding: 0 }} onClick={() => open(null)}>
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden>
            <circle cx="16" cy="16" r="13" fill="none" stroke="var(--ink)" strokeWidth="1.5" opacity=".45" />
            <circle cx="16" cy="16" r="7" fill="none" stroke="var(--ink)" strokeWidth="1.5" />
            <path d="M16 16 L26 8" stroke="var(--urgent)" strokeWidth="2" strokeLinecap="round" />
            <circle cx="16" cy="16" r="2.2" fill="var(--ink)" />
          </svg>
          <span className="brand-name">BaseGuard</span>
          <span className="brand-sub">Merkez Üs · çevre gözetimi</span>
        </button>
        <div className="topbar-stats">
          <span className="stat"><b>{s.frames}</b><span>kare</span></span>
          <span className="stat"><i className="dot" style={{ background: 'var(--urgent)' }} /><b>{s.urgent_frames}</b><span>müdahale</span></span>
          <span className="stat"><i className="dot" style={{ background: 'var(--watch)' }} /><b>{s.watch_frames}</b><span>izle</span></span>
          <span className="stat"><b>{s.contradicted_reports}</b><span>çelişkili rapor</span></span>
          <span className="status-live">
            <i className="dot" style={{ background: data.llm.available ? 'var(--good)' : 'var(--ink-3)' }} />
            {data.llm.available ? `Ajan hazır · ${data.llm.model}` : 'Ajan çevrimdışı · yalnız kayıt'}
          </span>
        </div>
      </header>
      {frame
        ? <FrameView id={frame} overview={data} onBack={() => open(null)} onNav={nav} onChanged={load} />
        : <Overview data={data} onOpen={(id) => open(id)} />}
    </div>
  )
}
