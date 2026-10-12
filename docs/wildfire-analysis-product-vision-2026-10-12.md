# Wildfire Signals: yangın analizi ürün hedefi

Durum: ürün hedefi ve aşamalı uygulama planı, 12 Ekim 2026. Bu belge önceki [gözlem inceleme planının](analysis-product-2026-10-12.md) üstündedir. Mevcut çalışan harita bu hedefin yalnızca veri toplama ve gözlem gösterme bölümünü karşılar. Aşağıdaki olasılıklar ve yayılım tahminleri bugün üründe yoktur.

## Kullanıcının alacağı yanıt

Bir kullanıcı seçtiği bölge ve zaman için şu dört soruyu sorabilmelidir:

1. **Şu anda nerede yangın var?** Kurumca bildirilen aktif orman/arazi yangınını, henüz doğrulanmamış uydu termal adayını ve yangın dışı sıcak kaynağı ayrı göster. Kaynağı, son doğrulama zamanını, konum belirsizliğini, varsa çevre sınırını ve çelişen kanıtı göster. “Kayıt yok” ile “yangın yok” aynı şey değildir.
2. **Yangın yoksa burada yangın oluşma olasılığı nedir?** Açık bir hedef tanımla: örneğin belirli coğrafi hücrede önümüzdeki 24 saatte bağımsız kaynakla kayda geçen yeni *arazi yangını* olasılığı. Yangın havası/tehlike endeksini doğrudan olay olasılığı gibi sunma; tutuşma nedenleri ve gözlem eksikliği ayrıca ele alınmalıdır.
3. **Aktif yangın nereye ve ne kadar ilerleyebilir?** Belirli 6/12/24 saat ufuklarında olası yayılım alanlarını, belirsizlik aralığını ve veri geçerlilik saatini göster. Rüzgâr tek başına yayılım tahmini değildir; başlangıç çevresi veya konumu, yakıt/bitki örtüsü, topoğrafya, nem, yağış ve müdahale bilgisi gereken girdilerdir. Bu girdiler yoksa “tahmin üretilemiyor” de.
4. **Yangının sönme veya etkin kalma olasılığı nedir?** Önce olay sonlanımı etiketini tanımla: son termal sinyal, kurumca kontrol altına alınma ve tamamen söndürülme farklı durumlardır. Yeterli ve zamanlı olay/müdahale geçmişi olmadan sayısal olasılık gösterme. Çıktı verilebildiğinde belirli zaman ufku, belirsizlik ve hangi sonlanımın tahmin edildiği görünür olmalıdır.

Amaç yangın yönetimine yardımcı **kanıtlı durum ve olasılık bilgisi** sunmaktır. Acil müdahale kararını otomatikleştirme veya resmî kurumun yerini alma iddiası değildir.

İlk hedef kullanıcı **genel kullanıcıdır**; analiz yine ayrıntılı ve derin olmalıdır. Harita ilk bakışta anlaşılır bir yanıt verir. Her sonucun ayrıntı görünümü kaynakların zaman çizelgesini, verinin nasıl eşleştirildiğini, hava/arazi girdilerini, model ve referans karşılaştırmasını, belirsizliği, eksik veriyi ve geçmiş doğruluk ölçümünü açar. Tek bir renk veya puan bu açıklamanın yerine geçmez.

Taslak PR'daki kayıt ayrıntısı artık bu dört soruyu birlikte gösterir. İlk soruda yalnızca kurumun bildirdiği durumu veya doğrulanmamış uydu adayını belirtir; kaynak başarısızlığı, eski toplama görüntüsü ve kaynak zamanı görünür. Diğer üç soruda bölgesel model ve ilgili veri kapıları geçilmediğinden doğrulanmış olasılık bulunmadığını ve eksik girdiyi açıkça gösterir. Bu, dört analizin tamamlandığı veya yangının mevcut davranışının ölçüldüğü anlamına gelmez.

## Veri ve ürün sınırları

