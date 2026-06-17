# Canlıya Alma Rehberi (Production Deployment)

En **sağlam + en ucuz** yöntem: tek bir küçük VPS üzerinde **Docker Compose +
Caddy** (otomatik HTTPS). Tek makinede backend, PostgreSQL, kiosk ve admin
çalışır; Caddy sertifikaları otomatik alır ve yeniler.

```
İnternet ──HTTPS──> Caddy (otomatik Let's Encrypt)
                       ├── api.okulunuz.com    → backend (FastAPI)
                       ├── kiosk.okulunuz.com  → kiosk SPA (nginx)
                       ├── panel.okulunuz.com  → admin SPA (nginx)
                       └── app.okulunuz.com    → öğretmen PWA (nginx)
                     PostgreSQL (kalıcı volume) — sadece iç ağ
```

Öğretmen uygulaması artık bir PWA'dır (App Store/Play Store **yok**);
telefonda tarayıcıdan "Ana Ekrana Ekle" ile kurulur (aşağıda **5. adım**).

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
| `app.okulunuz.com` | `<SUNUCU_IP>` |

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
- Caddy birkaç saniye içinde dört alan adı için sertifika alır.
- Kontrol:
  - `https://api.okulunuz.com/health` → `{"status":"ok", ...}`
  - `https://panel.okulunuz.com` → yönetim paneli (admin ile giriş yap)
  - `https://kiosk.okulunuz.com` → dönen QR ekranı
  - `https://app.okulunuz.com` → öğretmen PWA (giriş ekranı)

Logları izlemek için: `docker compose -f docker-compose.prod.yml logs -f`

## 4b. İlk kurulum: kampüsler, müdürler, onay akışı

Backend ilk açılışta **5 kampüsü** (İkitelli OSB, İstanbul OSB, Esenyurt, Kıraç,
Çorlu) ve `.env.prod`'daki **genel merkez (hq)** hesabını otomatik oluşturur.

1. `https://panel.okulunuz.com`'a **genel merkez** hesabıyla gir.
2. **Müdürler** sekmesinden her kampüse bir **kampüs müdürü** (e-posta + şifre)
   oluştur. Müdür kendi kampüsünün personelini ve raporlarını görür.
3. Personel telefonundan PWA'ya kaydolur (aşağıda **5. adım**); kaydı
   **beklemede** gelir. İlgili **kampüs müdürü** panelin **Personel** sekmesinden
   **Onayla**'ya basınca personel QR okutmaya başlar.
4. Personel telefon değiştirirse müdür **Personel ▸ Cihazı Sıfırla** der;
   personel yeni telefonda aynı numarayla yeniden kaydolur (geçmiş korunur).
5. Personel telefonu arızalanır/QR okutmayı unutursa müdür **Personel ▸
   Manuel Kayıt** ile eksik IN/OUT kaydını ekler; var olan bir QR kaydı asla
   değiştirilemez.
6. Sağlık raporu, ücretli izin vb. durumlarda müdür **İzin / Devamsızlık**
   sekmesinden tarih aralıklı bir kayıt açar; aktif olduğu sürece personelin
   QR okutması engellenir. Personel gelirse kayıt **Düzelt**ilir veya **İptal
   Et**ilir — scan hemen yeniden açılır.
7. **Kampüsler** sekmesinden (yalnızca genel merkez) her kampüsün mesai
   başlangıç/bitiş saati belirlenir; **Raporlar** sekmesindeki geç kalma/erken
   çıkış hesaplamaları bu saatlere dayanır.

> Genel merkez panelde **kampüs filtresi** ile tek tek kampüsleri veya tümünü
> görebilir; **Raporlar** sekmesinden tarih aralığı, tolerans dakikası ve
> hafta sonu filtreleriyle CSV/Excel indirebilir.

## 5. Öğretmen/personel PWA'sını dağıt (App Store/Play Store yok)

PWA zaten `https://app.okulunuz.com` adresinde yayında (4. adımda Caddy ile
ayağa kalktı). App Store / Google Play süreci **gerekmez**. Personel:

1. Telefon tarayıcısında `https://app.okulunuz.com` adresini açar.
2. **Ana Ekrana Ekle** der:
   - **iPhone (Safari):** Paylaş ▸ "Ana Ekrana Ekle".
   - **Android (Chrome):** ⋮ menü ▸ "Uygulamayı yükle / Ana ekrana ekle".
3. Uygulamayı ana ekrandan açar; tarayıcı barları olmadan (standalone) açılır.
4. **Bir kez** ad-soyad, görev, branş, **doğum tarihi**, telefon ve kampüsünü
   girerek **kaydolur** (şifre yok). Kampüs müdürü onayladıktan sonra cihaz 1
   yıllık oturuma kilitlenir; sonraki günler uygulama doğrudan kameraya açılır.

> Güvenlik: Her hesap **telefon numarasıyla** tek bir cihaza bağlıdır. Başka bir
> telefondan aynı numarayla kayıt, müdür "Cihazı Sıfırla" demeden **reddedilir**
> (hesap paylaşımı bu sayede engellenir). HTTPS zorunludur; kamera yalnızca
> güvenli bağlantıda çalışır.

## 6. Tablet kiosk modu

Tabletlerde `https://kiosk.okulunuz.com` adresini tam ekran aç. Cihazı tek
uygulamaya kilitlemek ve ekranı sürekli açık tutmak için **Fully Kiosk
Browser** gibi bir uygulama önerilir.

> **Tableti kampüs kimliğiyle aç:** Her tableti
> `https://kiosk.okulunuz.com/?campus=<KAMPUS_ID>` adresiyle aç (kampüs id'leri
> genel merkez panelindeki **Kampüsler** sekmesinden görülebilir). Bu sayede:
> başarılı her taramadan sonra tablette yeşil **"Giriş/Çıkış başarılı"** onayı
> çıkar; doğum günü olan personelin gün içindeki ilk girişinde ise tam ekran
> **"İyi ki doğdun!"** kutlaması gösterilir. `?campus=` verilmezse kiosk QR'ı
> normal gösterir ama tablette tarama onayı/kutlama çıkmaz (ekranda uyarı
> belirir).

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
- [ ] `AUTH_SECRET`, `REFRESH_SECRET`, `QR_SECRET` üçü de ayrı ve rastgele
- [ ] Öğretmen PWA'sı `https://app.okulunuz.com`'da açılıyor ve "Ana Ekrana
      Ekle" çalışıyor; tek-cihaz kilidi test edildi

---

## Neden bu yöntem?

- **Ucuz:** Tek VPS (~aylık 4–6 $), ek statik hosting/managed DB maliyeti yok.
- **Sağlam:** `restart: unless-stopped` ile servisler otomatik kalkar; Caddy
  TLS'i otomatik yeniler; veriler kalıcı volume'da.
- **Basit:** Tek komutla build + deploy; tek makinede tüm bileşenler.

Daha az operasyon istersen alternatif: backend+DB için Railway/Render (managed
PostgreSQL), kiosk/admin için Netlify/Vercel, mobil için EAS. Sunucu yönetimi
olmaz ama maliyet artar.
