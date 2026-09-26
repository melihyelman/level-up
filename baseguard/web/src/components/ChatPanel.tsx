import { useEffect, useRef, useState } from 'react'
import type { FrameDetail } from '../lib/api'
import { api } from '../lib/api'

interface Msg { role: 'user' | 'assistant'; content: string; tools?: string[] }

export default function ChatPanel({ detail }: { detail: FrameDetail }) {
  const id = detail.info.image_id
  const [log, setLog] = useState<Msg[]>([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement | null>(null)
  useEffect(() => { setLog([]) }, [id])
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [log, busy])

  const top = detail.assessment?.brief.vehicles[0]
  const contradicted = detail.reports.find((r) => r.agent?.verdict === 'tespitle çelişiyor')
  const suggestions = [
    top && `${top.id} için neden “${top.action}” dedin?`,
    contradicted ? `${contradicted.rid} raporuna neden güvenmiyorsun?` : 'Hangi rapora güvenmemeliyiz?',
    'Bu karede en belirsiz nokta ne?',
  ].filter(Boolean) as string[]

  const ask = async (text: string) => {
    if (!text.trim() || busy) return
    const history = log.map(({ role, content }) => ({ role, content }))
    setLog((l) => [...l, { role: 'user', content: text }]); setQ(''); setBusy(true)
    try {
      const r = await api.chat(id, text, history)
      setLog((l) => [...l, { role: 'assistant', content: r.answer, tools: r.tools }])
    } catch (e) {
      setLog((l) => [...l, { role: 'assistant', content: `Cevap alınamadı: ${(e as Error).message}` }])
    } finally { setBusy(false) }
  }

  if (!detail.assessment) return <div className="empty">Soru sormak için önce ajanı bu kare için çalıştırın.</div>
  return (
    <div className="chat">
      <div className="chat-log">
        {log.length === 0 && (
          <div className="empty" style={{ padding: 0 }}>
            Ajana bu kareyle ilgili soru sorun. Önceki değerlendirmesine ve araçlarına dayanarak, kaynak göstererek cevaplar.
          </div>
        )}
        {log.map((m, i) => (
          <div key={i} className={`msg ${m.role === 'user' ? 'user' : 'agent'} appear`}>
            {m.content}
            {!!m.tools?.length && <span className="tools">kullanılan araçlar: {m.tools.join(', ')}</span>}
          </div>
        ))}
        {busy && <div className="msg agent faint">düşünüyor…</div>}
        <div ref={end} />
      </div>
      {log.length === 0 && (
        <div className="chat-suggest">
          {suggestions.map((s) => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}
        </div>
      )}
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); ask(q) }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Sorunuz…" disabled={busy} />
        <button className="btn btn-primary" disabled={busy || !q.trim()}>Sor</button>
      </form>
    </div>
  )
}
