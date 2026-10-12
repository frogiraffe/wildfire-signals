# CWFIS durum zaman dizisi denemesi

Yerel tarihsel CWFIS kayıtları için `fire_public.status_series` yalnızca seçilen karar anında alınmış sürümleri okur. `OC` (kontrol dışı), `BH` (sınırları içinde tutuluyor) ve `UC` (kontrol altında) **kurumun bildirdiği durum aralıklarıdır**. Aralık süreleri yangının fiziksel yanma süresi, yanmış alanı veya sönme olasılığı değildir. Kaynak tarihleri ile uygulamanın kayıtları aldığı tarih ayrı tutulur; son aralıktan sonra durum bilinmiyor kalır.

```bash
python -m fire_public.status_series \
  --db /path/to/history.sqlite3 \
  --source-id 0_SK_003464 --as-of 2026-10-12T04:00:00Z
```

12 Ekim 2026'da alınan iki küçük tarihsel örnekten `0_SK_003464` için dört ardışık kayıt çıktı: toplam 100 saat `OC`, 96 saat `UC` olarak bildirilen **kaynak aralığı**. İki durum geçişinden biri `UC → OC` idi. Dolayısıyla `UC` durumunu “yangın söndü” gibi nihai etiket yapmak bu örnekte doğrudan yanlış olur. `0_SK_003423` için yalnızca bir `UC` aralığı vardı; bunun sonrasına dair sonuç yok. Her iki yangının 2019'daki durum kayıtları uygulama tarafından ancak 2026'da alındığı için 2019 karar anı sorgusu sıfır girdi döndürdü. Bunlar model değerlendirmesi veya genel Kanada oranı değildir.

Denetim aynı başlangıç tarihine ait daha sonra alınmış düzeltmeyi ayrı sürüm olarak tutar ve sorgu anında erişilen son sürümü seçer. Aralıklar arasındaki boşlukları ve örtüşmeleri doldurmaz; `gaps` ve `overlaps` olarak raporlar. `prediction` ve `extinguishment_label` alanları `null` kalır. CWFIS, kurum bildirimlerinin güncelliğinin yerel kuruma ve aktarım zamanına bağlı olduğunu [açıklar](https://cwfis.cfs.nrcan.gc.ca/en/faq).
