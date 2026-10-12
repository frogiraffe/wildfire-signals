# ABD olayları için hava bağlamı pilotu

Durum: taslak PR dalında uygulandı. Bu kart, yangının gelecekteki yönünü, büyüklüğünü veya sönmesini tahmin etmez.

## Kullanıcıya gösterilen veri

NIFC WFIGS kurum olayı açıldığında tarayıcı, olayın **kayıtlı nokta konumu** için [NOAA/NWS `/points` ve grid forecast API](https://www.weather.gov/documentation/services-web-api) üzerinden iki istekte bulunur. NWS grid tahmininin şimdi, 6, 12 ve 24 saat sonraki rüzgâr hızı/yönü/hamlesi, sıcaklığı ve bağıl nemi gösterilir. Yağış, kendi kaynak geçerlilik aralığına ait **tahmini miktar** olarak yazılır; gözlenmiş toplam veya anlık hız gibi sunulmaz. Eksik/değişmiş birim, sıfıra çevrilmez.

Kaynak güncelleme zamanı, tarayıcının alma zamanı ve her satırın örnekleme zamanı görünür. Rüzgâr, hamle, sıcaklık ve nemin **ayrı kaynak geçerlilik aralıkları** satırda açılabilir; aynı saatte gösterilmeleri kaynak aralıklarının aynı olduğu anlamına gelmez. Kaynak güncellemesi 12 saatten eskiyse uyarı çıkar. Negatif rüzgâr/yağış, yüzde 100'ü aşan nem ve geçersiz yön değerleri eksik sayılır. Olay koordinatı ile NWS grid hücresinin temsil ettiği konum aynı hassasiyette değildir; yangın çevresindeki mikroiklim ölçülmez. Kart ABD NWS kapsaması ve NIFC olaylarıyla sınırlıdır. Kanada/Türkiye için veri veya sonuç üretmez.

## Kaynak ve bütçe sınırı

NWS, API verisinin ücretsiz ve her amaçla kullanılabilir olduğunu, ancak kötüye kullanımı önleyen açıklanmamış makul hız sınırları bulunduğunu [belgeliyor](https://www.weather.gov/documentation/services-web-api). İstekler yalnızca kullanıcı olay ayrıntısını açtığında **tarayıcıdan doğrudan** yapılır; GitHub toplayıcısı, Cloudflare KV ve ücretli servis kullanılmaz. Yanıtların HTTP önbellek başlıkları tarayıcı tarafından kullanılabilir. İstek başarısızsa kart “kullanılamıyor/bilinmiyor” der.

12 Ekim 2026'da örnek ABD noktası `39.7456,-97.0892` sorgusunda `/points` JSON yanıtı 3.928 bayt, grid forecast JSON yanıtı 240.206 bayttı; bu **tek nokta ve tek anın** aktarım ölçüsüdür, ölçekli maliyet kanıtı değildir. Grid yanıtında gereken altı alan (`windSpeed`, `windDirection`, `windGust`, `temperature`, `relativeHumidity`, `quantitativePrecipitation`) bulundu. Şema, birim ve eksik değerler sonraki çalışmalarda değişebilir.

## Model verisi için açık kapı

Bu tarayıcı isteği tarihsel eğitim arşivine yazılmaz. NWS kaynak güncelleme zamanı, uygulamanın o tahmini geçmişte **aldığını kanıtlamaz**. Gelecekteki model örneği için tahmin yanıtı ham özet, kaynak sürümü, üretim/güncelleme, alım ve geçerlilik saatleriyle ayrıca saklanmalı ve karar anında erişilebilirliği sınanmalıdır. NWS grid tahmini gerçek hava gözlemi değildir; rüzgâr, yakıt, arazi ve müdahale etkisi birlikte ölçülmeden yayılım veya sonlanım yüzdesi yayımlanmaz.
