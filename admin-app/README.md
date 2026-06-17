# Admin App — React + Vite

Yönetici web paneli: anlık doluluk, yoklama kayıtları, filtreleme, **CSV dışa
aktarım**, kullanıcı yönetimi ve gece kapanışını elle tetikleme.

## Kurulum

```bash
cd admin-app
npm install
cp .env.example .env      # VITE_API_BASE_URL backend adresi
npm run dev               # http://localhost:5174
```

Üretim: `npm run build && npm run preview`

## Özellikler

- **Giriş:** Yalnızca `role=admin` kullanıcılar; JWT `localStorage`'da tutulur.
- **Gösterge Paneli:**
  - KPI: şu an içeride / bugün hareketli personel sayısı.
  - "Şu an içeride olanlar" listesi (son kaydı GİRİŞ olanlar).
  - Personel + gün filtreli kayıt tablosu (GİRİŞ/ÇIKIŞ, sistem-kapatma rozeti).
  - **CSV İndir** (filtreye göre; UTC + yerel saat sütunları).
  - **Gece Kapanışını Çalıştır** (`/api/admin/run-auto-close`).
- **Kullanıcılar:** Yeni öğretmen/yönetici oluşturma + liste.

Bağlandığı uçlar: `/api/auth/*`, `/api/logs`, `/api/logs/export`,
`/api/logs/summary/today`, `/api/admin/run-auto-close`.