| Girdi | Üründeki görevi | Şimdiki durum |
| --- | --- | --- |
| NASA FIRMS uydu tespitleri | Erken aday sinyali ve zaman dizisi | NOAA-20/21 0,05° hücre/saat adayları toplanıyor; yangın doğrulaması değil. |
| Resmî olay kayıtları ve yangın çevreleri | Olay kimliği, durum ve bağımsız değerlendirme etiketi | NIFC/CWFIS olayları ayrı toplanıyor; küresel kapsam ve çevre geçmişi yok. |
| Hava durumu ve tahmini | Oluşma koşulu, yayılım ve sonlanım girdisi | [ABD NIFC olay ayrıntısında 6/12/24 saatlik tahmini hava değişimi ve tek noktalı yerel NWS arşiv pilotu](us-weather-context-pilot-2026-10-12.md) var; sürekli model girdisi arşivi, Kanada/Türkiye kapsamı ve hava etkisi değerlendirmesi yok. |
| Yakıt/bitki, arazi örtüsü, topoğrafya ve kuraklık | Yayılım ve oluşma modellerinin yerel girdileri | Açık depoda bütünleşik katman yok; çözünürlük, lisans ve güncellik araştırılacak. |
| Yıldırım, insan etkinliği ve müdahale/containment geçmişi | Tutuşma ve sonlanım tahmini için olası girdiler | Kapsam ve güvenilirlik bölgeye göre araştırılacak; eksikse model hedefi daraltılacak. |
| Tarihsel yangın olayları ve çevreleri | Eğitim, geçmişe dönük sınama ve karşılaştırma | Mevcut 72 saatlik harita saklaması bunun için yeterli değil. |

## Zorunlu derin analiz işlevleri

