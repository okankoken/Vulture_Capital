# Vulture Capital

Bir Streamlit uygulamasında BIST ve NASDAQ/NYSE piyasa araştırması. Eski iki proje yerinde korunur. Kaynak `.env`, SSH anahtarları ve diğer kimlik bilgileri kopyalanmaz.

## Kurulan yapı

- `app.py`: Fırsat radarı, piyasa radarı, hisse inceleme, ortak tarihli karşılaştırma ve veri durumu. Lacivert ve altın renkli, özel akbaba görselli kimlik.
- `vulture/bootstrap.py`: Eski SQLite dosyalarını `mode=ro` ile okur; yeni veritabanına aktarır.
- `vulture/pipeline.py`: Her İstanbul takvim gününde tek mantıksal güncelleme. Dosya kilidi eşzamanlı çalışmayı engeller; başarı kaydı aynı gün ikinci tam çekimi engeller. Yeniden deneme sadece başarısız veya tamamlanmamış sembolleri işler.
- `dags/vulture_daily.py`: Her gün **02.30 Europe/Istanbul**, önce KAP/Nasdaq Trader sembol yenileme, sonra iki piyasanın fiyatları ve en son bulut yayını. `catchup=False`, `max_active_runs=1`; geçici veri hatasında 20 dakika sonra bir yeniden deneme. Fiyatı henüz bulunmayan yeni semboller kısmi durum olarak kaydedilir; tüm yayını geciktirmez.
- `compose.yaml`: Mevcut resmi `apache/airflow:3.3.1` imajıyla bu VM için tek düğümlü Airflow Standalone. Üretim için PostgreSQL ve uygun bir auth manager ile ayrı servisler gerekir. Diğer projelerin Docker servislerini değiştirmez.
- `data/vulture.db`: Birleşik fiyat, şirket, özet, çalışma ve hata kayıtları. Git'e alınmaz.
- `vulture/snapshots.py`: HTTPS depolamaya aktarılabilecek tutarlı sıkıştırılmış SQLite kopyası ve SHA-256 manifesti.

## Mevcut VM'de açma

Windows: **http://127.0.0.1:8502**. VirtualBox'taki mevcut `127.0.0.1:8502 → 8502` yönlendirmesi kullanılır. Eski yönlendirme kuralları değiştirilmedi. Bu port daha önce `fastapi_ml` adıyla ayrılmıştı; eski uygulama yeniden başlatılırsa port çakışması yaşamamak için yeni bir port yönlendirmesi seçilmeli.

VM'de proje: `/home/train/VultureCapital`.

```bash
cd /home/train/VultureCapital
docker compose ps
docker compose exec -T airflow airflow dags list
docker compose exec -T airflow airflow dags list-runs vulture_capital_daily
systemctl --user status vulture-capital.service --no-pager
```

Airflow API/UI yalnız VM loopback'inde `127.0.0.1:18080` üzerinden dinler. Airflow başlangıç parolası üretilir; kaynak kodda veya README'de paylaşılmaz. VM'de `runtime/airflow/simple_auth_manager_passwords.json.generated` dosyasındadır. Airflow arayüzü Windows'a ayrıca yönlendirilmemiştir.

VM açık olmalı. Docker servisi ve kullanıcı servis yöneticisi çalışıyorsa servisler yeniden başlar. Streamlit kullanıcı servisi için oturum kapalıyken ve açılışta çalışma, sistemin `linger` ayarına bağlıdır; bu ayar değiştirilmez.

## Yeni ortamda kurulum

