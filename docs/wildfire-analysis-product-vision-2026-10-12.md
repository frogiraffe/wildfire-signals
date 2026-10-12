# Wildfire Signals: yangın analizi ürün hedefi

Durum: ürün hedefi ve aşamalı uygulama planı, 12 Ekim 2026. Bu belge önceki [gözlem inceleme planının](analysis-product-2026-10-12.md) üstündedir. Mevcut çalışan harita bu hedefin yalnızca veri toplama ve gözlem gösterme bölümünü karşılar. Aşağıdaki olasılıklar ve yayılım tahminleri bugün üründe yoktur.

## Kullanıcının alacağı yanıt

Bir kullanıcı seçtiği bölge ve zaman için şu dört soruyu sorabilmelidir:

1. **Şu anda nerede yangın var?** Kurumca bildirilen aktif orman/arazi yangınını, henüz doğrulanmamış uydu termal adayını ve yangın dışı sıcak kaynağı ayrı göster. Kaynağı, son doğrulama zamanını, konum belirsizliğini, varsa çevre sınırını ve çelişen kanıtı göster. “Kayıt yok” ile “yangın yok” aynı şey değildir.
2. **Yangın yoksa burada yangın oluşma olasılığı nedir?** Açık bir hedef tanımla: örneğin belirli coğrafi hücrede önümüzdeki 24 saatte bağımsız kaynakla kayda geçen yeni *arazi yangını* olasılığı. Yangın havası/tehlike endeksini doğrudan olay olasılığı gibi sunma; tutuşma nedenleri ve gözlem eksikliği ayrıca ele alınmalıdır.
3. **Aktif yangın nereye ve ne kadar ilerleyebilir?** Belirli 6/12/24 saat ufuklarında olası yayılım alanlarını, belirsizlik aralığını ve veri geçerlilik saatini göster. Rüzgâr tek başına yayılım tahmini değildir; başlangıç çevresi veya konumu, yakıt/bitki örtüsü, topoğrafya, nem, yağış ve müdahale bilgisi gereken girdilerdir. Bu girdiler yoksa “tahmin üretilemiyor” de.
4. **Yangının sönme veya etkin kalma olasılığı nedir?** Önce olay sonlanımı etiketini tanımla: son termal sinyal, kurumca kontrol altına alınma ve tamamen söndürülme farklı durumlardır. Yeterli ve zamanlı olay/müdahale geçmişi olmadan sayısal olasılık gösterme. Çıktı verilebildiğinde belirli zaman ufku, belirsizlik ve hangi sonlanımın tahmin edildiği görünür olmalıdır.

Amaç yangın yönetimine yardımcı **kanıtlı durum ve olasılık bilgisi** sunmaktır. Acil müdahale kararını otomatikleştirme veya resmî kurumun yerini alma iddiası değildir.

## Veri ve ürün sınırları

| Girdi | Üründeki görevi | Şimdiki durum |
| --- | --- | --- |
| NASA FIRMS uydu tespitleri | Erken aday sinyali ve zaman dizisi | NOAA-20/21 0,05° hücre/saat adayları toplanıyor; yangın doğrulaması değil. |
| Resmî olay kayıtları ve yangın çevreleri | Olay kimliği, durum ve bağımsız değerlendirme etiketi | NIFC/CWFIS olayları ayrı toplanıyor; küresel kapsam ve çevre geçmişi yok. |
| Hava durumu ve tahmini | Oluşma koşulu, yayılım ve sonlanım girdisi | Yok; 10 m rüzgâr/hız/hamle, nem, sıcaklık ve yağış kaynağı ile Free maliyeti sınanacak. |
| Yakıt/bitki, arazi örtüsü, topoğrafya ve kuraklık | Yayılım ve oluşma modellerinin yerel girdileri | Açık depoda bütünleşik katman yok; çözünürlük, lisans ve güncellik araştırılacak. |
| Yıldırım, insan etkinliği ve müdahale/containment geçmişi | Tutuşma ve sonlanım tahmini için olası girdiler | Kapsam ve güvenilirlik bölgeye göre araştırılacak; eksikse model hedefi daraltılacak. |
| Tarihsel yangın olayları ve çevreleri | Eğitim, geçmişe dönük sınama ve karşılaştırma | Mevcut 72 saatlik harita saklaması bunun için yeterli değil. |

Sosyal medya veya haberler resmî olayla otomatik eşitlenmez. Konum, olay zamanı, tür ve kullanım hakkı doğrulanmadan yalnızca insan incelemesine açık kanıt olabilir. Quesería'daki araç yangını ile yaklaşık 455 km uzaktaki uydu adayı aynı olay sayılmamalıdır. NASA, termal anomalilerin yangın dışı sıcak kaynaklardan da gelebileceğini ve bulutların yangınları gizleyebileceğini [açıkça belirtiyor](https://firms.modaps.eosdis.nasa.gov/map2/).

