# Mobile App — Expo (React Native)

Öğretmenin telefonunda çalışan uygulama: giriş yapar, kamerayla tablet
ekranındaki QR kodu okutur ve sonucu (Giriş/Çıkış Başarılı / Geçersiz Kod)
gösterir.

## Kurulum

```bash
cd mobile-app
npm install
npx expo start          # QR'ı Expo Go ile telefonunuzda açın
```

## Backend adresi

`app.json` → `expo.extra.apiBaseUrl` değerini backend'inizin **telefondan
erişilebilir** adresine ayarlayın (ör. `http://192.168.1.20:8000`).
`localhost`, fiziksel cihazdan çalışmaz.

## Ekranlar

- **LoginScreen:** e-posta + şifre ile giriş. JWT `expo-secure-store` içinde
  güvenli saklanır; uygulama açılışında oturum doğrulanır.
- **ScannerScreen:** `expo-camera` ile QR okur, `/api/scan`'e gönderir.
  - Yeşil ✓ → Giriş Başarılı
  - Mavi ↩ → Çıkış Başarılı
  - Kırmızı ✕ → Geçersiz/süresi dolmuş kod
  - Aynı kod birden çok kez gönderilmesin diye okuma sonrası kilitlenir
    ("Tekrar Okut" ile sıfırlanır).

## İzinler

Kamera izni `app.json` içinde tanımlıdır; ilk kullanımda kullanıcıdan istenir.
