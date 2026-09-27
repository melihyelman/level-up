# Tehdit tanımı

> Ajana olduğu gibi verilir. Puan ya da formül değildir: ajan bu ölçütleri kanıta uygular, kararı
> kendisi verir ve gerekçesini yazar.

## Dikkat artıran göstergeler
Tek bir gösterge çoğu zaman yeterli değildir; göstergelerin birleşimi ve üsse yakınlık önemlidir.

1. **Üsse yaklaşma:** Son 30–60 dakikada üsse uzaklık belirgin şekilde azalıyor, şu anki yön üsse dönük,
   tahmini varış süresi kısa.
2. **Üs çevresinde tur veya yoklama:** Üs etrafında büyük bir açı taranmış (`base_sweep_deg`), ya da araç
   üsse yaklaşıp geri çekilmiş. En yakın geçiş üsse ne kadar yakınsa o kadar önemlidir.
3. **Bekleme veya dolaşma:** Üsse yakın bir noktada uzun süre bekleme ya da uzun yol kat edip aynı bölgede
   kalma (toplam yol büyük, net yer değiştirme küçük).
4. **Birlikte hareket:** Yalnızca `moving_together_with` ile ölçülmüş eşlik sayılır. Aynı anda aynı yolda
   bulunmak birlikte hareket değildir.
5. **Araç tipi:** Ağır araçlar (truck/bus) ve yük ya da örtü şüphesi daha fazla dikkat gerektirir.
6. **Raporla çelişki:** Özellikle bir aracı zararsız gösteren iddialar (dost unsur, planlı ikmal, "hareketleri
   olağan") tip veya hareket ölçümüyle çelişiyorsa bu tek başına ciddi bir işarettir.
7. **Kör nokta:** Hareket kaydı olup tespit edilemeyen ya da düşük güvenle tespit edilen araçların sınıfı
   belirsizdir. Bu belirsizlik kendi başına bir risktir.

## Riski azaltanlar
- Üsten belirgin şekilde uzaklaşma.
- Üsten uzakta, aynı yolda aynı yöne akan sıradan trafik.
- Üsten uzakta, uzun süredir yerinden ayrılmamış park halindeki araç.
- Kimlik iddiası (dost, planlı, teyitli) **tek başına riski düşürmez.** Yalnızca tip ve hareket tutarlıysa
  ve başka gösterge yoksa riski azaltan etken sayılabilir.

## Referans değerler
- Karelerin üsse uzaklığı yaklaşık 1,5 ile 5,5 km arasındadır. Bu aralığın yakın ucu (~2 km altı) ve
  ~15 dakikanın altındaki tahmini varış süreleri daha acildir.
- Üs etrafında ~90°'den büyük tarama ve ~1 km'nin altına inen en yakın geçiş dikkat çekicidir.

## Eylem
- **hemen teyit/müdahale:** Üsse yakın ya da yaklaşan bir araçta birden fazla gösterge varsa; kimlik
  iddiasıyla çelişen ve yaklaşan bir araç varsa; üsse çok yakın geçişli tur veya yoklama varsa.
- **izlemeye al:** Tek gösterge varsa, ya da kanıt zayıf veya çelişkiliyse.
- **işlem gerekmez:** Gösterge yoksa ya da riski azaltan durum baskınsa.
- **Güven:** Kanıt tutarlı ve yeterliyse yüksek. Tespit güveni düşükse, görsel teyit yapılamadıysa, rapor
  doğrulanamıyorsa ya da ölçümler çelişiyorsa düşük.
