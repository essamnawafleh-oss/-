"""البيانات الثابتة، التخزين على القرص، والحسابات."""
import copy
import json
import os
import re
import shutil
import sys
import uuid

APP_NAME = "StreetStudies"

REINFORCED_TABLE = [
    {"H": 150, "B": 75, "C": 20, "D": 30, "t": 25, "conc": 0.53, "steel": 26.79},
    {"H": 200, "B": 110, "C": 25, "D": 30, "t": 25, "conc": 0.75, "steel": 39.84},
    {"H": 250, "B": 145, "C": 30, "D": 30, "t": 25, "conc": 0.99, "steel": 53.12},
    {"H": 300, "B": 170, "C": 40, "D": 30, "t": 30, "conc": 1.25, "steel": 98.39},
    {"H": 350, "B": 205, "C": 45, "D": 35, "t": 35, "conc": 1.66, "steel": 124.58},
    {"H": 400, "B": 240, "C": 50, "D": 40, "t": 40, "conc": 2.13, "steel": 155.73},
    {"H": 450, "B": 275, "C": 60, "D": 45, "t": 45, "conc": 2.66, "steel": 201.96},
    {"H": 500, "B": 310, "C": 70, "D": 50, "t": 45, "conc": 3.13, "steel": 247.51},
    {"H": 550, "B": 340, "C": 85, "D": 55, "t": 50, "conc": 3.73, "steel": 271.25},
    {"H": 600, "B": 370, "C": 100, "D": 60, "t": 55, "conc": 4.38, "steel": 341.22},
    {"H": 650, "B": 405, "C": 105, "D": 65, "t": 60, "conc": 5.12, "steel": 521.60},
    {"H": 700, "B": 435, "C": 110, "D": 75, "t": 65, "conc": 6.08, "steel": 556.85},
    {"H": 750, "B": 470, "C": 115, "D": 85, "t": 75, "conc": 7.32, "steel": 688.95},
    {"H": 800, "B": 505, "C": 120, "D": 95, "t": 80, "conc": 8.50, "steel": 734.94},
    {"H": 850, "B": 540, "C": 130, "D": 105, "t": 90, "conc": 9.95, "steel": 814.38},
    {"H": 900, "B": 580, "C": 140, "D": 115, "t": 100, "conc": 11.78, "steel": 859.86},
    {"H": 950, "B": 630, "C": 150, "D": 130, "t": 110, "conc": 13.73, "steel": 1067.31},
    {"H": 1000, "B": 700, "C": 160, "D": 140, "t": 120, "conc": 16.04, "steel": 1204.33},
]

DEFAULT_REGIONS = ["وادي موسى", "البقعة", "الطيبة", "الراجف", "دلاغة", "ام صيحون والعمارين"]

TENDER_TYPES = ["خلطات", "تصريف"]
MIX_ON_BASE = "على_بيس"
MIX_ON_MIX = "على_خلطة"

WALL_RUBBLE_CODE = "RD-005"
WALL_REINFORCED_CODE = "RD-006"

_ROADS = "أعمال طرق"
_DRAIN = "تصريف مياه الأمطار"

