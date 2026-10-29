# VM -> GitHub -> Streamlit Cloud

Günlük akış: Airflow (02.30 Europe/Istanbul) -> yerel SQLite -> `market-data` dalına fiyat CSV'leri ve manifest -> Streamlit Cloud.

Cloud açıldığında Yahoo'ya yeniden istek gönderilmez. Özetler ve seçilen hisselerin geçmişleri GitHub'ın ham dosya servisinden okunur. Manifest, fiyat dosyalarının ait olduğu değişmez Git commit'ini taşır; bir oturumda farklı yayınların dosyaları karışmaz. Manifest beş dakika önbelleklenir.

## Tek seferlik yayın anahtarı

1. VM'de `python scripts/prepare_publisher.py` çalıştırın. Bu komut özel anahtarı yalnız `runtime/publisher_ed25519` içinde 0600 izinleriyle tutar; sadece açık anahtarı yazdırır. GitHub SSH sunucu anahtarları resmi HTTPS meta API'sinden alınır.
2. GitHub deposunda Settings -> Deploy keys -> Add deploy key. Başlık: `Vulture daily data VM`. Açık anahtarı yapıştırın, **Allow write access** işaretleyip kaydedin. Anahtar yalnız bu depoya erişir.
3. VM'de ilk yayını çalıştırın:

```bash
cd /home/train/VultureCapital
/home/train/miniconda3/bin/python -m vulture.publish
```

Cloud uygulaması `main` dalındaki kodu çalıştırır. Veri `market-data` dalındadır; `main` içine SQLite, anahtar, `.env` veya Airflow dosyaları yüklenmez. Bu depo public olduğundan, yayınlanan fiyat verileri ve şirket isimleri public olur.

## Sonraki günler

Airflow `update_all_markets` göreviyle veriyi alır. `publish_to_streamlit` görevi, veri çekme görevi hata verse de çalışıp korunmuş fiyatları ve hata durumunu yayımlar. Git gönderimi başarısızsa yayın görevi başarısız olur ve iki kez yeniden denenir. `git push --force` kullanılmaz.

Elle eski bash yaklaşımına denk komut:

```bash
bash scripts/update_and_publish.sh
```

Yalnız hazır veriyi yayımlamak için `python -m vulture.publish` yeterlidir; fiyatları tekrar indirmez.

Kullanıcı yalnızca web uygulamasını açar. VM kapalıyken günlük çekim yapılmaz; bulut son yayımlanmış veriyi göstermeyi sürdürür. GitHub erişimi kesilirse durum gizlenmez. Değişen fiyat verisi Git geçmişinde kalır; depo boyutu zamanla izlenmelidir. Yayın klasörü yeni projenin `runtime/data-publisher` dizinindedir; eski projeler etkilenmez.
