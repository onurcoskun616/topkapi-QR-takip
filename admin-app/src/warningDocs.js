// Printable HR documents (İhtar / Tutanak) for late-arrival and absence.
// Opens a formatted A4 document in a new window with a print button; the school
// name and principal name are pre-filled but editable in the page so they can be
// corrected before printing/saving as PDF. Two witness signature blocks are
// included on the Tutanak. No backend/library needed — the browser prints it.

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]
  );
}

function fmtDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function periodText(start, end) {
  if (!start) return "";
  if (!end || start === end) return fmtDate(start);
  return `${fmtDate(start)} – ${fmtDate(end)} tarihleri arasında`;
}

const TITLES = {
  late: { ihtar: "İŞE İZİNSİZ GEÇ GELME İHTARI", tutanak: "İŞE İZİNSİZ GEÇ GELME TUTANAĞI" },
  absent: { ihtar: "İŞE İZİNSİZ GELMEME İHTARI", tutanak: "İŞE İZİNSİZ GELMEME TUTANAĞI" },
};

// The "olay" (incident) sentence, tailored to late vs absent and day count.
function incidentSentence(kind, days, period) {
  const p = period ? `${period}` : "ilgili dönemde";
  if (kind === "late") {
    return `Yukarıda bilgileri yer alan personelin, ${esc(p)} <strong>${days}</strong> iş günü, ` +
      `işyerine <strong>izinsiz ve mazeretsiz olarak geç geldiği</strong> giriş-çıkış kayıtlarından tespit edilmiştir.`;
  }
  return `Yukarıda bilgileri yer alan personelin, ${esc(p)} <strong>${days}</strong> iş günü, ` +
    `işyerine <strong>izinsiz ve mazeretsiz olarak gelmediği</strong> giriş-çıkış kayıtlarından tespit edilmiştir.`;
}

function ihtarBody(kind, days, period) {
  const closing = kind === "late"
    ? "Bu davranışınızın tekrarı hâlinde hakkınızda 4857 sayılı İş Kanunu ve ilgili mevzuat çerçevesinde işlem yapılacağını, iş bu ihtar ile <strong>ihtaren</strong> bildiririz."
    : "Bu davranışınızın tekrarı hâlinde ve devamsızlığın mazeretsiz sürmesi durumunda hakkınızda 4857 sayılı İş Kanunu ve ilgili mevzuat çerçevesinde işlem yapılacağını, iş bu ihtar ile <strong>ihtaren</strong> bildiririz.";
  return `
    <p>Sayın <strong class="ec">%NAME%</strong>,</p>
    <p>${incidentSentence(kind, days, period)}</p>
    <p>İş sözleşmeniz ve çalışma düzenimiz gereği, mesai saatlerine riayet etmeniz ve
       devamsızlık/geç kalma durumlarında önceden yazılı izin almanız zorunludur.</p>
    <p>${closing}</p>
    <p>Gereğini bilgilerinize rica ederiz.</p>`;
}

function tutanakBody(kind, days, period) {
  return `
    <p>${incidentSentence(kind, days, period)}</p>
    <p>Durum, tarafımızca tespit edilerek iş bu tutanak <strong>iki şahit huzurunda</strong>
       tanzim edilmiş, ilgili personele tebliğ edilmek üzere düzenlenmiştir.</p>`;
}

/**
 * Open a printable İhtar or Tutanak document in a new window.
 * @param {object} o
 * @param {"late"|"absent"} o.kind
 * @param {"ihtar"|"tutanak"} o.docType
 * @param {object} o.person   { full_name, job_title, branch, campus_name, days }
 * @param {string} o.school    pre-fill for employer/school name
 * @param {string} o.principal pre-fill for the principal (Okul Müdürü)
 * @param {string} o.periodStart ISO date
 * @param {string} o.periodEnd   ISO date
 * @param {string} o.issueDate   ISO date (today)
 */