DEFAULT_ITEMS = [
    {"code": "RD-001", "group": _ROADS, "name": "تسوية", "unit": "م²", "price": 0, "auto": "tasweya"},
    {"code": "RD-004", "group": _ROADS, "name": "Base Course", "unit": "م²", "price": 0, "auto": "basecourse"},
    {"code": "ASP-002", "group": _ROADS, "name": "خلطة إسفلتية ساخنة", "unit": "م²", "price": 0, "auto": "khalta"},
    {"code": "ASP-001", "group": _ROADS, "name": "قشط إسفلت", "unit": "م²", "price": 0},
    {"code": "RD-002", "group": _ROADS, "name": "حفر", "unit": "م³", "price": 0},
    {"code": "RD-003", "group": _ROADS, "name": "ردم", "unit": "م³", "price": 0},
    {"code": "RD-005", "group": _ROADS, "name": "جدران دبش وباطون", "unit": "م³", "price": 0},
    {"code": "RD-006", "group": _ROADS, "name": "جدران مسلحة", "unit": "م³", "price": 0},
    {"code": "RD-007", "group": _ROADS, "name": "حبسات", "unit": "م³", "price": 0},
    {"code": "RD-008", "group": _ROADS, "name": "دهان طرق", "unit": "م²", "price": 0},
    {"code": "RD-009", "group": _ROADS, "name": "دهان كندرين", "unit": "م.ط", "price": 0},
    {"code": "RD-010", "group": _ROADS, "name": "كندرين", "unit": "م.ط", "price": 0},
    {"code": "RD-011", "group": _ROADS, "name": "بلاط", "unit": "م²", "price": 0},
    {"code": "RD-012", "group": _ROADS, "name": "إنترلوك", "unit": "م²", "price": 0},
    {"code": "RD-013", "group": _ROADS, "name": "ربراب", "unit": "م²", "price": 0},
    {"code": "RD-014", "group": _ROADS, "name": "قناة خرسانية مفتوحة", "unit": "م³", "price": 0},
    {"code": "RD-015", "group": _ROADS, "name": "قناة خرسانية مسلحة", "unit": "م³", "price": 0},
    {"code": "RD-016", "group": _ROADS, "name": "عبارة صندوقية", "unit": "م³", "price": 0},
    {"code": "RD-017", "group": _ROADS, "name": "جدران حجرية", "unit": "م.ط", "price": 0},
    {"code": "RD-018", "group": _ROADS, "name": "mc", "unit": "م²", "price": 0, "auto": "mc"},
    {"code": "RD-019", "group": _ROADS, "name": "مدة خرسانية", "unit": "م²", "price": 0},
    {"code": "RD-020", "group": _ROADS, "name": "مدة خرسانية مسلحة", "unit": "م²", "price": 0},
    {"code": "DRN-001", "group": _DRAIN, "name": "أنبوب Ø400", "unit": "م.ط", "price": 0},
    {"code": "DRN-002", "group": _DRAIN, "name": "أنبوب Ø600", "unit": "م.ط", "price": 0},
    {"code": "DRN-003", "group": _DRAIN, "name": "أنبوب Ø1000", "unit": "م.ط", "price": 0},
    {"code": "DRN-004", "group": _DRAIN, "name": "أنبوب Ø1200", "unit": "م.ط", "price": 0},
    {"code": "DRN-005", "group": _DRAIN, "name": "منهل تصريف", "unit": "عدد", "price": 0},
    {"code": "DRN-006", "group": _DRAIN, "name": "جرلات", "unit": "م.ط", "price": 0},
]

