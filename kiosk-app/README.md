# Kiosk App — React + Vite

Tablette tam ekran çalışan, sunucudan her 15 saniyede bir taze QR token alıp
gösteren basit SPA.

## Kurulum

```bash
cd kiosk-app
npm install
cp .env.example .env     # VITE_API_BASE_URL backend adresini göstermeli
npm run dev              # http://localhost:5173
```

Üretim:

```bash
npm run build && npm run preview
```

## Tablette kiosk modu (tarayıcı çubuğu görünmesin)

Uygulama artık bir PWA (manifest + ikonlar) olarak yapılandırıldı, bu sayede
adres çubuğu/menü gibi tarayıcı arayüzü olmadan, ana ekran simgesinden açılan
gerçek bir "uygulama" gibi tam ekran çalışabiliyor.

**Android tablet (önerilen yol):**
1. Tablette Chrome ile kiosk adresini açın (kampüse özel ise `?campus=<id>`
   ile, ör. `https://kiosk.okulunuz.com/?campus=3`).
2. Sağ üstteki ⋮ menüsünden **"Ana ekrana ekle"** (Add to Home screen) seçin.
3. Ana ekrandaki yeni simgeye dokunarak açın — artık adres çubuğu/sekme
   görünmez, tamamen tam ekran açılır.
4. (İsteğe bağlı, tabletin ayarına göre) Chrome'un kendisini değil, az önce
   eklediğiniz bu simgeyi tabletin "açılışta otomatik başlat" uygulaması
   yapın.

**Alternatif:** Sayfayı normal Chrome sekmesinde açık tutacaksanız, ekrana
ilk dokunuşta sayfa otomatik olarak tam ekrana geçer (adres çubuğu
gizlenir). Tamamen çıkmak isterseniz tabletin geri tuşu veya kenardan
kaydırma hareketiyle tam ekrandan çıkabilirsiniz.

**Diğer seçenek:** Tarayıcıyı F11 ile tam ekran yapmak veya bir kiosk
uygulaması (ör. Fully Kiosk Browser) kullanmak da çalışır.

- Sayfa, sunucu saatine göre senkronize bir geri sayım gösterir ve QR süresi
  dolduğunda otomatik yenilenir. Backend erişilemezse 3 sn'de bir tekrar dener.
