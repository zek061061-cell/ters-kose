# TERS KÖŞE — RiskBudur analiz motoru eşleme envanteri

Bu dosya Ters Köşe'nin tek-maç / tek-radar yaklaşımında arka planda çalışan analiz motorlarını, RiskBudur'da görülen analiz başlıklarıyla eşlemek için tutulur. Ayrı sekme açmak yerine bu sinyaller tek maç analizinde birleştirilir.

## Analiz motorları

| RiskBudur başlığı / mantığı | Ters Köşe karşılığı | Durum |
|---|---|---|
| Skor Örüntü Motoru | Skor örüntü motoru + Skor hafızası zinciri | Tamam |
| Üçleme | Üçleme motoru (G/B/M üçlü dizisi) | Tamam |
| Hakem Analizi | Hakem analizi | Tamam |
| Aynı Gün Sürpriz | Aynı gün sürpriz | Tamam |
| Tüm Sezon Eşleşme | Tüm sezon eşleşme + günlük eşleşme | Tamam |
| Hafta Sürpriz | Hafta sürpriz | Tamam |
| Sürpriz Profil | Aylık sürpriz profil | Tamam |
| Fikstür Skor | Fikstür skor akışı | Tamam |
| Fikstür Şikesi | Fikstür şikesi / rakip hafta teması | Tamam |
| Yatay Fikstür | Yatay fikstür | Tamam |
| Bülten | Günlük Bülten + toplu analiz | Tamam |
| 3-3 Geri Zincir | 3-3 geri zincir | Tamam |
| Sezon Tekerrür Avı | Sezon tekerrür avı / sezon tekerrürü | Tamam |
| Lig Sürpriz Haritası | Lig sürpriz haritası | Tamam |
| Lig Sürpriz Şeması | Lig sürpriz şeması | Tamam |
| Fikstür Temas Radarı | Fikstür temas radarı | Tamam |
| Hafta / Tarih Akışı | Hafta / tarih akışı + tarih/hafta benzerliği | Tamam |
| Lig Sürpriz Liderleri | Lig sürpriz liderliği | Tamam |
| Sürpriz 7'li Avı | Sürpriz 7'li avı | Tamam |
| Rakip Sürpriz | Rakip sürpriz + rakip sürpriz kontrolü | Tamam |
| Sürpriz Kontrolü | Sürpriz kontrolü | Tamam |
| Skor Varyasyon Avı | Skor varyasyon avı + skor varyasyon motoru | Tamam |
| 2-2 / 4-1 Takip | 2-2 / 4-1 takip | Tamam |
| Sıra Sayım Sonuçları | Sıra sayım sonuçları | Tamam |
| Benzer Hafta Bulucu | Benzer hafta bulucu | Tamam |
| AI Radar | AI Radar meta-motor + Ana Karar | Tamam |
| Senaryo Zincir | Senaryo zinciri | Tamam |
| Zincir Sürpriz | Zincir sürpriz 1/2 ve 2/1 | Tamam |
| Önceki Sezon Zinciri | Önceki sezon zinciri + önceki sezon temas zinciri | Tamam |
| Aylık Maç Akışı | Aylık maç akışı | Tamam |
| Ortak Takım Kümesi Motoru | Ortak takım kümesi | Tamam |
| Oran Analizi | Tarihsel 1-X-2 oran profili + piyasa olasılığı karşılaştırması | Tamam (oran verisi varsa) |

## Ters Köşe'ye özel ek katmanlar

- Tek maçta 1-X-2, çifte şans, KG, 1.5/2.5/3.5/4.5 Alt-Üst, takım golü, gol aralığı, skor, İY ve İY/MS olasılıkları.
- Poisson + takım formu + iç/deplasman performansı + H2H + lig ortalaması.
- 10 yıllık veri deposu için kalite kapısı, yinelenen/hatalı satır kontrolü, eksik sezon tespiti ve hedefli yeniden deneme.
- Lig bazlı kalibrasyon, motor bazlı backtest ağırlığı ve lig güven puanı.
- Güçlü tahmin başarı takibi, güven aralıkları, performans trendi ve model drift koruması.
- PAS GEÇ / ÖNERİ YOK sistemi: çelişkili veya zayıf veride zorla seçim üretmez.
- Excel/CSV otomatik sütun eşleme, oynanacak maçları toplu analiz, filtreleme ve Excel dışa aktarma.
- Günlük bülten ve haftalık radar tek karar katmanına bağlıdır.

## Bilinçli olarak kopyalanmayan ürün özellikleri

Topluluk Arena, Kupon Paylaş, lisans üretimi ve Telegram gönderimi analiz motoru değildir. Ters Köşe'nin mevcut hedefi analizleri çok sayıda ayrı sekmeye bölmeden tek maç / bülten / radar / veri akışında birleştirmektir. Bu sosyal ve ticari özellikler daha sonra ayrıca eklenebilir.

## Canlıya çıkış kontrol listesi

1. Son GitHub sürümünü Render'a deploy et.
2. /history/build ile 10 yıllık depoyu oluştur.
3. /history/status ile maç, lig, eksik sezon ve kalite değerlerini doğrula.
4. /history/retry-gaps ile varsa tamamlanmış sezon boşluklarını yeniden dene.
5. Uygulamada Sistem Testi'ni çalıştır.
6. Backtest çalıştır ve kalibrasyon meta verisini güncelle.
7. Maç Analizi, Bülten, Haftalık Radar ve Excel toplu analizini uçtan uca test et.