UNITS = ["م.ط", "عدد", "م²", "م³"]
# نوع الرسم على المخطط حسب وحدة البند
DRAW_FOR_UNIT = {"م.ط": "line", "عدد": "point", "م²": "area", "م³": "volume"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
CAD_EXTS = {".dxf", ".dwg"}


# ========== المسارات ==========
def resource_path(*parts):
    """مسار ملف ضمن مجلد assets، يعمل من المصدر ومن ملف exe المبني بـ PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    if hasattr(sys, "_MEIPASS"):
        base = os.path.join(base, "street_studies")
    return os.path.join(base, "assets", *parts)


def data_dir():
    override = os.environ.get("STREET_STUDIES_DATA")
    if override:
        root = override
    elif sys.platform == "win32":
        root = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
    else:
        root = os.path.join(os.path.expanduser("~"), ".local", "share", APP_NAME)
    os.makedirs(os.path.join(root, "attachments"), exist_ok=True)
    return root


# ========== الحسابات ==========
def reinforced_row(h_cm):
    for row in REINFORCED_TABLE:
        if row["H"] == h_cm:
            return row
    return None


def calc_reinforced(h_cm, length_m):
    row = reinforced_row(h_cm)
    if not row or not length_m or length_m <= 0:
        return None
    return {
        "conc_per_m": row["conc"],
        "steel_per_m": row["steel"],
        "total_conc": row["conc"] * length_m,
        "total_steel": row["steel"] * length_m,
        "dims": row,
    }


def calc_rubble(L, H, hb):
    if not L or not H or not hb or L <= 0 or H <= 0 or hb <= 0:
        return None
    B = H / 3
    W = B + 0.40
    v_wall = L * H * (0.25 + B) / 2
    v_base = L * W * hb
    return {"B": B, "W": W, "v_wall": v_wall, "v_base": v_base, "v_total": v_wall + v_base}


def wall_totals(walls):
    """يرجع (دبش، مسلح) بالمتر المكعب."""
    rubble = reinforced = 0.0
    for w in walls:
        if w.get("type") == "reinforced":
            r = calc_reinforced(w.get("h") or 150, w.get("length") or 0)
            if r:
                reinforced += r["total_conc"]
        else:
            r = calc_rubble(w.get("L") or 0, w.get("H") or 0, w.get("hb") or 0)
            if r:
                rubble += r["v_total"]
    return rubble, reinforced


def auto_quantities(length, width, mix_type):
    """الكميات التلقائية: التسوية = (عرض+2)×طول، البيس كورس = (عرض+1)×طول، mc = كمية البيس، الخلطة = عرض×طول."""
    if not (length and width):
        return {"RD-001": None, "RD-004": None, "RD-018": None, "ASP-002": None}
    on_mix = mix_type == MIX_ON_MIX
    base = 0.0 if on_mix else round((width + 1) * length, 2)
    return {
        "RD-001": 0.0 if on_mix else round((width + 2) * length, 2),
        "RD-004": base,
        "RD-018": base,
        "ASP-002": round(width * length, 2),
    }


def format_num(n):
    return f"{float(n or 0):,.2f}"


def safe_filename(name, fallback="بدون اسم"):
    """اسم صالح لملفات ويندوز (يحذف الرموز الممنوعة)."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(name or "")).strip().rstrip(". ")
    name = re.sub(r"\s+", " ", name)
    return name[:120] or fallback


def format_file_size(size):
    if size is None:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


# ========== المخزن ==========
class Store:
    def __init__(self, root=None):
        self.root = root or data_dir()
        self.path = os.path.join(self.root, "data.json")
        self.attach_dir = os.path.join(self.root, "attachments")
        os.makedirs(self.attach_dir, exist_ok=True)
        self.items = copy.deepcopy(DEFAULT_ITEMS)
        self.streets = []
        self.regions = list(DEFAULT_REGIONS)
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        streets = raw.get("streets")
        self.streets = streets if isinstance(streets, list) else []
        regions = raw.get("regions")
        self.regions = regions if isinstance(regions, list) and regions else list(DEFAULT_REGIONS)
        # نبدأ دائماً من البنود الافتراضية ونمرّر الأسعار المحفوظة
        prices, depths = {}, {}
        current = {it["code"]: it["name"] for it in DEFAULT_ITEMS}
        for it in raw.get("items") or []:
            # بند أُعيد استخدام كوده لشيء مختلف (مثل DRN-006 «مصيدة مياه» ← «جرلات») لا يرث السعر القديم
            if isinstance(it, dict) and it.get("name") and current.get(it.get("code")) not in (None, it["name"]):
                continue
            if isinstance(it, dict) and it.get("code"):
                try:
                    prices[it["code"]] = float(it.get("price") or 0)
                    if it.get("depth"):
                        depths[it["code"]] = float(it["depth"])
                except (TypeError, ValueError):
                    pass
        self.items = copy.deepcopy(DEFAULT_ITEMS)
        # البنود التي أضافها المستخدم
        for it in raw.get("customItems") or []:
            if isinstance(it, dict) and it.get("code") and it.get("name") and it.get("unit") in UNITS:
                self.items.append({"code": it["code"], "group": it.get("group") or "بنود إضافية",
                                   "name": it["name"], "unit": it["unit"], "price": 0, "custom": True})
        for it in self.items:
            if it["code"] in prices:
                it["price"] = prices[it["code"]]
            if it["code"] in depths:
                it["depth"] = depths[it["code"]]

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "items": self.items, "streets": self.streets, "regions": self.regions,
                       "customItems": [it for it in self.items if it.get("custom")]},
                      f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # ---- البنود
    def add_item(self, name, unit, group, price=0.0, depth=None):
        """بند جديد يضيفه المستخدم؛ كوده USR-001 وما بعده."""
        n = 1 + max([int(it["code"][4:]) for it in self.items
                     if it["code"].startswith("USR-") and it["code"][4:].isdigit()] + [0])
        it = {"code": f"USR-{n:03d}", "group": group or "بنود إضافية", "name": name.strip(), "unit": unit,
              "price": float(price or 0), "custom": True}
        if depth:
            it["depth"] = float(depth)
        self.items.append(it)
        self.save()
        return it

    def remove_item(self, code):
        """حذف بند مضاف (البنود الأساسية لا تُحذف). يرجع عدد السجلات التي كانت تستخدمه."""
        used = sum(1 for s in self.streets if (s.get("quantities") or {}).get(code))
        self.items = [it for it in self.items if not (it["code"] == code and it.get("custom"))]
        self.save()
        return used

    def item(self, code):
        for it in self.items:
            if it["code"] == code:
                return it
        return None

    def price(self, code):
        it = self.item(code)
        return float(it.get("price") or 0) if it else 0.0

    def street_cost(self, street):
        return sum(float(q or 0) * self.price(code) for code, q in (street.get("quantities") or {}).items())

    def filtered(self, region="", tender=""):
        return [s for s in self.streets
                if (not region or s.get("region") == region) and (not tender or s.get("tenderType") == tender)]

    # ---- المرفقات (تُنسخ إلى مجلد البيانات بدل تخزينها داخل JSON، بدون حد للحجم)
    def add_attachment(self, src_path):
        size = os.path.getsize(src_path)
        name = os.path.basename(src_path)
        stored = f"{uuid.uuid4().hex[:12]}_{name}"
        shutil.copy2(src_path, os.path.join(self.attach_dir, stored))
        ext = os.path.splitext(name)[1].lower()
        return {"name": name, "file": stored, "size": size, "isImage": ext in IMAGE_EXTS}

    def attachment_path(self, att):
        return os.path.join(self.attach_dir, att["file"])

    def purge_orphan_attachments(self):
        used = {a.get("file") for s in self.streets for a in s.get("attachments") or []}
        used |= {s["parcel"].get("file") for s in self.streets if s.get("parcel")}
        used |= {s["sitePlan"].get("file") for s in self.streets if s.get("sitePlan")}
        for fn in os.listdir(self.attach_dir):
            if fn not in used:
                try:
                    os.remove(os.path.join(self.attach_dir, fn))
                except OSError:
                    pass


