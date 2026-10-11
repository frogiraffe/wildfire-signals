# Wildfire Signals çalışma bağlamı

Bu klasör `frogiraffe/wildfire-signals` herkese açık Git deposudur ve Wildfire Signals haritası ile açık veri toplayıcısının **ana çalışma klasörüdür**. Kullanıcı Codex'i bu proje için burada açtığında önce bu depoyu ve canlı dağıtımı esas al.

- Canlı ön izleme: `https://wildfire-signals.pages.dev/`. Statik harita Cloudflare Pages'te; `/api/*` Pages Function ve Workers KV Free kullanır. NASA FIRMS, NIFC WFIGS ve CWFIS toplaması GitHub Actions'ta çalışır. Cloudflare Free Worker Cron yalnızca eski veride aynı GitHub işini tetikler.
- Kullanıcının bilgisayarının açık kalması gerekmez. Yerel Python testi veya dosya düzenleme, canlı toplayıcının bu bilgisayarda çalıştığı anlamına gelmez. Yerel Docker/model çalıştırma varsayma ve bu proje için Docker başlatma; önce açıkça gerekli olup olmadığını değerlendir. İş bitince başlatılmış yerel süreç bırakma.
- Canlı durum, başarı, kesinti, veri yaşı ve maliyet hakkında konuşmadan önce GitHub Actions, Pages API ve ilgili Cloudflare Free göstergelerini **o an** kontrol et. Depodaki README, rapor ve eski sohbet sonuçları canlı kanıt değildir.
- Uydu verisi 0,05 derece/hücre/saat `satellite_candidate` kayıtlarıdır; doğrulanmış yangın sayısı değildir. NIFC/CWFIS `agency_incident` kayıtları ayrı türdür. 8 km yakınlık ilişkisi yalnızca geçicidir. Bağımsız yangın doğruluğu veya tahmin başarısı ölçülmeden 1.0 kabulü yapma.
- Kullanıcı ücretsiz kullanım istiyor. Workers Paid, R2, ücretli eklenti veya büyük GitHub runner açma. Mevcut Free kapılarını ve kota sınırlarını koru.
- Eski özel geliştirme deposu `../fire-antalya`; etkin v3 çalışma ağacı `../fire-antalya-v300-worktree`. Orada çok sayıda kullanıcıya ait kirli değişiklik ve büyük yerel veri bulunur. Özel kodu, veri tabanını, anahtarları veya geçmişi bu açık depoya kopyalama; silme, sıfırlama veya topluca taşıma yapma. Özel model çalışması istenirse depoların sınırını açıkça belirt.
- Bu klasörün kaynağı ve dağıtım ayarları için `README.md` ile `.github/workflows/` dosyalarını oku. Güncel durumu yalnızca kontrol edilmiş veriye dayanarak bildir.
