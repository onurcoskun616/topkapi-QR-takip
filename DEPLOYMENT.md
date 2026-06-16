# Canlıya Alma Rehberi (Production Deployment)

En **sağlam + en ucuz** yöntem: tek bir küçük VPS üzerinde **Docker Compose +
Caddy** (otomatik HTTPS). Tek makinede backend, PostgreSQL, kiosk ve admin
çalışır; Caddy sertifikaları otomatik alır ve yeniler.

```
İnternet ──HTTPS──> Caddy (otomatik Let's Encrypt)
                       ├── api.okulunuz.com    → backend (FastAPI)
                       ├── kiosk.okulunuz.com  → kiosk SPA (nginx)
                       └── panel.okulunuz.com  → admin SPA (nginx)
                     PostgreSQL (kalıcı volume) — sadece iç ağ
```

Mobil uygulama (Expo) ayrı dağıtılır (aşağıda **5. adım**).

---

## Gereksinimler

- Küçük bir VPS: **2 vCPU / 2–4 GB RAM** yeterli (Hetzner CX22, DigitalOcean,
  Lightsail vb. — aylık ~4–6 $).
- Bir alan adı ve DNS yönetimi.
- Sunucuda **Docker** ve **Docker Compose** kurulu.

---

## 1. DNS

Üç A kaydını sunucunun genel IP'sine yönlendir:

| Kayıt | Değer |
| --- | --- |
| `api.okulunuz.com` | `<SUNUCU_IP>` |
| `kiosk.okulunuz.com` | `<SUNUCU_IP>` |
| `panel.okulunuz.com` | `<SUNUCU_IP>` |

> HTTPS zorunlu: Android cihazlar `http://` (cleartext) isteklerini engeller;
> kamera ve API çağrıları yalnızca HTTPS ile sorunsuz çalışır.

## 2. Sunucu hazırlığı

```bash
# Docker + Compose (Ubuntu örneği)
curl -fsSL https://get.docker.com | sh

# Saat senkronizasyonu — 15 saniye kuralı sunucu UTC saatine bağlıdır!
sudo timedatectl set-ntp true
timedatectl status        # "System clock synchronized: yes" görmelisin

# 80 ve 443 portları açık olmalı (firewall/güvenlik grubu)
```

## 3. Projeyi al ve sırları ayarla

```bash
git clone <repo-url> topkapi-qr && cd topkapi-qr
git checkout main        # ya da yayınlanacak sürüm/etiket

cp .env.prod.example .env.prod
# .env.prod içindeki TÜM CHANGE_ME değerlerini doldur:
openssl rand -hex 32     # AUTH_SECRET için
openssl rand -hex 32     # QR_SECRET için (FARKLI olmalı)
```

`.env.prod` içinde mutlaka değiştir:
- `API_DOMAIN`, `KIOSK_DOMAIN`, `PANEL_DOMAIN`, `ACME_EMAIL`
- `POSTGRES_PASSWORD`
- `AUTH_SECRET`, `QR_SECRET` (ikisi farklı, `openssl rand -hex 32`)
- `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD`

> `.env.prod` git'e dahil **edilmez** (`.gitignore` ile korunur).

## 4. Çalıştır

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

- Backend ilk açılışta tabloları oluşturur ve bootstrap admin'i ekler.
- Caddy birkaç saniye içinde üç alan adı için sertifika alır.
- Kontrol:
  - `https://api.okulunuz.com/health` → `{"status":"ok", ...}`
  - `https://panel.okulunuz.com` → yönetim paneli (admin ile giriş yap)
  - `https://kiosk.okulunuz.com` → dönen QR ekranı

Logları izlemek için: `docker compose -f docker-compose.prod.yml logs -f`

## 5. Mobil uygulama (Expo) yayını

API adresini ayarla ve EAS ile derle:

```bash
cd mobile-app
# app.json -> expo.extra.apiBaseUrl = "https://api.okulunuz.com"
npm install -g eas-cli
eas login
eas build -p android         # APK/AAB üretir
# (iOS için: eas build -p ios  — Apple geliştirici hesabı gerekir)
```

- Birkaç okul cihazı için: üretilen **APK**'yı doğrudan cihazlara kur.
- Geniş dağıtım için: Google Play / App Store.

## 6. Tablet kiosk modu

Tabletlerde `https://kiosk.okulunuz.com` adresini tam ekran aç. Cihazı tek
uygulamaya kilitlemek ve ekranı sürekli açık tutmak için **Fully Kiosk
Browser** gibi bir uygulama önerilir.

---

## Bakım

**Güncelleme:**
```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

**Veritabanı yedeği (günlük cron önerilir):**
```bash
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U topkapi topkapi_qr > backup_$(date +%F).sql
```

**Geri yükleme:**
```bash
cat backup_2026-06-16.sql | docker compose -f docker-compose.prod.yml \
  exec -T db psql -U topkapi -d topkapi_qr
```

---

## Canlı öncesi kontrol listesi

- [ ] `AUTH_SECRET` ≠ `QR_SECRET`, ikisi de `openssl rand -hex 32`
- [ ] Bootstrap admin parolası güçlü; ilk girişten sonra yeni admin açıldı
- [ ] DNS üç subdomain için doğru; 80/443 açık
- [ ] `https://api.../health` ve paneller HTTPS ile açılıyor (kilit ikonu)
- [ ] Sunucuda NTP aktif (`timedatectl`)
- [ ] Günlük PostgreSQL yedeği kuruldu
- [ ] Gece 23:59 otomatik kapanış ilk gün loglardan doğrulandı
- [ ] Mobil uygulamadaki `apiBaseUrl` = `https://api.okulunuz.com`

---

## Neden bu yöntem?

- **Ucuz:** Tek VPS (~aylık 4–6 $), ek statik hosting/managed DB maliyeti yok.
- **Sağlam:** `restart: unless-stopped` ile servisler otomatik kalkar; Caddy
  TLS'i otomatik yeniler; veriler kalıcı volume'da.
- **Basit:** Tek komutla build + deploy; tek makinede tüm bileşenler.

Daha az operasyon istersen alternatif: backend+DB için Railway/Render (managed
PostgreSQL), kiosk/admin için Netlify/Vercel, mobil için EAS. Sunucu yönetimi
olmaz ama maliyet artar.