Bu herkese açık depoya özel geliştirme deposunun kodu, veritabanı, anahtarı veya geçmişi taşınmaz. Özel model çalışması ayrı sınırda değerlendirilir; yalnızca yayımlanması uygun, denetlenmiş veri/sonuç sözleşmesi burada kullanılır. Workers/KV Free ve mevcut GitHub kaynak sınırları aşılmadan mimari seçilir.

## Aşamalar ve geçiş ölçütleri

1. **Olay zemini:** uydu adayından ayrı, zaman içinde kimliği korunan kurum olayı; kaynak tazeliği, olay türü, çevre ve kanıt bağlantıları. Bölge pilotu, bağımsız olay ve geçmiş çevre verisi bulunan yerden seçilir; küresel harita kapsamı, küresel model doğruluğu iddiası yaratmaz. İlk geçiş: yanlış eşleşme ve kaçan olaylar bağımsız veriyle ölçülür.
2. **Tarihsel ve çevresel veri:** olay/çevre zaman dizisi, hava, yakıt ve topoğrafyayı aynı konum ve *o anda bilinen* zamanla birleştir. Sağlayıcı hakları, güncellik, eksik aralık, indirme boyutu ve Free kota pilotu geçilmeden sürekli toplama açılmaz.
3. **Yangın oluşma olasılığı:** önce hava/kuraklık koşullarını açıklayıcı göster; sonra yeni olay hedefi için basit tarihsel taban oranı ile model karşılaştırması yap. Negatif örneklerin gözlem kapsamı belgelenir. Farklı yıl ve bölgelerde geriye dönük sınama, kalibrasyon ve ileriye dönük izleme olmadan yüzde yayımlanmaz.
4. **Aktif yangın yayılımı:** başlangıç çevresi ve çevresel girdiler olan olaylarda önce referans/senaryo modeli, ardından olasılıksal alanlar. Rüzgâr oku bir yayılım modeli yerine geçmez. Geçmiş çevre ilerlemesiyle mekânsal örtüşme, varış zamanı hatası ve güven aralığı kapsamı ölçülür. [US Forest Service FARSITE çalışması](https://research.fs.usda.gov/treesearch/27413) hava/rüzgâr değişimi ile arazi verisinin birlikte gerektiğini gösterir.
5. **Sönme/etkin kalma:** kurumların “aktif”, “kontrol altında” ve “söndü” kayıtları yeterli ve karşılaştırılabilirse zaman ufuklu sonlanım modeli; aksi halde yalnızca gözlenen son durum ve belirsizlik. Müdahale verisi yoksa bunun etkisi ölçülmeden kesin sonuç söylenmez.
6. **Ürün kapısı:** her ayrı çıktı için kaynak kapsaması, gecikme, eksik dönemler, referans model karşılaştırması, kalibrasyon ve ileriye dönük performans raporu. Başarısız veya etiketsiz çıktılar arayüzde “bilinmiyor/deneysel” olarak kalır. Yedi günlük toplama sürekliliği ve gerçek cihaz deneyimi ayrıca doğrulanır.

## İlk somut sonraki iş

Mevcut gözlem listesini daha fazla süslemek yerine **olay ve doğrulama veri sözleşmesini** tasarla: `satellite_candidate`, `agency_incident`, `fire_event`, `perimeter_observation`, `weather_field`, `forecast`, `outcome_label` ayrı varlıklar olsun. Her biri kaynak, gözlem/üretim/geçerlilik zamanı, geometri, sürüm ve eksiklik durumu taşısın. İki bölgeden küçük bir geçmiş olay örneklemiyle bu sözleşmenin veriyle kurulabildiğini ve Free kaynak sınırında kalabildiğini ölç; ancak sonra model ve yeni harita çıktısı geliştir.

İlk kullanıcı grubu, ölçülebilir pilot bölgesi ve dört çıktının teslim sırası kullanıcıyla netleşecek. Bunlar seçilmeden küresel doğruluk, operasyonel kullanıma uygunluk veya bir ilk model tarihi varsayılmaz.

Bu aşamalar bir 1.0 vaadi veya tarihlendirilmiş sürüm sözü değildir. USGS'nin [yangın olasılığı değerlendirmesi](https://www.usgs.gov/data/evaluations-fsim-burn-probability-maps-pyromes-conterminous-united-states-based-observed) de tarihsel olasılık haritalarını sonraki gerçek çevrelerle karşılaştırma gereğini örnekler.
