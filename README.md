# Topkapı Okulları — Dinamik QR Tabanlı Yoklama Sistemi

Öğretmen ve personelin giriş-çıkışlarını **15 saniyede bir yenilenen, sunucu
imzalı dinamik QR kodları** ile takip eden uçtan uca bir sistem.

```
┌──────────────┐      her 15 sn taze token       ┌──────────────────┐
│  Kiosk (Tablet)│ ◀──────────────────────────────│                  │
│  React + Vite │   GET /api/qr/token             │   FastAPI Backend │
└──────────────┘                                  │   + PostgreSQL    │
                                                  │   + APScheduler   │
┌──────────────┐   POST /api/scan (JWT + token)   │   (gece 23:59)    │
│ Mobil (Expo)  │ ──────────────────────────────▶ │                  │
│ React Native  │   "Giriş/Çıkış Başarılı"        └──────────────────┘
└──────────────┘
```

## Bileşenler

| Klasör        | Teknoloji                         | Görev                                            |
| ------------- | --------------------------------- | ------------------------------------------------ |
| `backend/`    | Python · FastAPI · SQLAlchemy(async) · PostgreSQL · APScheduler | API, JWT auth, QR üretimi, scan mantığı, cron |
| `kiosk-app/`  | React · Vite · qrcode.react       | Tam ekran tablet; QR'ı 15 sn'de bir yeniler      |
| `mobile-app/` | Expo · React Native · expo-camera | Öğretmen girişi + QR okutma                       |
| `admin-app/`  | React · Vite                      | Yönetici paneli: raporlar, doluluk, CSV, kullanıcı yönetimi |

## Teknoloji seçimi

Backend için **FastAPI** seçildi: async I/O, otomatik OpenAPI dokümantasyonu
(`/docs`), Pydantic doğrulaması ve düşük bağımlılıkla en stabil sonucu verir.

## İş kuralları (özet)

1. **Dinamik QR (15 sn):** Backend, `jti` + `iat` + `exp` taşıyan kısa ömürlü
   bir JWT üretir (`QR_SECRET` ile imzalı). Kiosk bunu QR olarak gösterir ve
   süresi dolunca otomatik yeniler.
2. **Giriş-Çıkış (Toggle):** Öğretmen kendi JWT'si + QR token'ı `/api/scan`'e
   gönderir. Backend:
   - QR token süresi geçtiyse → **400**.
   - Token daha önce kullanıldıysa (replay) → **409**.
   - Aksi halde o günkü son kayda bakar: kayıt yok / son kayıt OUT → **IN**;
     son kayıt IN → **OUT**.
3. **Gece sıfırlaması (23:59):** Hâlâ "içeride" (son kaydı IN) olan herkes için
   sistem `auto_closed_by_system` statüsünde bir OUT kaydı ekler.
4. **Zaman senkronizasyonu:** Tüm token üretim/doğrulaması ve gün sınırı
   **sunucu UTC saatine** göre yapılır; istemci saatine asla güvenilmez.

## Hızlı başlangıç (Docker)

```bash
cp backend/.env.example backend/.env   # gizli anahtarları değiştirin
docker compose up --build
# Backend:  http://localhost:8000   (Swagger: /docs)
# İlk açılışta .env'deki bootstrap admin otomatik oluşturulur.
```

Detaylı kurulum için her klasördeki `README.md` dosyasına bakın.

## Güvenlik notları

- `AUTH_SECRET` ve `QR_SECRET` **ayrı** tutulur; QR anahtarı sızsa bile login
  oturumu üretilemez.
- QR token'lar tek kullanımlıktır (`used_qr_tokens` defteri ile replay koruması).
- Şifreler `bcrypt` ile hash'lenir; login hatası kullanıcı sızdırmaz.
- CORS yalnızca yapılandırılan origin'lere açıktır.
- `.env` ve sırlar git'e dahil edilmez (`.gitignore`).
