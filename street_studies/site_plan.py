"""قراءة «مخطط موقع وترسيم» (PDF أو صورة) واستخراج بيانات القطعة والمالك وأحكام التنظيم.

- PDF رقمي: القراءة بمواضع الحروف على الصفحة (أدق طريقة). خط هذه المخططات يخزّن الحرفين «لا»
  بترتيب معكوس (ال)، فنكتشف ذلك من الألف ذات العرض الصفري ونعيد ترتيبه.
- صورة أو PDF ممسوح ضوئياً: قراءة النص بـ Tesseract (OCR) ثم تقسيم كل سطر عند «:».
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:
    import pymupdf
except ImportError:  # pragma: no cover
    pymupdf = None

from .data import resource_path

FIELDS = {
    "owner": "اسم المالك",
    "pieceNo": "رقم القطعة",
    "plate": "رقم اللوحة",
    "basin": "الحوض",
    "hay": "الحي",
    "village": "القرية",
    "parcelArea": "مساحة القطعة (م²)",
    "landUse": "استعمال القطعة",
    "planDate": "تاريخ المخطط",
}
ZONING_FIELDS = [
    ("use", "صفة الاستعمال"), ("front", "الارتداد الأمامي (م)"), ("side", "الارتداد الجانبي (م)"),
    ("back", "الارتداد الخلفي (م)"), ("coverage", "نسبة مساحة البناء"), ("floorRatio", "النسبة الطابقية"),
    ("floors", "عدد الطوابق"), ("height", "ارتفاع البناء (م)"), ("frontage", "الواجهة الأمامية (م)"),
    ("minLot", "مساحة الإفراز (م²)"),
]
# عناوين أعمدة جدول الأحكام في المخطط ← المفتاح
_ZONING_HEADERS = [
    ("صفة الاستعمال", "use"), ("الامامي", "front"), ("الجانبي", "side"), ("الخلفي", "back"),
    ("مساحة البناء", "coverage"), ("الطابقية", "floorRatio"), ("عدد الطوابق", "floors"),
    ("رتفاع البناء", "height"), ("الواجهه الامامية", "frontage"), ("مساحة الافراز", "minLot"),
]

_BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff]")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize(s):
    s = _BIDI.sub("", str(s or "")).translate(_AR_DIGITS)
    return re.sub(r"[ \t]+", " ", s).strip()


def _clean_value(s):
    s = normalize(s).strip(" :؛-–")
    return re.sub(r"\s+", " ", s)


def _split_name_number(s):
    """«البلد (012)» ← ("البلد", "012")؛ يقبل الأقواس المعكوسة من استخراج PDF/OCR."""
    s = _clean_value(s)
    s = re.sub(r"[(\[]\s*([0-9Oo]{2,4})\s*[)\]]", lambda m: "(" + m.group(1).replace("O", "0").replace("o", "0") + ")", s)
    s = re.sub(r"[A-Za-z]+", " ", s)
    m = re.search(r"[()]?\s*(\d{1,4})\s*[()]?", s)
    num = m.group(1) if m else ""
    name = _clean_value(re.sub(r"[()]?\s*\d{1,4}\s*[()]?", " ", s)) if m else s
    return name, num


# ---------------------------------------------------------------- PDF بالمواضع
def _pdf_rows(page):
    """صفوف الصفحة: لكل صف قائمة مقاطع، ولكل مقطع نصّه وحروفه مع مواضعها (بعد إصلاح «لا»)."""
    raw = page.get_text("rawdict")
    rows = []
    for b in raw["blocks"]:
        for line in b.get("lines", []):
            for sp in line["spans"]:
                cs = sp["chars"]
                chars = []
                i = 0
                while i < len(cs):
                    c = cs[i]
                    if (c["c"] in "اأإآ" and abs(c["bbox"][2] - c["bbox"][0]) < 0.05 and i + 1 < len(cs)
                            and cs[i + 1]["c"] == "ل"):
                        nxt = cs[i + 1]
                        chars.append(("ل", nxt["bbox"][0], nxt["bbox"][2]))
                        chars.append((c["c"], nxt["bbox"][0], nxt["bbox"][2]))
                        i += 2
                        continue
                    chars.append((c["c"], c["bbox"][0], c["bbox"][2]))
                    i += 1
                text = "".join(ch for ch, _, _ in chars)
                if not text.strip():
                    continue
                y = (sp["bbox"][1] + sp["bbox"][3]) / 2
                row = next((r for r in rows if abs(r["y"] - y) < 4), None)
                if row is None:
                    row = {"y": y, "spans": []}
                    rows.append(row)
                row["spans"].append({"text": text, "chars": chars, "x0": sp["bbox"][0], "x1": sp["bbox"][2]})
    rows.sort(key=lambda r: r["y"])
    return rows


def _find_labels(row, labels):
    """مواضع العناوين في الصف: [(المفتاح، x0، x1)]."""
    found = []
    for key, lab in labels:
        # أقصر مقطع يحوي العنوان («الامامي» موجودة أيضاً داخل «الواجهه الامامية»)
        hits = [sp for sp in row["spans"] if lab in sp["text"]]
        if not hits:
            continue
        sp = min(hits, key=lambda h: len(h["text"]))
        i = sp["text"].find(lab)
        xs = [x for _, a, b in sp["chars"][i:i + len(lab)] for x in (a, b)]
        found.append((key, min(xs), max(xs), sp))
    return found


def _row_values(row, found):
    """قيمة كل عنوان = الحروف الواقعة يسار العنوان حتى العنوان التالي (الكتابة من اليمين لليسار)."""
    found = sorted(found, key=lambda f: -f[2])
    out = {}
    label_ranges = []
    for key, x0, x1, sp in found:
        # العنوان يمتد حتى نهاية مقطعه من جهة اليسار (يشمل «:» و«/م2»)
        label_ranges.append((sp["x0"] if sp["x1"] - sp["x0"] < 90 else x0 - 6, x1))
    for n, (key, x0, x1, _sp) in enumerate(found):
        left_bound = found[n + 1][2] if n + 1 < len(found) else -1
        parts = []
        for sp in sorted(row["spans"], key=lambda s: -s["x1"]):
            seg = []
            for ch, a, b in sp["chars"]:
                xc = (a + b) / 2
                if left_bound < xc < x0 and not any(lo - 0.5 <= xc <= hi + 0.5 for lo, hi in label_ranges):
                    seg.append(ch)
            if seg:
                parts.append("".join(seg))
        out[key] = _clean_value(" ".join(parts))
    return out


_ROW1 = [("pieceNo", "رقم القطعة"), ("plate", "رقم اللوحة"), ("basin", "الحوض"), ("village", "اسم القرية")]
_ROW0 = [("owner", "اسم المالك"), ("hay", "الحي"), ("parcelArea", "مساحة القطعة")]


def parse_pdf_page(page):
    rows = _pdf_rows(page)
    data, zoning = {}, {}
    full = normalize(" ".join(sp["text"] for r in rows for sp in r["spans"]))
    m = re.search(r"(\d{4}/\d{1,2}/\d{1,2})", full)
    if m:
        data["planDate"] = m.group(1)
    header = values = None
    for i, row in enumerate(rows):
        for labels in (_ROW0, _ROW1, [("landUse", "استعمال القطعة")]):
            found = _find_labels(row, labels)
            if len(found) >= (1 if len(labels) == 1 else 2):
                data.update({k: v for k, v in _row_values(row, found).items() if v})
        if header is None and len(_find_labels(row, [(k, h) for h, k in _ZONING_HEADERS])) >= 6:
            header = row
            values = next((r for r in rows[i + 1:i + 3] if any(re.search(r"\d", s["text"]) for s in r["spans"])), None)
    if header is not None and values is not None:
        zoning = _zoning_from_positions(
            [(k, (x0 + x1) / 2) for k, x0, x1, _ in _find_labels(header, [(k, h) for h, k in _ZONING_HEADERS])],
            [(ch, (a + b) / 2) for sp in sorted(values["spans"], key=lambda s: -s["x1"]) for ch, a, b in sp["chars"]])
    return _finish(data, zoning)


def _zoning_from_positions(cols, chars):
    """يوزّع حروف صف القيم على أعمدة جدول الأحكام حسب أقرب عنوان."""
    cols = sorted(cols, key=lambda c: c[1])
    out = {}
    has_use = any(k == "use" for k, _ in cols)
    for ch, xc in chars:
        # الحروف العربية لا تكون إلا في عمود «صفة الاستعمال»؛ الأرقام تذهب لأقرب عمود
        if has_use and (re.match(r"[\u0621-\u064a ]", ch)):
            key = "use"
        else:
            key = min(cols, key=lambda c: abs(c[1] - xc))[0]
        out[key] = out.get(key, "") + ch
    return {k: _clean_value(v) for k, v in out.items() if _clean_value(v)}


# ---------------------------------------------------------------- OCR / نص حر
_LABEL_PATTERNS = [
    ("owner", r"اسم\s*ال?مال[كل]|المالك"),
    ("parcelArea", r"[مف][سص]اح[هة]\s*القطع[هة](?:\s*/?\s*م\s*2?)?"),
    ("pieceNo", r"رقم\s*القطع[هة]"),
    ("plate", r"رقم\s*اللوح[هة]"),
    ("basin", r"(?:اسم\s*و\s*)?رقم\s*الحوض|الحوض"),
    ("village", r"اسم\s*القري[هة]|القري[هة]"),
    ("landUse", r"استعمال\s*القطع[هة]"),
    # «الحي» تُقرأ أحياناً «للحي» أو بلا ألف؛ نشترط أن يتبعها فاصل
    ("hay", r"(?<![\u0621-\u064a])(?:ا|ل)?لحي(?=\s*[:+؛=]|\s+[\u0621-\u064a]+\s*[(\[)]\s*\d)"),
    ("planDate", r"تاريخ\s*الوصل"),
]
_SEP = " :+;؛=-–|"


def _label_hits(line):
    """كل العناوين في السطر بالترتيب: [(المفتاح، البداية، النهاية)] بدون تداخل."""
    hits = []
    for key, pat in _LABEL_PATTERNS:
        for m in re.finditer(pat, line):
            hits.append((m.start(), m.end(), key))
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    out, last_end = [], -1
    for a, b, key in hits:
        if a >= last_end:
            out.append((key, a, b))
            last_end = b
    return out


def parse_text_lines(lines):
    """تحليل أسطر منطقية «عنوان : قيمة عنوان : قيمة …» (من OCR أو نص PDF غير معروف التخطيط).
    القيمة = النص بين نهاية العنوان وبداية العنوان التالي، فلا نعتمد على «:» التي قد تُقرأ خطأً."""
    data = {}
    for raw in lines:
        line = normalize(raw)
        hits = _label_hits(line)
        for n, (key, a, b) in enumerate(hits):
            nxt = hits[n + 1][1] if n + 1 < len(hits) else len(line)
            v = line[b:nxt].strip(_SEP)
            if key == "owner":
                v = re.sub(r"[A-Za-z]+\S*", " ", v)  # بقايا عنوان «الحي» المقروء خطأ
            if key == "planDate":
                m = re.search(r"\d{4}/\d{1,2}/\d{1,2}", v + " " + line)
                v = m.group(0) if m else ""
            if key == "parcelArea" and not re.search(r"\d", v):
                # «703 جدول الأحياء (000) مساحة القطعة /م2:» — الرقم قبل العنوان بسبب ترتيب الاتجاهات
                m = re.search(r"(?:^|\s)(\d{2,7}(?:\.\d+)?)(?=\s)", line[:a])
                v = m.group(1) if m and float(m.group(1)) >= 20 else ""
            v = _clean_value(v)
            if v and key not in data:
                data[key] = v
    return _finish(data, {})


# ---------------------------------------------------------------- تنظيف وتوحيد
def _finish(data, zoning):
    out = {}
    if data.get("owner"):
        own = re.sub(r"[^\u0621-\u064a\s]", " ", data["owner"])
        own = re.sub(r"\s+", " ", own).strip()
        if len(own.split()) >= 2 and not re.match(r"^(وادي|وادى)\s*موسى", own):
            out["owner"] = own[:80]
    if data.get("pieceNo"):
        m = re.search(r"\d{1,6}", data["pieceNo"])
        if m:
            out["pieceNo"] = m.group(0)
    if data.get("plate"):
        m = re.search(r"\d{1,5}", data["plate"])
        if m:
            out["plate"] = m.group(0)
    for key in ("basin", "hay"):
        if data.get(key):
            name, num = _split_name_number(data[key])
            if name or num:
                out[key] = name
                out[key + "No"] = num
    if data.get("village"):
        v = re.sub(r"[^\u0621-\u064a\s]", " ", data["village"])
        out["village"] = re.sub(r"\s+", " ", v).strip().replace("وادى موسى", "وادي موسى")
    if data.get("parcelArea"):
        # «/م2 : 815» — نأخذ أكبر رقم ونتجاهل «2» الخاصة بوحدة المتر المربع
        nums = [n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", data["parcelArea"])]
        nums = [n for n in nums if float(n) >= 40]
        if nums:
            out["parcelArea"] = max(nums, key=float)
    if data.get("landUse"):
        out["landUse"] = _clean_value(re.sub(r"[A-Za-z]+", " ", data["landUse"]))
    if data.get("planDate"):
        out["planDate"] = data["planDate"]
    z = {}
    for k, v in (zoning or {}).items():
        if k == "use":
            z[k] = _clean_value(re.sub(r"[\d.]+", " ", v))
            # رقم الارتداد الأمامي يلتصق أحياناً بصفة الاستعمال
            m = re.match(r"^\s*(\d+(?:\.\d+)?)", v)
            if m and "front" not in zoning:
                z["front"] = m.group(1)
        else:
            m = re.search(r"\d+(?:\.\d+)?\s*%?", v)
            if m:
                z[k] = m.group(0).replace(" ", "")
    if z:
        out["zoning"] = z
    return out


# ---------------------------------------------------------------- OCR
def tesseract_path():
    exe = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    bundled = resource_path("tesseract", exe)
    if os.path.exists(bundled):
        return bundled
    found = shutil.which("tesseract")
    if found:
        return found
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            p = os.path.join(base, "Tesseract-OCR", "tesseract.exe")
            if base and os.path.exists(p):
                return p
    return None


def _ocr_lines(image_path, psm=6):
    exe = tesseract_path()
    if not exe:
        raise RuntimeError("محرك قراءة الصور (Tesseract) غير متوفر")
    env = dict(os.environ)
    tessdata = resource_path("tesseract", "tessdata")
    if os.path.isdir(tessdata):
        env["TESSDATA_PREFIX"] = tessdata
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    res = subprocess.run([exe, image_path, "stdout", "-l", "ara+eng", "--psm", str(psm), "tsv"],
                         capture_output=True, env=env, timeout=120, creationflags=flags)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.decode("utf-8", "replace")[:300] or "فشل OCR")
    rows = {}
    for ln in res.stdout.decode("utf-8", "replace").splitlines()[1:]:
        p = ln.split("\t")
        if len(p) < 12 or not p[11].strip():
            continue
        key = (int(p[2]), int(p[3]), int(p[4]))
        rows.setdefault(key, []).append((int(p[6]), p[11]))
    # ترتيب الكلمات من اليمين لليسار يعطي الترتيب المنطقي للسطر العربي
    return [" ".join(w for _, w in sorted(words, key=lambda t: -t[0])) for _, words in sorted(rows.items())]


def _prepare_image(src):
    """تكبير الصور الصغيرة وتحويلها لرمادي قبل OCR."""
    from PySide6.QtGui import QImage
    img = QImage(src)
    if img.isNull():
        raise RuntimeError("تعذّر فتح الصورة")
    if img.width() < 1800:
        img = img.scaledToWidth(2200)
    img = img.convertToFormat(QImage.Format.Format_Grayscale8)
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)
    return path


def read_site_plan(path):
    """يرجع (data, method). data: الحقول المستخرجة (قد تكون ناقصة)، method: pdf أو pdf-text أو ocr."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        if pymupdf is None:
            raise RuntimeError("مكتبة قراءة PDF غير متوفرة")
        doc = pymupdf.open(path)
        page = doc[0]
        data = parse_pdf_page(page)
        if len(data) >= 3:
            return data, "pdf"
        text_lines = page.get_text("text").splitlines()
        alt = parse_text_lines(text_lines)
        if len(alt) > len(data):
            data = alt
        if len(data) >= 3:
            return data, "pdf-text"
        # PDF ممسوح ضوئياً: نحوّل الصفحة لصورة ثم OCR
        fd, png = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        page.get_pixmap(dpi=220).save(png)
        try:
            return _ocr_best(png), "ocr"
        finally:
            os.remove(png)
    prepared = _prepare_image(path)
    try:
        return _ocr_best(prepared), "ocr"
    finally:
        os.remove(prepared)


