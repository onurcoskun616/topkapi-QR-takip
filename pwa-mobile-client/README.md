# Öğretmen PWA — React + Vite (vite-plugin-pwa)

Öğretmenlerin QR okuttuğu **kurulabilir web uygulaması**. App Store / Google
Play gerekmez; telefonda tarayıcıdan "Ana Ekrana Ekle" ile kurulur, ana
ekrandan açıldığında tarayıcı barları olmadan (standalone) doğrudan kamerayı
açar.

## Kurulum (geliştirme)

```bash
cd pwa-mobile-client
npm install
cp .env.example .env      # VITE_API_BASE_URL backend adresi
npm run dev               # http://localhost:5175
```

> Kamera (`getUserMedia`) yalnızca **HTTPS** veya `localhost` üzerinde çalışır.
> Üretimde uygulama HTTPS arkasında sunulmalıdır (bkz. `../DEPLOYMENT.md`).

Üretim derlemesi: `npm run build` → `dist/` (service worker + manifest dahil).

## Davranış

- **Sessiz oturum:** Açılışta `localStorage`'daki refresh token + cihaz parmak
  izi ile `/api/auth/refresh` çağrılır. Başarılıysa öğretmen login görmeden
  doğrudan kameraya düşer; değilse giriş ekranı gösterilir.
- **Giriş:** E-posta + şifre + cihaz parmak izi `/api/auth/login`'e gönderilir.
  Access token bellekte, 1 yıllık refresh token `localStorage`'da tutulur.
- **Tarama:** `html5-qrcode` ile arka kamera açılır; okunan token `/api/scan`'e
  gönderilir. Access token süresi dolmuşsa otomatik bir kez sessiz yenileme
  yapılıp tekrar denenir. Sonuç: yeşil ✓ Giriş / mavi ↩ Çıkış / kırmızı ✕
  Geçersiz.
- **Cihaz kilidi:** Hesap tek cihaza bağlıdır; başka telefondan giriş eski
  cihazı düşürür.

## PWA notları

- `manifest.webmanifest` ve `sw.js` build sırasında `vite-plugin-pwa` ile
  üretilir; ikonlar `public/` altındadır (`pwa-192.png`, `pwa-512.png`,
  `maskable-512.png`, `apple-touch-icon.png`).
- `registerType: autoUpdate` — yeni sürüm yayınlandığında uygulama arka planda
  güncellenir.
- API çağrıları service worker tarafından **önbelleğe alınmaz** (yoklama her
  zaman canlı sunucuya gider).
