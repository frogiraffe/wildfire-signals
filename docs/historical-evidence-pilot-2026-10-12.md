# Tarihsel olay kanıtı: ilk veri pilotu

Durum: **uygulandı ve yerel olarak sınandı**, 12 Ekim 2026. Bu pilot tahmin eğitimi veya gerçek yangın yayılımı doğrulaması değildir. [Ürün hedefinin](wildfire-analysis-product-vision-2026-10-12.md) ilk veri sözleşmesini sınar.

## Yapılan iş

- `fire_public.history.HistoryStore` kaynak olaylarını SQLite'a eklemeli kaydeder. Bir kayıt, kaynak kimliği, hak referansı, gözlem zamanı ve **uygulamanın ilk aldığı zaman** ile saklanır. `as_of` sorgusu henüz alınmamış kaydı geçmiş model girdisi gibi vermez. Aynı kaynak kaydı tekrar alındığında tekilleşir; düzeltme yeni kayıt oluşturur. Kurum olayları, kaynak kimliğinden ayrı `fire_event` kimliği ve kaynak bağlantısı alır; aynı kurum olayının durum/çevre kayıtları bu kimlikte sorgulanır. Uydu adayı ayrı türdür ve otomatik olay bağlantısı almaz.
- `fire_public.history_pilot` üç küçük resmî örnek indirir, ham JSON'u sıkıştırıp SHA-256 ile adlandırır, manifest üretir ve ağ kullanmadan yeniden SQLite oluşturabilir. Veriler Git'e, Workers KV'ye veya özel geliştirme deposundan bu depoya taşınmaz.
- Canlı haritanın yeni kurum kaydı zaman çizelgesi yalnızca **bizim gördüğümüz ilk kayıt ve en son dört kaynak kaydı değişimini** gösterir. Ad, konum, kaynak güncelleme tarihi veya kurum durumundaki değişiklik izlenir; gerçek yangın çevresi veya büyüme geçmişi olduğunu söylemez. Bir kaynak başarısız olduğunda kaydın kaybolması “söndü” olayı oluşturmaz.

## Ölçülen örneklem

12 Ekim 2026 00:44 UTC'de resmî servislerden sınırlı sorgularla şu kayıtlar alındı:

| Olay | Kaynak ve kayıt türü | Pilotun gördüğü kayıt | Sınır |
| --- | --- | ---: | --- |
| `0_SK_003464` | [CWFIS zamanlı aktif olay katmanı](https://cwfis.cfs.nrcan.gc.ca/downloads/docs/en/references/cwfif/cwfis-data-placemat.pdf) | 4 durum aralığı | 2019 tarihleri geçmişte bu uygulama tarafından görüldüklerini kanıtlamaz. |
| `0_SK_003423` | Aynı CWFIS katmanı | 1 durum aralığı | Bu pilot bu olay için çevre sorgulamadı; “çevre yok” iddiası değildir. |
| `{EFB046E9-CE8C-4DE6-87A7-E824C33AE187}` | [NIFC WFIGS çevre katmanı](https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/services/WFIGS_Interagency_Perimeters/FeatureServer/0) | 1 çevre | Sonradan erişilen çevre, eski tarihteki tahmine girdi olamaz. |

Altı normalleştirilmiş kayıt ilk şemada 45.056 bayt SQLite dosyası oluşturdu. Üç ham yanıtın sıkıştırılmış toplamı iki ardışık çalışmada 7.016 ve 7.015 bayttı. Ham yanıtların sağlama toplamları yeniden açıldığında doğrulandı; ağsız yeniden kurulan veritabanında aynı altı gözlem kimliği üretildi. Bu ilk çalışmadaki manifest sürümü 1 alma zamanını sorgular başlamadan kaydettiği için `as_of` kanıtı olarak kullanılmamalıdır. Sürüm 2 her yanıtın alınması tamamlandıktan sonraki zamanı ayrı kaydeder. 00:48 UTC'deki yeni sürüm çalışması yine altı kayıt ve 7.016 bayt sıkıştırılmış ham yanıt üretti. Sonradan eklenen olay kimliği şemasıyla aynı ham dosyalardan iki ağsız yeniden kurulum yapıldı: her biri 61.440 bayt ve bayt düzeyinde aynıydı. Bunlar **yalnızca üç olaylık pilotun** ölçüleridir; yıllık/bölgesel depolama maliyeti veya Free kota kanıtı değildir.

Önemli bulgu: CWFIS'in ham WFS yanıtındaki teknik `feature.id` iki ardışık sorgu arasında değişti. Ham SHA-256 özetleri değişirken **altı normalleştirilmiş gözlem kimliği aynı kaldı**. Teknik `feature.id` model olayı veya durum değişimi sayılmaz; ham yanıt özeti manifestte ayrı tutulur. Ham yanıtlar bu depoya eklenmedi; manifest tek başına gelecekte aynı verinin yeniden indirilebileceği garantisi değildir.

Kanada'nın [Open Government Licence](https://cwfis.cfs.nrcan.gc.ca/downloads/licence.txt) bağlantısı kayıtta bulunur. NIFC katmanı açıkça erişilebilse de bu örnek için yeniden yayımlama koşulları ayrıca incelenmeden ham çevre veya türev veri yayımlanmayacak. Kaynak servisleri ileride veri düzeltebilir; manifest ve ham yanıt özeti tam olarak pilotta kullanılan sürümü izler.

## Yeniden çalıştırma

```bash
python -m fire_public.history_pilot --db /tmp/wildfire-pilot.sqlite3 --raw-dir /tmp/wildfire-pilot-raw
python -m fire_public.history_pilot --replay --db /tmp/wildfire-pilot-replay.sqlite3 --raw-dir /tmp/wildfire-pilot-raw
```

Her komut **yeni** çıktı yolları ister ve mevcut veritabanını ezmez. İlk komut resmî servisleri tekrar okur; yanıtlar değişirse sayılar da değişebilir. İkinci komut `pilot-manifest.json` ile SHA-256 doğrulanmış yerel ham yanıtları kullanır. İki komut da Cloudflare'a veri yazmaz ve bilgisayarda çalışan süreç bırakmaz.

## Geçiş kapısı

Bu pilot tarihsel durum kayıtlarının ve bir son çevrenin saklanabildiğini gösterdi. Ayrı `fire_event` kimliği vardır; şimdilik her kurum kaynak kimliği kendi olayına bağlanır. **Kurumlar arası veya uydu adayıyla doğrulanmış eşleme yoktur.** Henüz olay boyunca ardışık **güvenilir çevre geometrileri**, o gün yayımlanmış hava tahminleri, arazi/yakıt katmanları, Türkiye için hakları doğrulanmış resmî geçmiş, uzun süreli ücretsiz arşiv veya bağımsız tahmin başarısı yoktur. Sonraki iş, bu girdilerin küçük ve tarihsel olarak dürüst bir eğitim örneklemine bağlanması ve arşivin süreklilik/maliyet ölçümüdür; yüzde ve yayılım alanı yayımlama kapısı kapalıdır.
