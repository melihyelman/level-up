import type { Action, Verdict } from './api'

export const ACTIONS: Action[] = ['hemen teyit/müdahale', 'izlemeye al', 'işlem gerekmez']

export const ACTION_LABEL: Record<Action, string> = {
  'hemen teyit/müdahale': 'Müdahale',
  'izlemeye al': 'İzle',
  'işlem gerekmez': 'İşlem yok',
}

export const ACTION_TONE: Record<Action, 'urgent' | 'watch' | 'clear'> = {
  'hemen teyit/müdahale': 'urgent',
  'izlemeye al': 'watch',
  'işlem gerekmez': 'clear',
}

export const VERDICT_TONE: Record<Verdict, 'bad' | 'mixed' | 'good' | 'neutral'> = {
  'tespitle çelişiyor': 'bad',
  'kısmen uyumlu': 'mixed',
  'tespitle uyumlu': 'good',
  'doğrulanamaz': 'neutral',
  ilgisiz: 'neutral',
}

export const CLS_LABEL: Record<string, string> = { car: 'otomobil', van: 'panelvan', truck: 'kamyon', bus: 'otobüs' }

export const km = (m: number, digits = 1) => `${(m / 1000).toFixed(digits).replace('.', ',')} km`
export const num = (x: number, digits = 1) => x.toFixed(digits).replace('.', ',')

export function actionRank(a: Action | null | undefined) {
  return a ? ACTIONS.indexOf(a) : 9
}

// local metric projection around the base (good to a few metres at this scale)
export function toLocal(lat: number, lon: number, lat0: number, lon0: number): [number, number] {
  return [(lon - lon0) * Math.cos((lat0 * Math.PI) / 180) * 111_320, (lat - lat0) * 110_540]
}

// data files use ASCII names; show them properly
const ZONE_TR: Record<string, string> = {
  'Kuzey Yolu': 'Kuzey Yolu',
  'Kuzeydogu Kavsagi': 'Kuzeydoğu Kavşağı',
  'Dogu Yolu': 'Doğu Yolu',
  'Guneydogu Yerlesimi': 'Güneydoğu Yerleşimi',
  'Guney Kapisi Yaklasimi': 'Güney Kapısı Yaklaşımı',
  'Guneybati Yolu': 'Güneybatı Yolu',
  'Bati Yerlesimi': 'Batı Yerleşimi',
  'Kuzeybati Yolu': 'Kuzeybatı Yolu',
  'Merkez Us': 'Merkez Üs',
}
export const zoneName = (z: string) => ZONE_TR[z] ?? z
