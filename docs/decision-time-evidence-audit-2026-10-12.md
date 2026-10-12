# Karar anındaki kanıt denetimi

Bu, yerel ABD/Kanada olay arşivi ile tek noktalı NWS tahmin arşivinin **geçmiş karar anında** birlikte kullanılabilir olup olmadığını okuyan bir araştırma aracıdır. Arşivleri değiştirmez; model eğitmez, sonuç etiketi veya yangın tahmini üretmez.

```bash
python -m fire_public.decision_evidence \
  --events-db /path/to/events.sqlite3 \
  --weather-db /path/to/weather.sqlite3 \
  --provider cwfis --source-id 0_SK_003464 \
  --decision-at 2026-10-12T04:00:00Z \
  --weather-source-id TOP/32,81
```

Olay ve hava kaynak kimlikleri açıkça verilir. Kurum ve hava kayıtlarının `observed_at` ve `captured_at` saatleri karar anından ileri olamaz. Hava noktasının o ana dek alınmış bir kurum durum kaydındaki noktaya uzaklığı 5 km'yi aşamaz; bu yalnızca pilotun **yakınlık kapısıdır**, aynı yangın veya aynı hava hücresi kanıtı değildir. Hava kaydında karar anını kapsayan, doğru birimli ve geçerli rüzgâr hızı, sıcaklık ve bağıl nem değerleri bulunmalıdır. Daha sonra alınmış çevre veya durum kayıtları girdi kimlikleri listesine girmez. Eksikler `exclusions` alanında nedenleriyle görünür. `joint_input_available` yalnızca bu dar zaman/konum/değer kapısını anlatır; `model_ready` daima `false` kalır.

12 Ekim 2026 yerel denemesinde `cwfis:0_SK_003464` için 00:00 UTC kararında sıfır kurum girdisi vardı: tarihsel kaynak kayıtları uygulama tarafından henüz alınmamıştı. 04:00 UTC kararında dört kurum gözlemi bulunuyordu; Kansas'taki NWS grid noktası olay noktasından yaklaşık **1.921 km** uzaktaydı. Hava girdisi `weather_point_too_far` nedeniyle dışlandı. Bu iki denetimden **sıfır** birleşik eğitim girdisi çıktı. Her iki SQLite dosyası ve ham yanıtlar yerelde kaldı; açık Git deposuna veya Workers KV'ye eklenmedi.

Alım zamanları yerel saat beyanıdır; harici güvenilir zaman damgası yoktur. 5 km eşiği modelin mekânsal çözünürlüğünü veya meteorolojik temsil gücünü doğrulamaz. Olay etiketlerinin kapsamı, müdahale ve çevre serileri, doğru hava ufku, kaynak eksik dönemleri, geçmiş veri hakları ve ileriye dönük değerlendirme henüz kurulmadığı için bu denetimden model başarısı ya da risk yüzdesi çıkarılamaz.
