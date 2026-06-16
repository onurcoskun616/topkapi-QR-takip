# Backend — FastAPI

## Kurulum (yerel)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # değerleri düzenleyin

# PostgreSQL gerekli (docker compose up db ile de açabilirsiniz)
uvicorn app.main:app --reload --port 8000
```

İnteraktif API dokümanı: <http://localhost:8000/docs>

## Önemli ortam değişkenleri

| Değişken                  | Açıklama                                       |
| ------------------------- | ---------------------------------------------- |
| `DATABASE_URL`            | `postgresql+asyncpg://...`                     |
| `AUTH_SECRET`             | Login JWT imza anahtarı                        |
| `QR_SECRET`               | QR token imza anahtarı (AUTH'tan farklı olmalı)|
| `QR_TOKEN_TTL_SECONDS`    | QR geçerlilik süresi (varsayılan 15)           |
| `ATTENDANCE_TIMEZONE`     | Gün sınırı için saat dilimi (depolama UTC)     |
| `BOOTSTRAP_ADMIN_*`       | İlk açılışta oluşturulacak admin               |

## API uç noktaları

| Method | Yol                      | Yetki  | Açıklama                              |
| ------ | ------------------------ | ------ | ------------------------------------- |
| POST   | `/api/auth/login`        | —      | E-posta + şifre → JWT                 |
| GET    | `/api/auth/me`           | user   | Mevcut kullanıcı                      |
| GET    | `/api/auth/users`        | admin  | Tüm kullanıcıları listele             |
| POST   | `/api/auth/users`        | admin  | Yeni öğretmen/admin oluştur           |
| GET    | `/api/qr/token`          | —      | Taze QR token (15 sn)                 |
| POST   | `/api/scan`              | user   | QR okut → IN/OUT toggle               |
| GET    | `/api/logs/me`           | user   | Kendi geçmişi                         |
| GET    | `/api/logs`              | admin  | Tüm kayıtlar (user_id/day filtreli)   |
| GET    | `/api/logs/export`       | admin  | CSV dışa aktarım (UTC + yerel saat)   |
| GET    | `/api/logs/summary/today`| admin  | Şu an içeride olanlar + günlük sayılar|
| POST   | `/api/admin/run-auto-close` | admin | Gece kapanışını elle tetikle        |
| GET    | `/health`                | —      | Sağlık + sunucu saati                 |

## Cron / arka plan görevleri (APScheduler)

- **23:59 (yerel):** `auto_close_open_attendances` — içeride kalanlara
  `auto_closed_by_system` OUT kaydı ekler.
- **Saat başı:** `purge_used_qr_tokens` — replay defterini temizler.

## Testler

```bash
pytest -q
```
