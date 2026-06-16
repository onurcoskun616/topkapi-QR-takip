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
| `AUTH_SECRET`             | Access token imza anahtarı                     |
| `REFRESH_SECRET`          | Refresh token imza anahtarı (AUTH'tan farklı)  |
| `QR_SECRET`               | QR token imza anahtarı (diğerlerinden farklı)  |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token ömrü (varsayılan 15)          |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | Refresh token ömrü (varsayılan 365)        |
| `QR_TOKEN_TTL_SECONDS`    | QR geçerlilik süresi (varsayılan 15)           |
| `ATTENDANCE_TIMEZONE`     | Gün sınırı için saat dilimi (depolama UTC)     |
| `BOOTSTRAP_ADMIN_*`       | İlk açılışta oluşturulacak **genel merkez (hq)** hesabı |

> İlk açılışta 5 kampüs (İkitelli OSB, İstanbul OSB, Esenyurt, Kıraç, Çorlu)
> otomatik tohumlanır (`app/bootstrap.py` → `DEFAULT_CAMPUSES`).

## Roller

| Rol               | Giriş            | Kapsam                                            |
| ----------------- | ---------------- | ------------------------------------------------ |
| `staff`           | Şifresiz, cihaz-bağlı (PWA self-kayıt) | QR okutur, kendi geçmişini görür  |
| `campus_director` | E-posta + şifre  | Kendi kampüsü: personel onay/sıfırlama + raporlar |
| `hq` (genel merkez) | E-posta + şifre | Tüm kampüsler + müdür/kampüs yönetimi            |

## API uç noktaları

| Method | Yol                          | Yetki     | Açıklama                                          |
| ------ | ---------------------------- | --------- | ------------------------------------------------- |
| GET    | `/api/campuses`              | —         | Kampüs listesi (kayıt formu açılır menüsü)        |
| POST   | `/api/auth/register`         | —         | Personel self-kayıt / yeni telefon yeniden tanıtma → access + refresh (beklemede) |
| POST   | `/api/auth/login`            | —         | Müdür/genel merkez: e-posta + şifre + cihaz → access + refresh |
| POST   | `/api/auth/refresh`          | —         | Refresh token + cihaz imzası → yeni access (sessiz) |
| POST   | `/api/auth/logout`           | user      | Mevcut oturumu (cihazı) geçersiz kıl              |
| GET    | `/api/auth/me`               | user      | Mevcut kullanıcı (durum dahil — PWA onayı bekler) |
| GET    | `/api/staff`                 | yönetici  | Personel listesi (müdür: kendi kampüsü)           |
| POST   | `/api/staff/{id}/approve`    | yönetici  | Bekleyen personeli onayla                         |
| POST   | `/api/staff/{id}/reset-device` | yönetici | Cihaz kaydını sıfırla (telefon değişikliği)      |
| POST   | `/api/staff/{id}/disable`    | yönetici  | Personeli devre dışı bırak                        |
| PATCH  | `/api/staff/{id}`            | yönetici  | Profil düzelt (ad/görev/branş/kampüs)             |
| GET    | `/api/directors`             | hq        | Kampüs müdürlerini listele                        |
| POST   | `/api/directors`             | hq        | Yeni kampüs müdürü oluştur                        |
| POST   | `/api/directors/{id}/disable`| hq        | Müdür hesabını devre dışı bırak                   |
| GET    | `/api/qr/token`              | —         | Taze QR token (15 sn)                             |
| POST   | `/api/scan`                  | staff (aktif) | QR okut → IN/OUT toggle                        |
| GET    | `/api/logs/me`               | staff     | Kendi geçmişi                                     |
| GET    | `/api/logs`                  | yönetici  | Kayıtlar (kampüs kapsamlı; hq `campus_id` filtreli)|
| GET    | `/api/logs/export`           | yönetici  | CSV dışa aktarım (UTC + yerel saat + kampüs)      |
| GET    | `/api/logs/summary/today`    | yönetici  | Şu an içeride olanlar + günlük sayılar (kampüs kapsamlı) |
| POST   | `/api/admin/run-auto-close`  | hq        | Gece kapanışını elle tetikle                      |
| GET    | `/health`                    | —         | Sağlık + sunucu saati                             |

## Cron / arka plan görevleri (APScheduler)

- **23:59 (yerel):** `auto_close_open_attendances` — içeride kalanlara
  `auto_closed_by_system` OUT kaydı ekler.
- **Saat başı:** `purge_used_qr_tokens` — replay defterini temizler.

## Testler

```bash
pytest -q
```
