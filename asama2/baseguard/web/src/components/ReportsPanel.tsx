import { useState } from 'react'
import type { Report } from '../lib/api'
import { VERDICT_TONE, zoneName } from '../lib/format'

export default function ReportsPanel({ reports }: { reports: Report[] }) {
  const coord = reports.filter((r) => r.scope === 'koordinat')
  const zone = reports.filter((r) => r.scope !== 'koordinat')
  const [openZone, setOpenZone] = useState(false)

  if (!reports.length) return <div className="empty">Bu kareyle ilgili saha raporu yok.</div>
  return (
    <div>
      <div className="empty" style={{ padding: '14px 16px 4px' }}>
        Raporlar doğrulanmamıştır. Her iddia, sensör ölçümüyle yan yana konur; hükmü ajan verir, çelişkide tespit esas alınır.
      </div>
      {coord.map((r) => <ReportCard key={r.rid} r={r} />)}
      {zone.length > 0 && (
        <div className="rcard">
          <button className="btn btn-ghost" style={{ padding: 0, height: 'auto' }} onClick={() => setOpenZone(!openZone)}>
            {openZone ? '▾' : '▸'} Bölge geneli raporlar ({zone.length})
          </button>
          {openZone && zone.map((r) => <ReportCard key={r.rid} r={r} compact />)}
        </div>
      )}
    </div>
  )
}

const trClaim = (s: string) =>
  s.replace(/bus\/truck/g, 'ağır araç').replace(/\btruck\b/g, 'kamyon').replace(/\bcar\b/g, 'otomobil')
    .replace(/\bvan\b/g, 'panelvan').replace(/\bbus\b/g, 'otobüs')

function ReportCard({ r, compact }: { r: Report; compact?: boolean }) {
  const where = r.scope === 'koordinat'
    ? r.dist_point_to_frame_m === 0 ? 'nokta karede' : `nokta karenin ${r.dist_point_to_frame_m} m dışında`
    : `bölge: ${zoneName(r.zone ?? '')}`
  return (
    <div className="rcard" style={compact ? { padding: '12px 0 0', borderBottom: 0 } : undefined}>
      <div className="rcard-top">
        <span className="mono" style={{ color: 'var(--ink)' }}>{r.rid}</span>
        <span className={`src ${r.source === 'third_party' ? 'third' : ''}`}>{r.source === 'official' ? 'RESMİ' : '3. TARAF'}</span>
        <span>{r.time} · çekimden {r.minutes_before_capture} dk önce · {where}</span>
        {r.agent && <span className={`pill ${VERDICT_TONE[r.agent.verdict]}`} style={{ marginLeft: 'auto' }}>{r.agent.verdict}</span>}
      </div>
      <p className="quote">“{r.text}”</p>
      {!!r.claims_vs_measurements?.length && (
        <table className="claims">
          <thead><tr><th>İddia</th><th>Sensör ölçümü</th></tr></thead>
          <tbody>
            {r.claims_vs_measurements.map((c, i) => (
              <tr key={i}>
                <td>{trClaim(c.claim)}</td>
                <td className="meas">{c.measurement.split('; ').map((part, j) => <div key={j}>{trClaim(part)}</div>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {r.agent && (
        <div className="verdict-line">
          <span className="eyebrow" style={{ paddingTop: 3, whiteSpace: 'nowrap' }}>Ajan</span>
          <p>{r.agent.reason}</p>
        </div>
      )}
      {r.agent && r.agent.claims_checked.length > 0 && !compact && (
        <details style={{ marginTop: 8 }}>
          <summary className="faint" style={{ fontSize: 14, cursor: 'pointer' }}>İddia bazında ajan notları ({r.agent.claims_checked.length})</summary>
          <table className="claims" style={{ marginTop: 6 }}>
            <tbody>
              {r.agent.claims_checked.map((c, i) => <tr key={i}><td>{c.claim}</td><td className="meas">{c.finding}</td></tr>)}
            </tbody>
          </table>
        </details>
      )}
    </div>
  )
}
