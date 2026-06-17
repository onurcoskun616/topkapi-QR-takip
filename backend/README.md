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
| POST   | `/api/auth/register`         | —         | Personel self-kayıt / yeni telefon yeniden tanıtma (ad, görev, branş, **doğum tarihi**, telefon, kampüs) → access + refresh (beklemede) |
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
| GET    | `/api/kiosk/recent-scans`    | —         | Kiosk için: `campus_id` ile, son ~12 sn içindeki başarılı QR taramalarını döndürür (tablette yeşil "Giriş/Çıkış başarılı" onayı); doğum günü ilk-girişi `birthday` bayrağıyla işaretlenir |
| POST   | `/api/scan`                  | staff (aktif) | QR okut → IN/OUT toggle                        |
| GET    | `/api/logs/me`               | staff     | Kendi geçmişi                                     |
| GET    | `/api/logs`                  | yönetici  | Kayıtlar (kampüs kapsamlı; hq `campus_id` filtreli)|
| POST   | `/api/logs/manual`           | yönetici  | Manuel giriş/çıkış kaydı ekle (telefon arızalı vb. — yalnızca eksik kaydı tamamlar, var olan QR kaydını değiştiremez) |
| GET    | `/api/logs/export`           | yönetici  | CSV dışa aktarım (UTC + yerel saat + kampüs, tarih aralığı filtreli) |
| GET    | `/api/logs/export.xlsx`      | yönetici  | Aynı ham kayıtların Excel (.xlsx) dışa aktarımı   |
| GET    | `/api/logs/summary/today`    | yönetici  | Şu an içeride olanlar + günlük sayılar (kampüs kapsamlı) |
| GET    | `/api/leaves/types`          | yönetici  | Önerilen izin/devamsızlık türleri (açık liste — serbest metin de girilebilir) |
| GET    | `/api/leaves`                | yönetici  | İzin/devamsızlık kayıtlarını listele (personel/kampüs/durum/tarih filtreli) |
| POST   | `/api/leaves`                | yönetici  | Personel için tarih aralığı kapsayan izin/devamsızlık kaydı oluştur (aktifken QR okutmayı engeller) |
| PATCH  | `/api/leaves/{id}`           | yönetici  | İzin kaydını düzelt (tür/tarih aralığı/not/durum)  |
| POST   | `/api/leaves/{id}/cancel`    | yönetici  | İzin kaydını iptal et (personel anında yeniden QR okutabilir) |
| GET    | `/api/reports/late`          | yönetici  | En çok geç kalanlar sıralaması (tolerans dakikası + kampüs mesai saatine göre) |
| GET    | `/api/reports/early-leave`   | yönetici  | En çok erken çıkanlar sıralaması                  |
| GET    | `/api/reports/absences`      | yönetici  | Devamsızlık günü detayı (izinle açıklanan / `unresolved` — açıklanmayan) |
| GET    | `/api/reports/absence-summary` | yönetici | İzin türüne göre toplam + personel başına devamsızlık özeti |
| GET    | `/api/reports/export.xlsx`   | yönetici  | Yukarıdaki rapor tablolarının tamamını Excel'e aktar |
| PATCH  | `/api/campuses/{id}/shift`   | **hq**    | Kampüsün mesai başlangıç/bitiş saatini belirle (yalnızca genel merkez; müdürün yetkisi yok) |
| POST   | `/api/admin/run-auto-close`  | hq        | Gece kapanışını elle tetikle                      |
| GET    | `/health`                    | —         | Sağlık + sunucu saati                             |

## Tablette tarama onayı ve doğum günü kutlaması (kiosk)

Tarama telefonda yapılır (QR tabletten okunur, `POST /api/scan` telefondan
gelir). Personelin elindeki **telefon, sonucu ağ yanıtı gelir gelmez anında**
gösterir (tarama isteği kamera kapanmasını beklemeden gönderilir). Tablet ise
sonucu doğrudan görmediğinden kampüsünün son taramalarını yoklayarak **yeşil
onay** ve **doğum günü kutlaması** gösterir.

