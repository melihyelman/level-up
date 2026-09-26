# Çıktı biçimi deneyi: 4 seviye vs evet/hayır

| ölçüt | levels | binary | action |
|---|---|---|---|
| runs | 12 | 12 | 12 |
| vehicle_agreement | 0.676 | 0.649 | 0.459 |
| frame_agreement | 5/6 | 6/6 | 5/6 |
| coverage | 0.927 | 1.0 | 1.0 |
| validation_retries | 14 | 17 | 16 |
| avg_seconds | 158.8 | 189.3 | 154.3 |
| avg_prompt_tokens | 51341 | 55515 | 56490 |
| avg_reasoning_tokens | 2410 | 3130 | 2211 |
| errors | [] | [] | [] |

## Kare kare kararlar (tekrar1 / tekrar2)


### img_000860

| araç | levels r1 | levels r2 | binary r1 | binary r2 | action r1 | action r2 |
|---|---|---|---|---|---|---|
| **kare** | DİKKAT | DİKKAT | EVET | EVET | hemen teyit/müdahale | hemen teyit/müdahale |
| D1 | DİKKAT | DİKKAT | EVET/orta | EVET/orta | İZLE | İZLE |
| D2 | İZLE | NORMAL | HAYIR | HAYIR | YOK | YOK |
| D3 | NORMAL | NORMAL | HAYIR | EVET/orta | İZLE | İZLE |
| D4 | DİKKAT | DİKKAT | EVET/orta | EVET/orta | İZLE(düşük) | MÜDAHALE |
| D5 | İZLE | İZLE | EVET/orta | HAYIR | İZLE(düşük) | YOK(düşük) |
| D6 | DİKKAT | DİKKAT | EVET/yüksek | EVET/orta | MÜDAHALE | İZLE |

### img_005788

| araç | levels r1 | levels r2 | binary r1 | binary r2 | action r1 | action r2 |
|---|---|---|---|---|---|---|
| **kare** | DİKKAT | KRİTİK | EVET | EVET | hemen teyit/müdahale | hemen teyit/müdahale |
| D1 | DİKKAT | KRİTİK | EVET/yüksek | EVET/yüksek | MÜDAHALE | MÜDAHALE |
| D2 | İZLE | DİKKAT | HAYIR | EVET/orta | İZLE | YOK |
| D3 | İZLE | DİKKAT | HAYIR | HAYIR | İZLE | YOK |
| D4 | DİKKAT | KRİTİK | EVET/yüksek | EVET/yüksek | MÜDAHALE | MÜDAHALE |
| D5 | — | DİKKAT | HAYIR | HAYIR | İZLE | YOK |
| D6 | İZLE | İZLE | EVET/orta | HAYIR | İZLE | YOK |
| D7 | İZLE | İZLE | HAYIR | HAYIR | İZLE(düşük) | YOK |
| T0223 | İZLE | DİKKAT | EVET/orta | EVET/orta | İZLE(düşük) | İZLE(düşük) |

### img_003464

| araç | levels r1 | levels r2 | binary r1 | binary r2 | action r1 | action r2 |
|---|---|---|---|---|---|---|
| **kare** | DİKKAT | DİKKAT | EVET | EVET | izlemeye al | hemen teyit/müdahale |
| D1 | DİKKAT | DİKKAT | EVET/yüksek | EVET/yüksek | İZLE | MÜDAHALE |
| D2 | DİKKAT | DİKKAT | EVET/yüksek | EVET/yüksek | İZLE | MÜDAHALE |
| D3 | İZLE | İZLE | HAYIR | HAYIR | İZLE | İZLE |
| D4 | DİKKAT | DİKKAT | EVET/yüksek | EVET/yüksek | İZLE | MÜDAHALE |
| D5 | İZLE | NORMAL | HAYIR | HAYIR | YOK | İZLE(düşük) |
| D6 | NORMAL | NORMAL | HAYIR | HAYIR | İZLE | İZLE |
| D7 | İZLE | İZLE | HAYIR | HAYIR | İZLE(düşük) | İZLE(düşük) |

### img_003189

| araç | levels r1 | levels r2 | binary r1 | binary r2 | action r1 | action r2 |
|---|---|---|---|---|---|---|
| **kare** | DİKKAT | DİKKAT | EVET | EVET | izlemeye al | izlemeye al |
| D1 | NORMAL | NORMAL | HAYIR | HAYIR | YOK | İZLE(düşük) |
| D2 | — | İZLE | EVET/orta | EVET/orta | İZLE | İZLE |
| D3 | — | İZLE | EVET/orta | EVET/orta | İZLE(düşük) | YOK |
| D4 | — | DİKKAT | EVET/orta | HAYIR | İZLE | İZLE |

### img_006388

| araç | levels r1 | levels r2 | binary r1 | binary r2 | action r1 | action r2 |
|---|---|---|---|---|---|---|
| **kare** | DİKKAT | DİKKAT | EVET | EVET | hemen teyit/müdahale | hemen teyit/müdahale |
| D1 | DİKKAT | DİKKAT | HAYIR | HAYIR | YOK | İZLE |
| D2 | DİKKAT | DİKKAT | HAYIR | EVET/yüksek | İZLE | İZLE |
| D3 | İZLE | İZLE | HAYIR | EVET/orta | İZLE(düşük) | YOK |
| D4 | DİKKAT | DİKKAT | HAYIR | EVET/yüksek | YOK | YOK |
| D5 | İZLE | İZLE | EVET/orta | HAYIR | İZLE(düşük) | YOK(düşük) |
| D6 | NORMAL | NORMAL | EVET/orta | HAYIR | İZLE(düşük) | YOK(düşük) |
| D7 | DİKKAT | DİKKAT | EVET/yüksek | EVET/orta | MÜDAHALE | MÜDAHALE |
| T0057 | İZLE | DİKKAT | EVET/yüksek | EVET/yüksek | MÜDAHALE | MÜDAHALE(düşük) |

### img_003880

| araç | levels r1 | levels r2 | binary r1 | binary r2 | action r1 | action r2 |
|---|---|---|---|---|---|---|
| **kare** | DİKKAT | DİKKAT | EVET | EVET | hemen teyit/müdahale | hemen teyit/müdahale |
| D1 | DİKKAT | DİKKAT | EVET/yüksek | EVET/yüksek | MÜDAHALE | MÜDAHALE |
| D2 | DİKKAT | DİKKAT | EVET/orta | HAYIR | İZLE | İZLE |
| D3 | DİKKAT | DİKKAT | EVET/yüksek | EVET/yüksek | MÜDAHALE | MÜDAHALE |
| D4 | İZLE | İZLE | HAYIR | HAYIR | İZLE(düşük) | YOK(düşük) |