- **Hava etkisi ve senaryoları:** aynı yangın için rüzgâr yönü/hızı/hamlesi, sıcaklık, bağıl nem ve yağışın zamanla değişimini gerçek gözlemlerle açıklayıp 6/12/24 saatlik alternatif hava senaryolarını karşılaştır. Senaryo çıktısını gerçekleşecek hava tahmini veya nedensel kanıt olarak sunma; girdinin kaynağı, üretim saati ve değiştirilen varsayım görünsün.
- **Olayın zaman çizelgesi:** yeni tespit, kurum teyidi, çevre ve alan değişimi, duraklama, yeniden alevlenme, kontrol altına alınma ve söndürülme durumlarını zaman damgalı göster. Alan artışı, ilerleme yönü/hızı ve durum değişimini kaynak kapsamı ile birlikte istatistiksel olarak çözümle; termal sinyal sayısını doğrudan yanmış alan veya yangın şiddeti sayma.
- **Olası etki alanı:** seçilen yangın ve zaman ufku için olası ulaşım alanı, varış zamanı ve belirsizlik aralığı göster; mevcut yangın çevresi ile gelecekteki olası alanı ayır. Yerleşim/altyapı kesişimi ancak ilgili katmanların kapsamı ve güncelliği doğrulandığında eklenir.
- **Arazi ve yol etkisi:** yükseklik, eğim, bakı, yakıt/bitki örtüsü, yol türü/genişliği, çevredeki yakıt sürekliliği ve mümkünse müdahale bilgisini ayrı girdiler olarak değerlendir. Yolları mutlak yangın bariyeri kabul etme; yangının yolu aşması ve yolun müdahale erişimine katkısı ayrı etkiler olarak sınanır. ABD için [3DEP yükseklik](https://www.usgs.gov/3d-elevation-program) ve [LANDFIRE arazi/yakıt](https://landfire.gov/topographic/aspect) olası kaynaklardır; Kanada ve Türkiye için eşdeğer katman, lisans ve çözünürlük ayrıca araştırılır. [US Forest Service'in yakıt şeridi değerlendirmesi](https://research.fs.usda.gov/treesearch/81184), yol kenarındaki şeritlerin tek başına yangını nadiren durdurduğunu bildirir.
- **Tarihsel benzer olaylar:** geçmiş yangınları hava, mevsim, yakıt, arazi ve başlangıç durumu bakımından karşılaştır; benzer olayları açıklayıcı örnek olarak göster. Benzerlik tek başına olasılık veya güvenilir yayılım tahmini sayılmaz.

## Öğrenmeye uygun tarihsel veri yöntemi

Canlı haritanın yedi gün sonra silinen KV anlık görüntüleri, eğitim/veri arşivi değildir. Geriye dönük alınmış **nihai** yangın çevresi yalnızca son etiket olarak kullanılabilir; o günkü model girdisi gibi kullanılırsa gelecek bilgisi geçmişe sızar. ABD'deki [MTBS](https://mtbs.gov/) büyük yangınların nihai çevrelerini içerir ve boyut eşiği nedeniyle bütün küçük yangınları temsil etmez. Kanada'nın [CNFDB](https://cwfis.cfs.nrcan.gc.ca/en/fire-history) olay noktaları ve kurumların haritaladığı çevreleri içerir; tarihsel çevrelerin olay boyunca hangi saatte bilindiği ayrıca doğrulanmalıdır. [ERA5 saatlik yeniden analiz](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download) tarihsel hava için adaydır; o tarihte gerçekten yayımlanmış tahminin yerine geçmez.

Veri sözleşmesinde olay kimliği altında değiştirilemeyen gözlem kayıtları tut: `source_observation`, `incident_status`, `perimeter_observation`, `weather_observation`, `weather_forecast_run`, `terrain_tile_version`, `fuel_tile_version`, `road_tile_version`, `intervention_observation`, `outcome_label` ve `model_prediction`. Her kayıtta sağlayıcı/lisans, kaynak kimliği, geometri ve koordinat sistemi, olay/gözlem zamanı, ilk erişilebilir olduğu zaman, alma zamanı, yayımlama veya tahmin üretim zamanı, geçerlilik zamanı, veri sürümü, kalite/eksiklik durumu ve ham kaynağın denetlenebilir özeti bulunur. Düzeltmeler eski kaydı silmez; yeni sürüm ekler. Tahmin de girdi sürümleriyle ve model sürümüyle birlikte dondurulur.

Önerilen ilk saklama deneyi: küçük, izinli ABD ve Kanada olay örneklerinde normalize olay/zaman tabloları için **SQLite**, büyük hava/arazi dilimleri için tarih ve bölgeye bölünmüş sıkıştırılmış dosyalar; bunların manifest, sağlama toplamı ve üretim betiği ayrı tutulur. Dosya biçimi ve sürekli barındırma yeri, örnek veri boyutu, erişim hakkı, geri yükleme ve ücretsiz kota ölçülünce seçilir. Büyük tarihsel veri Git geçmişine veya Workers KV'ye konmaz; bu açık depoya özel depodaki veri kopyalanmaz. Türkiye için resmî olay/çevre tarihi ve yeniden kullanım hakkı doğrulanmadan eğitim kapsamı iddia edilmez.

İlk [karar anı kanıt denetimi](decision-time-evidence-audit-2026-10-12.md), yerel kurum ve NWS arşivlerini yalnızca açıkça seçilen olay/hava kimliğiyle, alım zamanı, nokta uzaklığı, birim ve tahmin geçerliliği kapılarından geçirir. İlk tarihsel örnekte birleşik eğitim girdisi çıkmadı; bu sonuç veri toplama ve güvenilir zaman kaydı ihtiyacını somutlaştırır, model denemesi değildir.

Her eğitim örneği `(olay, karar zamanı, ufuk, o anda erişilebilir girdiler, sonradan ölçülmüş sonuç)` biçimindedir. Tutuşma, 6/12/24 saatlik çevre değişimi, belirli alana varış ve `kontrol_altında`/`söndü` ayrı hedeflerdir. Etiketsiz veya izlenemeyen dönemler negatif örnek sayılmaz. Olay, yıl ve bölge bazında ayrılmış geçmiş sınamalar; en basit kalıcılık, tarihsel taban oranı ve mevcut bilimsel referansla karşılaştırma; olasılık kalibrasyonu ve coğrafi hata ölçümü gerekir. Bu sınamalar geçmeden “% sönme” veya “şu alana ulaşır” gibi kesin ürün çıktısı açılmaz.

Sosyal medya veya haberler resmî olayla otomatik eşitlenmez. Konum, olay zamanı, tür ve kullanım hakkı doğrulanmadan yalnızca insan incelemesine açık kanıt olabilir. Quesería'daki araç yangını ile yaklaşık 455 km uzaktaki uydu adayı aynı olay sayılmamalıdır. NASA, termal anomalilerin yangın dışı sıcak kaynaklardan da gelebileceğini ve bulutların yangınları gizleyebileceğini [açıkça belirtiyor](https://firms.modaps.eosdis.nasa.gov/map2/).

Bu herkese açık depoya özel geliştirme deposunun kodu, veritabanı, anahtarı veya geçmişi taşınmaz. Özel model çalışması ayrı sınırda değerlendirilir; yalnızca yayımlanması uygun, denetlenmiş veri/sonuç sözleşmesi burada kullanılır. Workers/KV Free ve mevcut GitHub kaynak sınırları aşılmadan mimari seçilir.

## Aşamalar ve geçiş ölçütleri

Dört ana yanıt ve yukarıdaki derin analiz işlevleri **tek ürünün** hedefindedir. Geliştirme ve yayımlama aşamalıdır: her yanıt yalnızca kendi veri ve değerlendirme kapısını geçince aynı arayüzde açılır. Henüz doğrulanmamış işlevler çalışıyormuş gibi gösterilmez. Aşağıdaki sıra, veri ve bilimsel doğrulama bağımlılıklarını anlatır; kullanıcının hangi işlevi daha değerli bulduğunu sıralamaz.

1. **Olay zemini:** uydu adayından ayrı, zaman içinde kimliği korunan kurum olayı; kaynak tazeliği, olay türü, çevre ve kanıt bağlantıları. Pilot coğrafyalar ABD, Kanada ve Türkiye'dir. ABD/Kanada'da mevcut NIFC/CWFIS olay kayıtlarıyla ilk ölçüm kurulur; Türkiye'de bağımsız resmî olay akışı, geçmiş çevreler ve yeniden kullanım hakkı ayrıca doğrulanır. Bir bölgede doğrulanan model diğerine otomatik taşınmaz; küresel harita kapsamı, küresel model doğruluğu iddiası yaratmaz. İlk geçiş: yanlış eşleşme ve kaçan olaylar bölge bazında bağımsız veriyle ölçülür.
2. **Tarihsel ve çevresel veri:** yukarıdaki sürümlü olay arşivini küçük örneklemde kur; olay/çevre zaman dizisi, hava, yakıt, topoğrafya ve yolları aynı konum ve *o anda bilinen* zamanla birleştir. Sağlayıcı hakları, güncellik, eksik aralık, indirme boyutu, geri yükleme ve Free kota pilotu geçilmeden sürekli toplama açılmaz.
3. **Yangın oluşma olasılığı:** önce hava/kuraklık koşullarını açıklayıcı göster; sonra yeni olay hedefi için basit tarihsel taban oranı ile model karşılaştırması yap. Negatif örneklerin gözlem kapsamı belgelenir. Farklı yıl ve bölgelerde geriye dönük sınama, kalibrasyon ve ileriye dönük izleme olmadan yüzde yayımlanmaz.
4. **Aktif yangın yayılımı:** başlangıç çevresi ve çevresel girdiler olan olaylarda önce referans/senaryo modeli, ardından olasılıksal alanlar ve farklı hava koşullarının karşılaştırması. Eğim, bakı, yakıt ve yol etkileri ayrı hata analizleriyle sınanır. Rüzgâr oku bir yayılım modeli yerine geçmez. Geçmiş çevre ilerlemesiyle mekânsal örtüşme, varış zamanı hatası ve güven aralığı kapsamı ölçülür. [US Forest Service FARSITE çalışması](https://research.fs.usda.gov/treesearch/27413) hava/rüzgâr değişimi ile arazi verisinin birlikte gerektiğini gösterir.
5. **Sönme/etkin kalma:** kurumların “aktif”, “kontrol altında” ve “söndü” kayıtları yeterli ve karşılaştırılabilirse zaman ufuklu sonlanım modeli; aksi halde yalnızca gözlenen son durum ve belirsizlik. Müdahale verisi yoksa bunun etkisi ölçülmeden kesin sonuç söylenmez.
6. **Ürün kapısı:** her ayrı çıktı için kaynak kapsaması, gecikme, eksik dönemler, referans model karşılaştırması, kalibrasyon ve ileriye dönük performans raporu. Başarısız veya etiketsiz çıktılar arayüzde “bilinmiyor/deneysel” olarak kalır. Yedi günlük toplama sürekliliği ve gerçek cihaz deneyimi ayrıca doğrulanır.

## İlk somut sonraki iş

İlk uygulama parçası **olay ve doğrulama veri sözleşmesi** ile küçük bir ABD/Kanada tarihsel örneklemidir. Mevcut `satellite_candidate` ve `agency_incident` kayıtlarını birbirine dönüştürmeden `fire_event` kimliği ve yukarıdaki sürümlü gözlem/sonuç kayıtlarına bağla. Örneklemde en az bir çevresi zaman içinde değişen, bir çevresi yalnızca nihai durumda bulunan ve bir çevre verisi bulunmayan olay seç. Her biri için kaynak hakkını ve ham veri özetini kaydet; belirli bir geçmiş karar anında erişilebilir girdileri yeniden kur, sonradan bilinen sonucu ayrı tut, eksik dönemleri raporla. Sıkıştırılmış boyutu, geri yüklemeyi ve Free kaynak sınırını ölç. Bunlar gösterilmeden model eğitimi veya yeni harita tahmini açma.

İlk kullanıcı grubu genel kullanıcı, pilot coğrafyalar ABD/Kanada/Türkiye ve dört ana analizin tamamı hedef olarak seçildi. Bunlar tek üründe aşamalı geliştirilecek. Kullanıcının ayrıca istediği hava senaryoları, derin zaman serisi analizi, geçmişten öğrenen veri arşivi, olası etki alanı ve arazi/yol etkileri yukarıdaki gereksinimlere dahildir. Bölgesel veri ve değerlendirme kapıları geçilmeden küresel doğruluk, operasyonel kullanıma uygunluk veya bir ilk model tarihi varsayılmaz.

Bu aşamalar bir 1.0 vaadi veya tarihlendirilmiş sürüm sözü değildir. USGS'nin [yangın olasılığı değerlendirmesi](https://www.usgs.gov/data/evaluations-fsim-burn-probability-maps-pyromes-conterminous-united-states-based-observed) de tarihsel olasılık haritalarını sonraki gerçek çevrelerle karşılaştırma gereğini örnekler.