export function openWarningDoc(o) {
  const title = TITLES[o.kind][o.docType];
  const days = o.person.days || 1;
  const period = periodText(o.periodStart, o.periodEnd);
  const role = [o.person.job_title, o.person.branch].filter(Boolean).join(" / ") || "-";
  const bodyHtml = (o.docType === "ihtar" ? ihtarBody : tutanakBody)(o.kind, days, period)
    .replace("%NAME%", esc(o.person.full_name));

  const witnesses = o.docType === "tutanak"
    ? `
      <div class="sign-row">
        <div class="sign"><div class="sign-line"></div>Şahit 1<br/><span class="hint">(Ad Soyad / İmza)</span></div>
        <div class="sign"><div class="sign-line"></div>Şahit 2<br/><span class="hint">(Ad Soyad / İmza)</span></div>
      </div>`
    : "";

  const receipt = o.docType === "ihtar"
    ? `
      <div class="sign-row">
        <div class="sign"><div class="sign-line"></div>İhtarı Tebliğ Eden<br/><span class="ed">%PRINCIPAL%</span><br/><span class="hint">Okul Müdürü</span></div>
        <div class="sign"><div class="sign-line"></div>Tebellüğ Eden (Personel)<br/><span class="hint">${esc(o.person.full_name)}</span></div>
      </div>`
    : `
      <div class="sign-row">
        <div class="sign"><div class="sign-line"></div>Tutanağı Düzenleyen<br/><span class="ed">%PRINCIPAL%</span><br/><span class="hint">Okul Müdürü</span></div>
        <div class="sign"><div class="sign-line"></div>Tebellüğ Eden (Personel)<br/><span class="hint">${esc(o.person.full_name)}</span></div>
      </div>`;

  const html = `<!doctype html><html lang="tr"><head><meta charset="utf-8"/>
<title>${esc(title)} — ${esc(o.person.full_name)}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: "Times New Roman", Georgia, serif; color:#111; margin:0; background:#f3f3f3; }
  .toolbar { position:sticky; top:0; background:#0b1f3a; color:#fff; padding:10px 16px; display:flex; gap:10px; }
  .toolbar button { font:inherit; padding:8px 14px; border:0; border-radius:6px; cursor:pointer; }
  .print { background:#f5c518; }
  .close { background:#334155; color:#fff; }
  .page { background:#fff; width:210mm; min-height:297mm; margin:16px auto; padding:24mm 22mm; box-shadow:0 2px 10px rgba(0,0,0,.2); }
  .school { text-align:center; font-size:15pt; font-weight:bold; text-transform:uppercase; }
  h1 { text-align:center; font-size:14pt; margin:26px 0 20px; text-decoration:underline; }
  table.meta { width:100%; border-collapse:collapse; margin:0 0 18px; font-size:11.5pt; }
  table.meta td { border:1px solid #333; padding:6px 9px; }
  table.meta td.k { width:34%; background:#f4f4f4; font-weight:bold; }
  p { font-size:12pt; line-height:1.7; text-align:justify; margin:10px 0; }
  .date { text-align:right; font-size:11.5pt; margin:22px 0 26px; }
  .sign-row { display:flex; justify-content:space-between; gap:30px; margin-top:40px; }
  .sign { flex:1; text-align:center; font-size:11pt; }
  .sign-line { border-top:1px solid #333; margin-bottom:6px; height:48px; }
  .hint { color:#555; font-size:9.5pt; }
  .ed, .ec { border-bottom:1px dotted #999; outline:none; }
  .ed:focus, .ec:focus { background:#fff8d6; }
  @media print {
    .toolbar { display:none; }
    body { background:#fff; }
    .page { box-shadow:none; margin:0; width:auto; min-height:auto; padding:18mm 20mm; }
  }
</style></head>
<body>
  <div class="toolbar">
    <button class="print" onclick="window.print()">🖨️ Yazdır / PDF Kaydet</button>
    <button class="close" onclick="window.close()">Kapat</button>
    <span style="align-self:center;opacity:.85">Okul adı ve müdür adını yazdırmadan önce düzenleyebilirsiniz (üzerine tıklayın).</span>
  </div>
  <div class="page">
    <div class="school" contenteditable="true">%SCHOOL%</div>
    <h1>${esc(title)}</h1>
    <table class="meta">
      <tr><td class="k">Personel (Ad Soyad)</td><td>${esc(o.person.full_name)}</td></tr>
      <tr><td class="k">Görev / Branş</td><td>${esc(role)}</td></tr>
      <tr><td class="k">Kampüs / Birim</td><td>${esc(o.person.campus_name || "-")}</td></tr>
      <tr><td class="k">Dönem</td><td>${esc(period || "-")}</td></tr>
      <tr><td class="k">Gün Sayısı</td><td>${days}</td></tr>
    </table>
    ${bodyHtml}
    ${witnesses}
    <div class="date">Tarih: ${fmtDate(o.issueDate)}</div>
    ${receipt}
  </div>
  <script>
    // Make the school / principal names editable inline.
    document.querySelectorAll('.ed').forEach(function(el){ el.setAttribute('contenteditable','true'); });
  </script>
</body></html>`
    .replaceAll("%SCHOOL%", esc(o.school || o.person.campus_name || "OKUL ADI"))
    .replaceAll("%PRINCIPAL%", esc(o.principal || "Okul Müdürü"));

  const w = window.open("", "_blank");
  if (!w) {
    alert("Belge penceresi açılamadı — tarayıcı açılır pencere iznini kontrol edin.");
    return;
  }
  w.document.write(html);
  w.document.close();
}