- Tablet hangi kampüse ait olduğunu URL'den okur (`?campus=<id>`) ve
  `/api/kiosk/recent-scans?campus_id=<id>` ucunu ~0,7 sn'de bir yoklar; yeşil
  onay genelde taramadan ~0,4 sn sonra (en fazla ~1 sn) belirir.
- **Yeşil onay:** Her başarılı QR taramasından hemen sonra tablette yeşil tikli
  "Giriş başarılı" / "Çıkış başarılı" + isim bildirimi çıkar. Yalnızca son ~12
  sn içindeki geçerli `qr_scan` kayıtları döner (sonradan açılan tablet eski
  taramaları tekrar göstermez); müdürün **manuel** kaydı ve gece otomatik
  kapanışı tablette gösterilmez (kimse bizzat okutmuyor).
- **Doğum günü:** Personel **self-kayıtta doğum tarihini** girer (`birth_date`,
  zorunlu; yalnızca ay/gün kullanılır). Doğum günü bugün olan personelin
  gün içindeki **ilk girişi** `birthday` bayrağıyla döner; tablet o tarama için
  yeşil onay yerine tam ekran "İyi ki doğdun!" kutlaması gösterir.
- `birth_date` alanı modele sonradan eklendiği için, mevcut veritabanlarında
  `users.birth_date` kolonu açılışta otomatik (idempotent) eklenir
  (`ensure_schema_upgrades`).

## Manuel kayıt, izin/devamsızlık ve raporlama (özet)

- **Manuel kayıt** (`POST /api/logs/manual`): Yönetici, telefonu arızalanan ya
  da QR okutmayı unutan personel için geçmiş bir IN/OUT kaydı **ekleyebilir**;
  var olan bir QR kaydını **asla değiştiremez veya silemez** —
  `AttendanceSource.director_manual` olarak işaretlenir ve raporlarda/CSV'de
  ayırt edilebilir. Aynı gün için zaten bir IN varsa tekrar IN eklemek **409**
  döner; gelecek tarihli kayıt **400** ile reddedilir.
- **İzin/devamsızlık** (`LeaveRecord`): Yönetici, personel için açık uçlu bir
  metinle (`leave_type` — "Sağlık raporu", "Ücretli izin" vb., serbest metin de
  kabul edilir) bir tarih aralığı kaydeder. Kayıt `active` olduğu ve bugünün
  yerel tarihi aralığa girdiği sürece `/api/scan` o personelin QR okutmasını
  reddeder ("müdürünüze başvurun" mesajıyla). Personel asıl gelirse yönetici
  `PATCH` ile aralığı kısaltır veya `cancel` ile tamamen iptal eder — ikisi de
  scan'i **anında** yeniden açar. İzinle açıklanmayan devamsız günler
  raporlarda **hiçbir zaman sessizce atlanmaz**; `unresolved` (durum
  girilmedi) olarak işaretlenir.
- **Raporlama**: Tüm rapor uç noktaları (`/api/reports/*`) keyfi
  `start_date`/`end_date` aralığı, `threshold_minutes` (geç kalma/erken çıkma
  toleransı) ve `exclude_weekends` filtreleri kabul eder; hq ayrıca
  `campus_id` ile tek kampüse indirgeyebilir. Hem ham kayıtlar
  (`/api/logs/export.xlsx`) hem de rapor tabloları
  (`/api/reports/export.xlsx`) Excel olarak indirilebilir.
- **Mesai saatleri**: `Campus.shift_start`/`shift_end` geç kalma ve erken
  çıkış hesaplamalarının dayanağıdır; yalnızca **hq** bu saatleri
  değiştirebilir (`PATCH /api/campuses/{id}/shift`) — kampüs müdürünün bu uç
  noktaya erişimi yoktur (403).

## Cron / arka plan görevleri (APScheduler)

- **23:59 (yerel):** `auto_close_open_attendances` — içeride kalanlara
  `auto_closed_by_system` OUT kaydı ekler.
- **Saat başı:** `purge_used_qr_tokens` — replay defterini temizler.

## Testler

```bash
pytest -q
```