def _ocr_best(image):
    """تمريرة OCR أولى بتخطيط «كتلة واحدة»، وثانية بتخطيط «أعمدة» إن كانت النتيجة ناقصة."""
    best = parse_text_lines(_ocr_lines(image, 6))
    if len(best) < 6:
        alt = parse_text_lines(_ocr_lines(image, 4))
        merged = dict(alt, **best)
        if len(merged) > len(best):
            best = merged
    return best


def render_first_page(path, width_px=1400):
    """صورة الصفحة الأولى من PDF (لعرضها في التقرير). يرجع QImage أو None."""
    if pymupdf is None or not path.lower().endswith(".pdf"):
        return None
    from PySide6.QtGui import QImage
    page = pymupdf.open(path)[0]
    zoom = width_px / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                 QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888)
    return img.copy()


def summary_lines(sp):
    """أسطر عرض مختصرة لبيانات المخطط."""
    out = []
    if sp.get("pieceNo"):
        out.append(f"قطعة {sp['pieceNo']}" + (f" · لوحة {sp['plate']}" if sp.get("plate") else ""))
    if sp.get("basin"):
        out.append(f"حوض {sp['basin']}" + (f" ({sp['basinNo']})" if sp.get("basinNo") else ""))
    if sp.get("hay"):
        out.append(f"حي {sp['hay']}" + (f" ({sp['hayNo']})" if sp.get("hayNo") else ""))
    if sp.get("village"):
        out.append(sp["village"])
    if sp.get("parcelArea"):
        out.append(f"مساحة {sp['parcelArea']} م²")
    return out
