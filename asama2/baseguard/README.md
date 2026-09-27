# BaseGuard · Saha raporu destekli LLM ajanı

Bir drone karesini **araç tespitleri + son 2 saatlik hareket kayıtları + saha raporlarıyla** birlikte
değerlendirip üs için neyin dikkat gerektirdiğini gerekçeleriyle bildiren ajan.

## Hızlı başlangıç

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                      # GLM_API_KEY'i girin
.venv/bin/python -m scripts.precompute_detections   # 40 kare, tam blend (~2.5 dk, M2/MPS) → cache/detections.json
# web arayüzü (React) — demo: tek süreç
(cd web && npm install && npm run build)
.venv/bin/uvicorn server.api:app --port 8000   # → http://localhost:8000
# geliştirme: backend + Vite (hot reload)
.venv/bin/uvicorn server.api:app --port 8000 --reload & (cd web && npm run dev)   # → http://localhost:5173
.venv/bin/streamlit run app.py            # eski geliştirici arayüzü (araç testi: ?dev=1)
.venv/bin/python cli.py img_000860        # ajanın araç çağrıları + değerlendirmesi
.venv/bin/python cli.py img_000860 --facts  # yalnızca ölçümler (LLM'siz)
.venv/bin/python cli.py --all             # günün tüm kareleri, öncelik sırasıyla
.venv/bin/python -m pytest -q tests
```

Veri dosyaları varsayılan olarak bir üst klasörden (`stage2/`) okunur; `BG_DATA_DIR` ile değiştirilebilir.
API anahtarı yoksa ajan çalışmaz; arayüz yalnızca ölçümleri gösterir.

## Mimari: araçlar ölçer, agent karar verir, denetim doğrular

```
kullanıcı: "img_000860'ı değerlendir"  (+ işaretsiz kare)
   │
   ▼
agent/runner.py   GLM-5.3-Flash araç çağırma döngüsü (reasoning high, en fazla 12 tur, token sınırı)
   │  hangi aracı, hangi sırayla çağıracağına agent karar verir
   ├─ get_image_info     boyut, çekim saati, köşe koordinatları, üsse uzaklık                  core/scene.py
   ├─ detect_vehicles    1. gün modeli (3×YOLO26+TTA+WBF, cache) + piksel→enlem/boylam + işaretli kare
   ├─ match_tracks       çekim anında biten kayıtlarla birebir eşleşme ve mesafeler             core/tracks.py
   ├─ get_motion         (bir ya da birden çok kayıt) üsse uzaklık serisi, hız, yön, duraklama,
   │                     üs etrafında taranan açı, son 1 saatte yakın seyreden kayıtlar
   ├─ get_reports        ham raporlar + rapor noktası çevresindeki araçlar + iddia→ölçüm tablosu core/reports.py
   ├─ view_region        yakın plan (renk/yük/sınıf kontrolü)
   ├─ get_track_points, search_reports
   └─ submit_assessment  kareye özel şema: her araç ve her koordinatlı rapor için anahtarlı karar
          │
          ▼
agent/audit.py    gerekçe denetimi: kapsam · var olmayan kimlik · ölçümsüz "konvoy" · araç çıktısında
                  karşılığı olmayan sayı → en fazla 2 kez agent'a düzeltmeye döner, kalanlar uyarı olarak görünür
```

- **Karar biçimi:** Her araç için *eylem* (hemen teyit/müdahale · izlemeye al · işlem gerekmez) ve *güven*
  (yüksek/düşük). 4 seviye ve evet/hayır ile karşılaştırılarak seçildi: `cache/experiments/output_modes/report.md`.
- **Tehdit tanımı:** [agent/doctrine.md](agent/doctrine.md). Nitel ölçütler; puan ya da formül yok.
  Ajana olduğu gibi verilir, kararı ajan verir.
- **Ajana giden girdi:** İlk mesajda işaretsiz kare; `detect_vehicles` işaretli kareyi, `view_region` yakın
  planları gösterir. Her turun düşüncesi (en fazla 1500 karakter) sonraki tura not olarak taşınır.
- **İzlenebilirlik:** Her araç çağrısı, sonucu ve denetim adımı kaydedilir; arayüzde ve komut satırında görünür.
- **LLM yoksa:** Karar üretilmez, yalnızca ölçümler gösterilir (`cli.py <id> --facts`).
- **Kararlılık ölçümü:** `python -m scripts.eval_stability --name <ad>`. Aynı kareleri tekrar çalıştırıp
  kararların ne kadar tutarlı olduğunu, kapsamı ve denetim istatistiklerini raporlar.

## Web arayüzü (`web/`, `server/api.py`)

- **Günlük durum:** Üs merkezli taktik harita (1·2·4·6 km halkaları, bölgeler, 40 kare), zaman çizelgesi ve
  ajanın önerdiği eyleme göre öncelik kuyruğu. Harita çevrimdışı SVG'dir; internet gerekmez.
- **Kare incelemesi:** Görüntü üzerinde ajanın kararıyla renklenen etkileşimli kutular; araç seçilince gerekçe,
  ölçümler, üsse göre 2 saatlik rota ve yakın plan. Raporlar sekmesi her iddiayı sensör ölçümüyle yan yana gösterir.
- **Ajan akışı:** Son çalıştırmanın kaydı, 6× hızla *kayıttan oynatma* (açıkça etiketli) ya da *canlı çalıştırma*
  (SSE ile adım adım: araç çağrıları, yakın planlar, denetim, karar). **Soru sor** sekmesi takip sorularını cevaplar.
- Renk yalnızca durumu anlatır: kırmızı müdahale, amber izle, gri işlem yok, mavi değerlendirilmedi.
- Klavye: ← → kareler arası, Esc geri.

## Ölçüm katmanıyla ilgili notlar

- Eşleşme önce güvenli kutularla (conf ≥ 0.3), sonra zayıf kutularla yapılır ki zayıf bir kopya kutu
  kaydı "çalmasın". 40 karede medyan eşleşme mesafesi 0.1 m.
- Örnekteki T0122 kamyonu modelde 0.12 güvenle çıkıyor. Bu yüzden zayıf kutular da agent'a verilir ve
  gerçek olup olmadığına kayıt ile görüntüye bakarak agent karar verir.
- Kareler aslında eğik açılı. Görev tanımı gereği kuşbakışı doğrusal dönüşüm kullanılıyor; birkaç metrelik hata olabilir.

## Testler

`tests/test_core.py` ölçümleri görev tanımındaki ve canlı örnekteki sayılarla karşılaştırır.
`tests/test_agent_loop.py` agent döngüsünü sahte bir LLM ile test eder: araç dağıtımı, görüntüler, şema
reddi, denetimle geri dönme, cache. Ayrıca denetimin elle incelenen img_005788 hatalarını yakaladığını doğrular.
