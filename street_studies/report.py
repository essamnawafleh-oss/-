"""تقرير PDF لكل معاملة، وتصدير مجلد باسم صاحب المعاملة يضم التقرير وملف الأوتوكاد والمرفقات."""
import datetime
import html
import os
import shutil

from PySide6.QtCore import QMarginsF, QSizeF, Qt, QUrl
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPdfWriter, QTextDocument, QTextOption

from . import dxf_render, excel_export, theme
from .data import (
    MIX_ON_MIX, calc_reinforced, calc_rubble, format_file_size, format_num, safe_filename,
)

ACCENT = "#1A5F7A"


def owner_name(street):
    return safe_filename(street.get("name"))


def folder_name(street):
    base = owner_name(street)
    if street.get("pieceNo"):
        base += f" - قطعة {safe_filename(street['pieceNo'])}"
    return base


def _unique(path):
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{root} ({i}){ext}"):
        i += 1
    return f"{root} ({i}){ext}"


def _esc(v):
    return html.escape(str(v if v not in (None, "") else "—"))


def _tr(*cells):
    """صف جدول؛ Qt يرسم الجداول من اليسار لليمين دائماً لذلك نعكس ترتيب الخلايا."""
    return "<tr>" + "".join(reversed(cells)) + "</tr>"


def _row(label, value):
    return _tr(f'<td class="k">{_esc(label)}</td>', f"<td>{value}</td>")


def build_html(store, street, parcel_img=False, parcel_info=None, images=()):
    s = street
    L, W = s.get("length") or 0, s.get("width") or 0
    total = store.street_cost(s)
    mix = "خلطة على خلطة" if s.get("mixType") == MIX_ON_MIX else "خلطة على بيس كورس"
    today = datetime.date.today().strftime("%Y/%m/%d")

    info = "".join([
        _row("اسم المواطن", f"<b>{_esc(s.get('name'))}</b>"),
        _row("رقم القطعة", _esc(s.get("pieceNo"))),
        _row("المنطقة", _esc(s.get("region"))),
        _row("طبيعة العطاء", _esc(s.get("tenderType"))),
        _row("نوع الخلطة", _esc(mix)),
        _row("الطول × العرض", f"{L:g} م × {W:g} م"),
        _row("مساحة الطريق", f"{format_num(L * W)} م²"),
    ])
    if s.get("notes"):
        info += _row("ملاحظات", _esc(s["notes"]).replace("\n", "<br>"))

    rows = ""
    q = s.get("quantities") or {}
    for it in store.items:
        v = q.get(it["code"])
        if not v:
            continue
        price = float(it.get("price") or 0)
        rows += _tr(f"<td>{_esc(it['code'])}</td>", f"<td>{_esc(it['name'])}</td>", f"<td>{_esc(it['unit'])}</td>",
                    f'<td class="n">{format_num(v)}</td>', f'<td class="n">{format_num(price)}</td>',
                    f'<td class="n"><b>{format_num(v * price)}</b></td>')
    if not rows:
        rows = '<tr><td colspan="6" class="muted">لا توجد كميات مدخلة.</td></tr>'

    walls = ""
    for i, w in enumerate(s.get("walls") or [], 1):
        if w.get("type") == "reinforced":
            r = calc_reinforced(w.get("h") or 150, w.get("length") or 0)
            detail = (f"ارتفاع {w.get('h')} سم · طول {w.get('length') or 0:g} م — خرسانة "
                      f"<b>{r['total_conc']:.2f} م³</b> · حديد <b>{r['total_steel']:.1f} كجم</b>") if r else "غير مكتمل"
            walls += _tr(f'<td class="k">جدار مسلح #{i}</td>', f"<td>{detail}</td>")
        else:
            r = calc_rubble(w.get("L") or 0, w.get("H") or 0, w.get("hb") or 0)
            detail = (f"L={w.get('L') or 0:g} م · H={w.get('H') or 0:g} م · hb={w.get('hb') or 0:g} م — حجم كلي "
                      f"<b>{r['v_total']:.3f} م³</b> (جدار {r['v_wall']:.3f} + قاعدة {r['v_base']:.3f})") if r else "غير مكتمل"
            walls += _tr(f'<td class="k">جدار دبش وباطون #{i}</td>', f"<td>{detail}</td>")

    walls_html = f'<h2>الجدران</h2><table width="100%">{walls}</table>' if walls else ""

    parcel = ""
    if s.get("parcel"):
        p = s["parcel"]
        parcel = '<h2>مخطط قطعة الأرض</h2>'
        if parcel_img:
            parcel += '<p class="c"><img src="img://parcel" width="640"></p>'
        meta = f"ملف الأوتوكاد: <b>{_esc(p['name'])}</b> ({format_file_size(p.get('size'))}) — مرفق مع هذا التقرير."
        if parcel_info:
            meta += f"<br>{parcel_info}"
        parcel += f'<p class="muted">{meta}</p>'

    files = [a for a in s.get("attachments") or []]
    gallery = ""
    if images:
        gallery = "<h2>الصور</h2>" + "".join(
            f'<p class="c"><img src="img://att{i}" width="{wpx}"><br><span class="muted">{_esc(n)}</span></p>'
            for i, n, wpx in images)
    others = [a for a in files if not a.get("isImage")]
    if others:
        gallery += "<h2>المرفقات</h2><ul>" + "".join(
            f"<li>{_esc(a['name'])} — {format_file_size(a.get('size'))}</li>" for a in others) + "</ul>"

    return f"""
<html dir="rtl"><head><style>
body {{ color: #1B2428; }}
h1 {{ color: {ACCENT}; font-size: 20pt; margin: 0; }}
h2 {{ color: {ACCENT}; font-size: 13pt; margin-top: 18px; margin-bottom: 6px; }}
table {{ border-collapse: collapse; }}
td, th {{ padding: 5px 8px; border: 1px solid #D5DDE0; }}
th {{ background: {ACCENT}; color: #FFFFFF; font-weight: bold; }}
td.k {{ background: #F1F5F7; color: #56676E; font-weight: bold; width: 28%; }}
td.n {{ text-align: left; }}
.muted {{ color: #6B7B81; font-size: 9pt; }}
.c {{ text-align: center; }}
.total {{ background: #E7F4EC; color: #17804F; font-size: 13pt; font-weight: bold; }}
</style></head><body>
<table width="100%" cellpadding="0" style="border:none"><tr>
<td style="border:none; text-align:left" class="muted">التاريخ: {today}</td>
<td style="border:none"><h1>تقرير دراسة شارع</h1>
<span class="muted">تطبيق دراسات الشوارع الذكي</span></td></tr></table>
<hr>
<h2>بيانات المعاملة</h2>
<table width="100%">{info}</table>
<h2>الكميات والكلفة</h2>
<table width="100%">
<tr><th>الكلفة</th><th>سعر الوحدة</th><th>الكمية</th><th>الوحدة</th><th>البند</th><th>الكود</th></tr>
{rows}
<tr><td class="total n">{format_num(total)}</td><td colspan="5" class="total">إجمالي كلفة الشارع</td></tr>
</table>
{walls_html}
{parcel}
{gallery}
<br><p class="muted c">تم عمل هذا التطبيق بواسطة المهندس عمر الحمادين</p>
</body></html>"""