# ========== اكتشاف التكرار والدمج ==========
def normalize_name(s):
    s = re.sub(r"[ً-ْـ]", "", str(s or ""))  # تشكيل وتطويل
    s = s.translate(str.maketrans("أإآىة", "ااايه"))
    return re.sub(r"\s+", " ", s).strip()


def normalize_piece(s):
    s = str(s or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    s = re.sub(r"\D", "", s)
    return s.lstrip("0") or ("0" if s else "")


def find_duplicates(streets, name="", piece="", basin_no="", exclude=-1):
    """سجلات محفوظة لنفس القطعة (ونفس الحوض إن عُرف) أو لنفس المالك. يرجع [(الفهرس، السبب)]."""
    out = []
    n, p, b = normalize_name(name), normalize_piece(piece), normalize_piece(basin_no)
    for i, s in enumerate(streets):
        if i == exclude:
            continue
        sp = normalize_piece(s.get("pieceNo"))
        sb = normalize_piece((s.get("plan") or {}).get("basinNo"))
        same_piece = bool(p) and sp == p and (not b or not sb or sb == b)
        same_owner = bool(n) and len(n.split()) >= 2 and normalize_name(s.get("name")) == n
        if same_piece or same_owner:
            out.append((i, "نفس القطعة" if same_piece and not same_owner else
                        "نفس المالك" if same_owner and not same_piece else "نفس القطعة والمالك"))
    return out


def merge_street(old, new):
    """دمج سجل جديد مع سجل محفوظ: القيم الجديدة تغلب، وما لم يُدخل في الجديد يبقى من القديم."""
    out = copy.deepcopy(old)
    for k, v in new.items():
        if k in ("quantities", "plan"):
            merged = dict(old.get(k) or {})
            merged.update({kk: vv for kk, vv in (v or {}).items() if vv not in (None, "", 0)})
            out[k] = merged
        elif k == "attachments":
            files = {a.get("file") for a in old.get(k) or []}
            out[k] = list(old.get(k) or []) + [a for a in v or [] if a.get("file") not in files]
        elif v not in (None, "", [], {}, 0, 0.0):
            out[k] = copy.deepcopy(v)
    return out
