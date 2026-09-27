# Aşama 1: Drone görüntülerinde araç tespiti (TAYFUN)

Sınıflar: car, van, truck, bus. Metrik: mAP@0.5.

**Son model:** 3 YOLO26 modelinin WBF birleşimi. Public LB **0.79722**, doğrulama mAP50 **0.8806**.
Tüm modeller yalnızca COCO ön eğitimli ağırlıklardan (`yolo26m.pt`, `yolo26l.pt`) başlatıldı.

## Birleşimdeki modeller

| Model | Koşu adı | Mimari | Veri | Epoch | Çıkarım | Ağırlık | Val mAP50 |
|---|---|---|---|---|---|---|---|
| night | `p4_carunder_yolo26l_1536_e30` | YOLO26-L, 1536 px | araba ağırlıklı görüntüler azaltılmış | 39 | 8 görünüm TTA | 3 | 0.8748 |
| carunder | `p3_carunder_sh0.8_e20` | YOLO26-M, 1280 px | araba ağırlıklı görüntüler azaltılmış | 26 | 3 görünüm TTA | 1 | 0.8598 |
| patch | `p2_patch` | YOLO26-M, 1280 px | nadir sınıf yamaları eklenmiş | 15 | tek görünüm | 1 | 0.8432 |
| **Birleşim** | | | | | WBF, iou 0.65 | 3:1:1 | **0.8806** |

Sınıf bazında AP50 (birleşim): car 0.936, van 0.792, truck 0.866, bus 0.928.

## Dosyalar ve sıra

| Dosya | Ne yapar |
|---|---|
| `1_egitim_patch_m1280.ipynb` | Veri hazırlama, test benzeri doğrulama bölmesi, nadir sınıf yama üretimi, `p2_patch` eğitimi (`VARIANT='patch'`, `EP=20`) |
| `2_egitim_carunder_m1280.ipynb` | Araba ağırlıklı görüntüleri çıkarma (`CU_SH=0.8`), `p3_carunder_sh0.8_e20` eğitimi, 3 görünüm TTA |
| `3_egitim_night_l1536.ipynb` | Aynı veri varyantıyla YOLO26-L 1536 eğitimi (`p4`), kopmadan sonra otomatik devam |
| `4_tta_multizoom.py` | 8 görünüm TTA (1.0, yatay çevirme, 1.1, 1.25, 1.75, 2.0 yakınlaştırma + Ultralytics aug + çevrilmiş 1.25). Colab'da `exec(open(...).read())` ile `3_` notebook'undan sonra çalıştırıldı |
| `5_blend_agirlik_arama.py` | 647 doğrulama görüntüsünde WBF ağırlık araması ve test birleşimi |
| `../model/infer_blend.py` | Eğitilmiş 3 ağırlıkla yeni görüntülerde uçtan uca çıkarım → `submission.csv` (depoda hazır) |
| `parse_sub.py` | Gönderim dosyası okuyucu (blend için) |
| `sonuclar/` | Ağırlık araması sonucu, TTA grid kaydı, tüm deneylerin tablosu (`EXPERIMENTS.md`) |

## Yeniden üretme

1. Notebook'lar Google Colab'da (A100) çalıştırıldı. İlk hücrelerdeki `DATA` (yarışma verisi) ve `RUNS` (çıktı klasörü) yollarını kendi ortamınıza göre ayarlayın.
2. `1_`, `2_`, `3_` notebook'larını sırayla çalıştırın. Her biri aynı test benzeri doğrulama bölmesini (647 görüntü, seed 42) kurar ve modeli, doğrulama/test tahminlerini `RUNS` altına yazar.
3. `3_` sonrası `4_tta_multizoom.py` ile 8 görünüm TTA tahminlerini üretin.
4. `ROKETSAN_ROOT` ortam değişkeni `data/` ve `runs/` klasörlerini gösterecek şekilde `python 5_blend_agirlik_arama.py`.
5. Sadece çıkarım için (eğitim gerekmez): `pip install -r requirements.txt`, sonra depo kökünden `python model/infer_blend.py --test_dir <görüntü klasörü> --weights model/weights --out submission.csv`.

Eğitilmiş ağırlıklar ve hazır çıkarım kodu depoda `../model/` klasöründe: `model/weights/` (`night_l1536.pt`, `carunder_m1280.pt`, `patch_m1280.pt`) ve `model/infer_blend.py`.
Yarışma verisi kurallar gereği depoya eklenmedi.

## Önemli kararlar

- **Doğrulama bölmesi:** Test setinde 2000x1500 görüntü yok, çözünürlük dağılımı farklı. Bu yüzden rastgele bölme yerine test ile aynı çözünürlük dağılımında 647 görüntü ayrıldı.
- **Çoklu etiketli NMS:** Aynı kutuya birden fazla sınıf skoru bırakmak doğrulamada 0.808 → 0.826.
- **Araba azaltma:** Araba oranı %80 ve üzeri, kamyon/otobüs içermeyen 1537 görüntü eğitimden çıkarıldı.
- **TTA:** Yakınlaştırma küçük araçlara yardım ediyor, uzaklaştırma zarar veriyor (grid araması `sonuclar/grid_log.txt`).
- **Denenip birleşime girmeyenler:** RF-DETR (ağırlığı 0 çıktı ve ön eğitim kural riski taşıyordu), gece görüntüleri için CLAHE (kazanç yok).