def write_pdf(store, street, path):
    doc = QTextDocument()
    doc.setDefaultFont(theme.font(10))
    opt = QTextOption()
    opt.setTextDirection(Qt.LayoutDirection.RightToLeft)
    opt.setAlignment(Qt.AlignmentFlag.AlignRight)
    doc.setDefaultTextOption(opt)

    parcel_img, parcel_info = False, None
    p = street.get("parcel")
    if p and p.get("path") and p["name"].lower().endswith(".dxf"):
        try:
            d = dxf_render.load(p["path"])
            img = dxf_render.render(d, 1800, 1200, line_width=1.6)
            doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl("img://parcel"), img)
            parcel_img = True
            area = dxf_render.area_of_largest_closed(d)
            parcel_info = f"أبعاد الرسم: {dxf_render.size_text(d)}"
            if area:
                parcel_info += f" · مساحة أكبر شكل مغلق: {format_num(area)} (بوحدات الرسم المربعة)"
        except ValueError as e:
            parcel_info = str(e)

    images = []
    for i, a in enumerate(street.get("attachments") or []):
        if a.get("isImage") and a.get("path"):
            img = QImage(a["path"])
            if img.isNull():
                continue
            if img.width() > 1600:
                img = img.scaledToWidth(1600, Qt.TransformationMode.SmoothTransformation)
            doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(f"img://att{i}"), img)
            # الصور الطولية تُصغّر حتى لا تتجاوز ارتفاع الصفحة
            wpx = 640 if img.width() >= img.height() else int(640 * img.width() / img.height() * 0.9)
            images.append((i, a["name"], max(200, wpx)))

    doc.setHtml(build_html(store, street, parcel_img, parcel_info, images))

    writer = QPdfWriter(path)
    writer.setTitle(f"تقرير دراسة شارع — {street.get('name', '')}")
    writer.setCreator("تطبيق دراسات الشوارع الذكي")
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                     QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter))
    writer.setResolution(144)
    # تخطيط المستند بعرض منطقة الطباعة (بنقاط الكاتب) حتى تتناسب الصور والجداول
    rect = writer.pageLayout().paintRectPixels(writer.resolution())
    doc.setPageSize(QSizeF(rect.width(), rect.height()))
    doc.print_(writer)


def export_report(store, street, out_dir, with_excel=True):
    """ينشئ مجلداً باسم صاحب المعاملة ويرجع مساره."""
    name = owner_name(street)
    folder = _unique(os.path.join(out_dir, folder_name(street)))
    os.makedirs(folder)

    s = dict(street)
    if s.get("parcel"):
        s["parcel"] = dict(s["parcel"], path=store.attachment_path(s["parcel"]))
    s["attachments"] = [dict(a, path=store.attachment_path(a)) for a in s.get("attachments") or []]

    write_pdf(store, s, os.path.join(folder, f"{name}.pdf"))
    if with_excel:
        excel_export.export(store, [street], os.path.join(folder, f"{name}.xlsx"),
                            street.get("region", ""), street.get("tenderType", ""))
    if s.get("parcel") and os.path.exists(s["parcel"]["path"]):
        ext = os.path.splitext(s["parcel"]["name"])[1].lower()
        shutil.copy2(s["parcel"]["path"], _unique(os.path.join(folder, f"{name} - مخطط القطعة{ext}")))
    for a in s["attachments"]:
        if os.path.exists(a["path"]):
            shutil.copy2(a["path"], _unique(os.path.join(folder, f"{name} - {safe_filename(a['name'])}")))
    return folder
