# İleriye dönük kurum kaydı alım denemesi

Mevcut GitHub Actions toplayıcısı başarılı bir kamu anlık görüntüsü yayımladığında, isteğe bağlı olarak aynı görüntüden küçük bir **araştırma alım dosyası** çıkarabilir. Yeni NIFC, CWFIS, FIRMS veya NWS isteği yapılmaz; Workers KV'ye ek veri yazılmaz. Dosya yalnızca NIFC/CWFIS olay kayıtlarını, iki kaynağın başarılı/başarısız/ertelenmiş durumunu, tarama ve gerçek alım saatlerini, GitHub çalışma kimliğini ve yayımlanan görüntünün SHA-256 anahtarını içerir. Uydu adayları ve geçici eşleşmeler dışarıda kalır.

Kod, UTC 00/06/12/18 saatlerinin :17–:59 aralığında en fazla bir normal başarılı toplamadan dosya üretmeye çalışır; 55 dakikalık toplama aralığı koruması bu pencere içinde ikinci normal taramayı engeller. Elle zorlanan onarım çalışmaları dahil edilmez. Tek dosya en fazla **128 KiB**, olay sayısı en fazla **2.000**; sınır aşılırsa dosya kesilmez, atlama nedeni çalışma günlüğüne yazılır. Dosya üretim hatası yayımlanmış haritayı geri almaz. `ENABLE_ANALYSIS_ARCHIVE=true` depo değişkeni olmadan özellik kapalıdır; taslak PR ana dala alınmadıkça çalışmaz.

İş akışı dosyayı `actions/upload-artifact@v4` ile **90 gün** saklar. Kontrol edilen depo ayarı 12 Ekim 2026'da 90 gündü. Dört dosya/gün ve 128 KiB tavanında 90 günlük **azami sıkıştırılmış dosya yükü yaklaşık 45 MiB** olur; GitHub artefakt ambalajı ve diğer depolama bu hesaba dahil değildir. [GitHub'ın güncel belgesi](https://docs.github.com/en/billing/concepts/product-billing/github-actions) Free plan artefakt alanının paketlerle paylaşıldığını, [saklama belgesi](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository) herkese açık depoda üst sınırın 90 gün olduğunu bildirir. Bu yöntem **kalıcı tarihsel veri deposu değildir**; 90 gün dolmadan dışa aktarım ve güvenilir uzun dönem saklama çözümü gerektirir.

İndirilen artefaktların `agency-*.json.gz` dosyalarını tek dizin altında toplayıp şu denetimi çalıştır:

```bash
python -m fire_public.receipt_audit /path/to/extracted-artifacts
```

Denetim dosya özetini ve boyutunu kontrol eder, dokuz saati aşan alım boşluklarını, başarısız ve ertelenmiş kurum kaynaklarını ayrı ayrı ve tekrar görülen olay kimliklerini sayar. Bir olayın sonraki aktif katmanda görünmemesini **söndü** etiketi saymaz. GitHub artefaktı ve içindeki saatler tek başına bağımsız, değiştirilemez zaman kanıtı değildir. Bu küçük kohortta hava, yakıt, arazi, çevre, müdahale ve doğrulanmış sonuç etiketleri henüz yoktur; eğitim veya olasılık yayımlama kapısı geçilmemiştir.

İndirilen dosyaları, Git dışındaki yerel SQLite araştırma arşivine aktar:

```bash
python -m fire_public.receipt_history --receipts /path/to/extracted-artifacts --db /path/outside/repo/agency-history.sqlite3
```

Aktarım her taramanın saatini ve kaynak durumunu ayrı saklar; yalnızca `complete` kurum kaynağındaki olayları yeni gözlem olarak ekler. `failed` veya `deferred` taramasında haritaya taşınan eski olay, yeni kurum teyidi sayılmaz. Aynı dosyaları yeniden aktarmak idempotenttir; aynı tarama saatine ait içerik değişirse aktarım reddedilir. `incident_at(store, provider, source_id, at=...)` belirli karar anında `listed`, `source_unavailable`, `not_listed_in_complete_scan` veya `no_receipt_yet` döndürür. Son iki durumun hiçbiri yangının söndüğünü kanıtlamaz. Bu arşiv GitHub artefaktlarının 90 gün sonra silinmesini önlemez; dışa aktarım ve yedekleme hâlâ gereklidir.
