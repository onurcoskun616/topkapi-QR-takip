# Topkapı Okulları — Dinamik QR Tabanlı Yoklama Sistemi

Öğretmen ve personelin giriş-çıkışlarını **15 saniyede bir yenilenen, sunucu
imzalı dinamik QR kodları** ile takip eden uçtan uca bir sistem.

```
┌───────────────┐     her 15 sn taze token        ┌──────────────────┐
│ Kiosk (Tablet) │ ◀──────────────────────────────│                  │
│  React + Vite  │   GET /api/qr/token             │  FastAPI Backend  │
└───────────────┘                                  │  + PostgreSQL     │
                                                   │  + APScheduler    │
┌───────────────┐  POST /api/scan (access + token) │  (gece 23:59)     │
│ Öğretmen PWA   │ ──────────────────────────────▶ │                  │
│ React + Vite   │   "Giriş/Çıkış Başarılı"        └──────────────────┘
│ (Ana Ekrana Ekle)
└───────────────┘
```

## Bileşenler

| Klasör              | Teknoloji                         | Görev                                            |
| ------------------- | --------------------------------- | ------------------------------------------------ |
| `backend/`          | Python · FastAPI · SQLAlchemy(async) · PostgreSQL · APScheduler | API, dual-token auth, QR üretimi, scan mantığı, cron |
| `kiosk-app/`        | React · Vite · qrcode.react       | Tam ekran tablet; QR'ı 15 sn'de bir yeniler; başarılı taramada yeşil "Giriş/Çıkış başarılı" onayı, doğum günü ilk girişinde kutlama gösterir (`?campus=<id>`) |
| `pwa-mobile-client/`| React · Vite · vite-plugin-pwa · html5-qrcode | Öğretmen PWA'sı: "Ana Ekrana Ekle", doğrudan kamera, sessiz oturum yenileme |
| `admin-app/`        | React · Vite                      | Müdür/genel merkez paneli: kampüs raporları, personel onayı, cihaz sıfırlama, manuel kayıt, izin/devamsızlık, CSV/Excel, müdür ve mesai saati yönetimi |

## Çok kampüslü yapı (5 kampüs · ~700 personel)

İkitelli OSB · İstanbul OSB · Esenyurt · Kıraç · Çorlu. Üç rol:

| Rol               | Giriş            | Kapsam                                            |
| ----------------- | ---------------- | ------------------------------------------------ |
| **Personel**      | Şifresiz, cihaz-bağlı (PWA) | QR okutur, kendi geçmişini görür       |
| **Kampüs Müdürü** | E-posta + şifre  | Kendi kampüsü: personel onay/sıfırlama + raporlar |
| **Genel Merkez**  | E-posta + şifre  | Tüm kampüsler + müdür/kampüs yönetimi            |

## Teknoloji seçimi

Backend için **FastAPI** seçildi: async I/O, otomatik OpenAPI dokümantasyonu
(`/docs`), Pydantic doğrulaması ve düşük bağımlılıkla en stabil sonucu verir.

## İş kuralları (özet)

1. **Dinamik QR (15 sn):** Backend, `jti` + `iat` + `exp` taşıyan kısa ömürlü
   bir JWT üretir (`QR_SECRET` ile imzalı). Kiosk bunu QR olarak gösterir ve
   süresi dolunca otomatik yeniler.
2. **Giriş-Çıkış (Toggle):** Öğretmen access token'ı + QR token'ı `/api/scan`'e
   gönderir. Backend:
   - QR token süresi geçtiyse → **400**.
   - Token daha önce kullanıldıysa (replay) → **409**.
   - Aksi halde o günkü son kayda bakar: kayıt yok / son kayıt OUT → **IN**;
     son kayıt IN → **OUT**.
3. **Gece sıfırlaması (23:59):** Hâlâ "içeride" (son kaydı IN) olan herkes için
   sistem `auto_closed_by_system` statüsünde bir OUT kaydı ekler.
4. **Zaman senkronizasyonu:** Tüm token üretim/doğrulaması ve gün sınırı
   **sunucu UTC saatine** göre yapılır; istemci saatine asla güvenilmez.
5. **Dual-token + cihaz kilidi (oturum güvenliği):**
   - Kayıt/girişte kısa ömürlü **access token** (≈15 dk) + 1 yıllık **refresh
     token** (localStorage) verilir.
   - Cihazdan üretilen **device fingerprint** oturuma bağlanır.
   - **Tek cihaz kuralı:** Aynı hesapla başka cihazdan giriş yapılırsa eski
     cihazın oturumu DB'den silinir (şifre/hesap paylaşımına karşı).
   - **Sessiz yenileme:** PWA her açılışta refresh token + fingerprint ile arka
     planda yeni access token alır; personel doğrudan kameraya düşer.
