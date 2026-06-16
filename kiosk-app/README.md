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

## Tablette kiosk modu

- Tarayıcıyı tam ekran (F11) veya bir kiosk uygulaması (ör. Fully Kiosk
  Browser) ile açın.
- Sayfa, sunucu saatine göre senkronize bir geri sayım gösterir ve QR süresi
  dolduğunda otomatik yenilenir. Backend erişilemezse 3 sn'de bir tekrar dener.
