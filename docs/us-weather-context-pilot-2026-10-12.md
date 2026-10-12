# ABD olayları için hava bağlamı pilotu

Durum: taslak PR dalında uygulandı. Bu kart, yangının gelecekteki yönünü, büyüklüğünü veya sönmesini tahmin etmez.

## Kullanıcıya gösterilen veri

NIFC WFIGS kurum olayı açıldığında tarayıcı, olayın **kayıtlı nokta konumu** için [NOAA/NWS `/points` ve grid forecast API](https://www.weather.gov/documentation/services-web-api) üzerinden iki istekte bulunur. NWS grid tahmininin şimdi, 6, 12 ve 24 saat sonraki rüzgâr hızı/yönü/hamlesi, sıcaklığı ve bağıl nemi gösterilir. Yağış, kendi kaynak geçerlilik aralığına ait **tahmini miktar** olarak yazılır; gözlenmiş toplam veya anlık hız gibi sunulmaz. Eksik/değişmiş birim, sıfıra çevrilmez.

Kaynak güncelleme zamanı, tarayıcının alma zamanı ve her satırın örnekleme zamanı görünür. Rüzgâr, hamle, sıcaklık ve nemin **ayrı kaynak geçerlilik aralıkları** satırda açılabilir; aynı saatte gösterilmeleri kaynak aralıklarının aynı olduğu anlamına gelmez. Kaynak güncellemesi 12 saatten eskiyse uyarı çıkar. Negatif rüzgâr/yağış, yüzde 100'ü aşan nem ve geçersiz yön değerleri eksik sayılır. Olay koordinatı ile NWS grid hücresinin temsil ettiği konum aynı hassasiyette değildir; yangın çevresindeki mikroiklim ölçülmez. Kart ABD NWS kapsaması ve NIFC olaylarıyla sınırlıdır. Kanada/Türkiye için veri veya sonuç üretmez.

## Kaynak ve bütçe sınırı

NWS, API verisinin ücretsiz ve her amaçla kullanılabilir olduğunu, ancak kötüye kullanımı önleyen açıklanmamış makul hız sınırları bulunduğunu [belgeliyor](https://www.weather.gov/documentation/services-web-api). İstekler yalnızca kullanıcı olay ayrıntısını açtığında **tarayıcıdan doğrudan** yapılır; GitHub toplayıcısı, Cloudflare KV ve ücretli servis kullanılmaz. Yanıtların HTTP önbellek başlıkları tarayıcı tarafından kullanılabilir. İstek başarısızsa kart “kullanılamıyor/bilinmiyor” der.

12 Ekim 2026'da örnek ABD noktası `39.7456,-97.0892` sorgusunda `/points` JSON yanıtı 3.928 bayt, grid forecast JSON yanıtı 240.206 bayttı; bu **tek nokta ve tek anın** aktarım ölçüsüdür, ölçekli maliyet kanıtı değildir. Grid yanıtında gereken altı alan (`windSpeed`, `windDirection`, `windGust`, `temperature`, `relativeHumidity`, `quantitativePrecipitation`) bulundu. Şema, birim ve eksik değerler sonraki çalışmalarda değişebilir.

## Model verisi için açık kapı

Tarayıcı isteği tarihsel eğitim arşivine yazılmaz. Ayrıca geliştirilen **ayrı ve elle çalıştırılan yerel arşiv pilotu**, seçilmiş bir NWS nokta/grid yanıtını ham SHA-256 dosyaları, manifest ve SQLite `weather_forecast_snapshot` kaydı olarak saklar. Kaynak `updateTime` alanını, gerçek alım saatini ve altı değişkenin kendi geçerlilik aralıklarını ayırır. `as_of` sorgusu alım saatinden önce bu tahmini vermez. Hava kaydı otomatik olarak bir `fire_event` ile eşleşmez.

```bash
python -m fire_public.weather_pilot --latitude 39.7456 --longitude -97.0892 \
  --db /tmp/wildfire-weather.sqlite3 --raw-dir /tmp/wildfire-weather-raw
python -m fire_public.weather_pilot --replay \
  --db /tmp/wildfire-weather-replay.sqlite3 --raw-dir /tmp/wildfire-weather-raw
```

12 Ekim 2026 01:07 UTC'deki tek noktalı çalışmada NWS kaynağının `updateTime` değeri 11 Ekim 23:36:19 UTC, uygulamanın grid yanıtını aldığı zaman 12 Ekim 01:07:56 UTC idi. O iki an arasındaki karar sorgusu **sıfır** kayıt döndürdü; alımdan sonraki sorgu bir kayıt döndürdü. Nokta ve grid ham JSON yanıtları sırasıyla 3.928 ve 240.206 bayt, sıkıştırılmış toplam 11.464 bayt, SQLite dosyası 73.728 bayttı. Ağsız yeniden kurulum aynı veritabanını bayt düzeyinde üretti. Bunlar tek nokta ölçüsüdür; bölgesel maliyet, kaynak sürekliliği veya model başarısı kanıtı değildir. Ham veri bu açık Git deposuna eklenmedi ve Workers KV'ye yazılmadı.

NWS kaynak güncelleme zamanı, uygulamanın o tahmini güncelleme anında **aldığını kanıtlamaz**. Gelecekteki model örneği için üretim/güncelleme ve alım saatleri, ham özet, birim/geçerlilik aralığı ve kaynağın eksik kaldığı zamanlar birlikte saklanmalıdır. NWS grid tahmini gerçek hava gözlemi değildir; rüzgâr, yakıt, arazi ve müdahale etkisi birlikte ölçülmeden yayılım veya sonlanım yüzdesi yayımlanmaz.

Manifestteki `manifest_sha256`, kazara yapılan alan değişikliklerini yeniden kurulumda yakalar. Bu yerel dosya harici bir zaman damgası veya imza değildir: dosyaları değiştirebilen biri özeti yeniden hesaplayabilir. `captured_at` yerel saat tarafından bildirilen alım zamanıdır; bağımsız alım kanıtı olmadığı için bu pilotun kayıtları bilimsel geriye dönük sınamada doğrulanmış geçmiş tahmin olarak kullanılmamalıdır. Sürekli arşiv aşamasında güvenilir zaman kaydı ve değiştirilemez alım günlüğü ayrıca tasarlanacaktır.