6. **Personel self-kaydı + müdür onayı:**
   - Personel PWA'da **ad-soyad, görev, branş, telefon, kampüs** girerek kaydolur
     (şifre yok). Hesap **beklemede** kalır; kampüs müdürü onaylayınca QR okutur.
   - **Telefon = kalıcı kimlik:** İlk tanıtılan cihaz hesaba kilitlenir. Başka
     telefondan aynı numarayla kayıt **reddedilir** (409) — bu kasıtlıdır.
7. **Telefon değişikliği (müdür yetkisi):** Personel telefon değiştirince müdür
   panelden **"Cihazı Sıfırla"** der; eski cihaz bağı silinir. Personel yeni
   telefonda **aynı numarayla** yeniden kaydolup cihazı bağlar (geçmiş korunur).
8. **Kampüs kapsamı:** Müdür yalnızca kendi kampüsünün personelini ve raporlarını
   görür/yönetir; genel merkez tüm kampüsleri görür ve `campus_id` ile filtreler.
9. **Manuel kayıt düzeltmesi:** Telefon arızalanırsa/unutulursa müdür panelden
   eksik IN/OUT kaydını **manuel olarak ekleyebilir**; var olan bir QR kaydını
   asla değiştiremez — bu kayıtlar raporlarda "manuel" olarak işaretlenir.
10. **İzin/devamsızlık takibi:** Müdür, personel için açık uçlu bir nedenle
    (sağlık raporu, ücretli izin, vb. — serbest metin) tarih aralıklı izin
    kaydı açar; aktif izin süresince QR okutma engellenir. Personel gelirse
    kayıt düzeltilir veya iptal edilir — scan hemen yeniden açılır. İzinle
    açıklanmayan devamsız günler raporlarda **"durum girilmedi" (unresolved)**
    olarak işaretlenir, hiçbir zaman sessizce atlanmaz.
11. **Raporlama:** Günlük/haftalık/aylık/yıllık veya keyfi tarih aralığı,
    geç kalma/erken çıkma toleransı (dakika) ve hafta sonu hariç tutma
    filtreleriyle en çok geç kalanlar, en çok erken çıkanlar, en çok devamsız
    olanlar ve izin türü istatistikleri; ham kayıtlar ve raporlar CSV/Excel
    olarak indirilebilir.
12. **Mesai saatleri yalnızca genel merkezde:** Her kampüsün mesai
    başlangıç/bitiş saatini sadece **genel merkez** belirler; geç kalma/erken
    çıkış raporları bu saatlere dayanır.
13. **Tablette tarama onayı:** Her başarılı QR taramasından hemen sonra
    tablette yeşil tikli "Giriş başarılı" / "Çıkış başarılı" + isim bildirimi
    çıkar (kiosk, kampüsünün son taramalarını yoklar; tablet kampüsünü
    `?campus=<id>` ile bilir).
14. **Doğum günü kutlaması:** Personel kayıtta **doğum tarihini** girer. Doğum
    günü bugün olan personel gün içindeki **ilk girişini** yapınca, ilgili
    kampüsün tableti yeşil onay yerine tam ekran "İyi ki doğdun!" kutlaması
    gösterir; kutlama yalnızca o kampüsün tabletlerinde çıkar.

## Hızlı başlangıç (Docker)

```bash
cp backend/.env.example backend/.env   # gizli anahtarları değiştirin
docker compose up --build
# Backend:  http://localhost:8000   (Swagger: /docs)
# İlk açılışta .env'deki bootstrap admin otomatik oluşturulur.
```

Detaylı kurulum için her klasördeki `README.md` dosyasına bakın.

## Güvenlik notları

- `AUTH_SECRET`, `REFRESH_SECRET` ve `QR_SECRET` **üç ayrı** anahtardır; bir
  alandaki sızıntı diğerinde token üretemez.
- Access token kısa ömürlü; refresh token cihaz parmak iziyle bağlanır ve tek
  cihazda geçerlidir (yeni giriş eskisini DB'den siler).
- QR token'lar tek kullanımlıktır (`used_qr_tokens` defteri ile replay koruması).
- Şifreler `bcrypt` ile hash'lenir; login bilinmeyen e-postada da bcrypt
  çalıştırır (zamanlama ile kullanıcı sızdırmaz).
- CORS yalnızca yapılandırılan origin'lere açıktır.
- `.env*` ve sırlar git'e dahil edilmez (`.gitignore`).
