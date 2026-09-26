// Types mirror server/api.py. Measurements come from tools; decisions only from the agent.

export type Action = 'hemen teyit/müdahale' | 'izlemeye al' | 'işlem gerekmez'
export type Confidence = 'yüksek' | 'düşük'
export type Verdict = 'tespitle uyumlu' | 'kısmen uyumlu' | 'tespitle çelişiyor' | 'doğrulanamaz' | 'ilgisiz'

export interface FrameSummary {
  id: string
  time: string
  zone: string
  dist_to_base_m: number
  direction: string
  center: [number, number]
  footprint_m: [number, number]
  vehicles: number
  assessment: null | { action: Action; headline: string; urgent: number; watch: number; contradicted: number }
}

export interface Overview {
  base: { name: string; lat: number; lon: number }
  zones: { name: string; lat: number; lon: number }[]
  llm: { available: boolean; model: string }
  frames: FrameSummary[]
  stats: {
    frames: number
    assessed: number
    urgent_frames: number
    watch_frames: number
    urgent_vehicles: number
    contradicted_reports: number
  }
}

export interface Stop { start: string; end: string; minutes: number; dist_to_base_m: number }

export interface Motion {
  track_id: string
  start: string
  end: string
  dist_to_base_series: [string, number][]
  dist_to_base_now_m: number
  start_dist_to_base_m: number
  min_dist_to_base_m: number
  min_dist_time: string
  speed_last_10m_ms: number
  speed_last_30m_ms: number
  path_len_m: number
  net_disp_m: number
  closing_rate_30m_ms: number
  heading_compass: string | null
  heading_vs_base_deg: number | null
  base_sweep_deg: number
  eta_to_base_min: number | null
  moving_now: boolean
  stopped_minutes_total: number
  stops: Stop[]
  polyline: [string, number, number][]
  moving_together_with: { track_id: string; mean_sep_m: number }[]
}

export interface Decision {
  id: string
  track_id: string | null
  action: Action
  confidence: Confidence
  reason: string
  evidence?: string[]
}

export interface Vehicle {
  id: string
  kind: 'detection' | 'track_only'
  cls: string | null
  conf: number | null
  box: [number, number, number, number] | null
  center_px: [number, number]
  lat: number
  lon: number
  dist_to_base_m: number
  track_id: string | null
  match_dist_m: number | null
  required: boolean
  motion: Motion | null
  decision: Decision | null
}

export interface ReportVerdict {
  rid: string
  verdict: Verdict
  reason: string
  claims_checked: { claim: string; finding: string }[]
}

export interface Report {
  rid: string
  time: string
  source: 'official' | 'third_party'
  text: string
  scope: 'koordinat' | 'bölge' | 'genel'
  minutes_before_capture: number
  point?: [number, number]
  point_px?: [number, number]
  dist_point_to_frame_m?: number
  zone?: string
  within_60m_of_point?: { id: string; cls: string; conf: number | null; dist_m: number; track_id: string | null }[]
  claims_vs_measurements?: { claim: string; measurement: string }[]
  agent: ReportVerdict | null
}

export interface Brief {
  action: Action
  headline: string
  brief: string
  vehicles: Decision[]
  reports: ReportVerdict[]
  uncertainties: string[]
  audit: string[]
}

export interface FrameDetail {
  info: {
    image_id: string
    capture_time: string
    width_px: number
    height_px: number
    footprint_m: [number, number]
    m_per_px: number
    nearest_zone: string
    dist_to_base_m: number
    direction_from_base: string
    center: [number, number]
    base: { name: string; lat: number; lon: number }
  }
  vehicles: Vehicle[]
  reports: Report[]
  tracks_just_outside: { track_id: string; dist_outside_frame_m: number }[]
  assessment: null | {
    brief: Brief
    usage: { calls: number; prompt_tokens: number; completion_tokens: number; reasoning_tokens: number; seconds: number }
    effort: string
    model: string
    audit_rounds: number
    created: number
    steps: number
  }
  running: boolean
}

export interface TraceEvent {
  kind: 'start' | 'user' | 'say' | 'thought' | 'tool_call' | 'tool_result' | 'warn' | 'audit' | 'final' | 'done' | 'error'
  title?: string
  detail?: unknown
  t?: number
  mode?: 'live' | 'replay'
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

export const api = {
  overview: () => get<Overview>('/api/overview'),
  frame: (id: string) => get<FrameDetail>(`/api/frames/${id}`),
  imageUrl: (id: string) => `/api/frames/${id}/image`,
  cropUrl: (id: string, target: string) => `/api/frames/${id}/crop/${target}`,
  streamUrl: (id: string, mode: 'replay' | 'live', speed = 6) =>
    mode === 'replay' ? `/api/frames/${id}/replay?speed=${speed}` : `/api/frames/${id}/run`,
  chat: async (id: string, question: string, history: { role: string; content: string }[]) => {
    const r = await fetch(`/api/frames/${id}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history }),
    })
    if (!r.ok) throw new Error(await r.text())
    return (await r.json()) as { answer: string; tools: string[] }
  },
}

export const getTrace = (id: string) => get<TraceEvent[]>(`/api/frames/${id}/trace`)