Python 3.11+ önerilir (mevcut VM'nin Python 3.13 ortamında test edildi):

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m vulture.bootstrap --home /home/train
streamlit run app.py --server.port 8502
```

Sıfırdan başlarken `python -m vulture.symbols` güncel listeleri KAP ve Nasdaq Trader'dan oluşturur; ardından `python -m vulture.pipeline` fiyatları alır. Mevcut projelerden devralınan eski semboller ve fiyatlar korunur. Yeni ABD keşfinde test kayıtları, ETF ve varant/hak/unit/imtiyazlı türler filtrelenir. Yeni halka arz, sağlayıcıda bir geçerli fiyat barı oluşunca gösterilebilir. Yalnız son keşifte eklenenleri çekmek için `python -m vulture.pipeline --new-only` kullanılabilir; normal günlük görev tüm takip listesini işler.

## Hesaplama ve hata davranışı

- Son fiyat: ham kapanış. Getiriler ve grafik: bölünme/temettü için düzeltilmiş kapanış.
- 1 gün ve 1 hafta: 1 ve 5 işlem gözlemi. 1/3/6/12 ay: takvim ayı, hedef tarihte veya öncesindeki son gözlem.
- Bir yıllık zirve/dip: düzeltilmiş **kapanış** aralığı; gün içi yüksek/düşük değildir.
- Hacim Z: son 30 gözlemin ortalaması ve örnek standart sapması.
- Yetersiz geçmiş boş bırakılır; sıfır getiri olarak gösterilmez.
- Piyasa genişliği aynı veri tarihli hisseleri kullanır. Endeks getirisi olarak sunulmaz.
- Eski fiyatlar silinmez. Son 800 günlük veriler yeniden alınarak kurumsal işlem düzeltmeleri güncellenir. Daha eski tarihler korunur; 800 günden eski kurumsal işlem revizyonları için ayrıca geçmiş düzeltmesi gerekir.
- Her sembol fiyatları ve özeti tek transaction'da güncellenir. Hatalı sembollerin eski verileri korunur ve hata listesinde gösterilir. Tüm piyasa tek atomik snapshot değildir; güncelleme sürerken farklı tarihler görülebilir.
- Kaynak Yahoo Finance chart uç noktasıdır. Kullanım limiti veya erişim değişikliği olabilir; lisanslı üretim veri servisi değildir. HTTP zaman aşımı ve sınırlı geri çekilme vardır. Kalıcı 404/eksik fiyat hataları çalışmayı `partial` yapar ve uygulamada görünür; geçici ağ/servis hataları Airflow yeniden denemesini tetikler. Henüz fiyatı oluşmamış yeni bir hisse, günlük yayını engellemez.
- `--limit 2` yalnız smoke testidir, günlük tam güncelleme kaydından ayrıdır.

## Streamlit Community Cloud yayını

Yerel çalışan uygulama henüz `streamlit.app` üzerinde yayımlanmış sayılmaz. Cloud için iki bağlantı gerekir:

1. Kaynak kodu içeren GitHub deposu: giriş dosyası `app.py`, Python 3.11, bağımlılıklar `requirements.txt`.
2. VM'deki Airflow'un `market-data` dalına günlük CSV verilerini gönderebilmesi için bu depoya özel bir SSH deploy key. Kurulum: [CLOUD_SETUP.md](CLOUD_SETUP.md). Cloud, bu public veri dalını otomatik okur; buluta ayrıca parola veya depolama hesabı eklemek gerekmez.

Fırsat radarı yıllık düzeltilmiş kapanış dibine uzaklık, yıllık zirveden düşüş ve veri yaşı ile filtreler. Bir alım sinyali veya temel değerleme modeli değildir.

Veri kopyası üretme (yerelde yalnız son iki export tutulur):

```bash
python -m vulture.snapshots
```

Bu sıkıştırılmış SQLite yöntemi isteğe bağlı alternatif bir dağıtım yoludur. Varsayılan yöntem GitHub veri dalıdır. Alternatif yöntemde `runtime/publish/` altındaki hash isimli `.db.gz` dosyasını ve `manifest.json` dosyasını aynı HTTPS klasörüne aktarın; **önce veri, en son manifest**. Alternatif Cloud Secrets:

```toml
VULTURE_SNAPSHOT_MANIFEST_URL = "https://YOUR-DATA-HOST/vulture/manifest.json"
# Yalnız depo Bearer auth kullanıyorsa:
# VULTURE_SNAPSHOT_TOKEN = "..."
```

Cloud uygulaması manifesti beş dakikada bir kontrol eder; SHA-256 değişmişse dosyayı indirir, bütünlüğünü doğrular ve yerel kopyayı atomik değiştirir. Piyasa sağlayıcısına istek atmaz. Bozuk veya erişilemeyen kopyada son sağlam veriyi korur. İlk kopya yoksa veri beklediğini söyler. Eski `.env` dosyalarını, veritabanlarını veya `runtime/` klasörünü GitHub'a göndermeyin.

## Doğrulama

```bash
python -m unittest discover -s tests -p test_core.py -v
python tests/check_app.py
docker compose exec -T airflow airflow dags list-import-errors
```

Temel testler: bölünme düzeltmesi, takvim ayı getirisi, boş geçmiş, başarısız fetch'te eski veriyi koruma, retry'da başarılı sembolü atlama ve aynı gün ikinci çekimi engelleme. Uygulama testleri iki piyasanın beş ekranını açar.

İlk sürüm fiyat araştırmasına odaklanır. Eski projelerin Google CSE haber ve Gemini chatbot hizmetleri aktarılmadı; gizli anahtarlar ve eski AI servisleri kullanılmıyor. Hisse incelemesindeki değerlendirme hesaplanan istatistiklerden üretilir.
