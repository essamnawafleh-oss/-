"""بيانات المخطط التنظيمي (قطع، شوارع تنظيمية، أودية) بنظام JTM، والتحويل إلى WGS84 للصورة الجوية.

الإحداثيات المحفوظة في السجلات (مسارات الرسم) مطلقة بنظام JTM بالمتر، مثل النسخة الأصلية.
داخل هذه الوحدة نعمل بإحداثيات نسبية (x - ox, y - oy) لدقة أعلى في الرسم.
"""
import array
import itertools
import threading
import json
import math
import os
import zlib

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPolygonF

from .data import data_dir, normalize_piece, resource_path

LAYER_PARCEL, LAYER_ROAD, LAYER_WADI, LAYER_EXTRA = "0", "1", "2", "3"
CELL = 400.0  # حجم خلية الفهرس المكاني بالمتر

# ---------------------------------------------------------------- JTM (Jordan Transverse Mercator)
_A, _F = 6378137.0, 1 / 298.257223563
_N = _F / (2 - _F)
_K, _E0, _N0, _L0 = 0.9998, 500000.0, -3000000.0, math.radians(37)
_AA = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_AL = [_N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16 + 41 * _N ** 4 / 180,
       13 * _N ** 2 / 48 - 3 * _N ** 3 / 5 + 557 * _N ** 4 / 1440,
       61 * _N ** 3 / 240 - 103 * _N ** 4 / 140, 49561 * _N ** 4 / 161280]
_BE = [_N / 2 - 2 * _N ** 2 / 3 + 37 * _N ** 3 / 96 - _N ** 4 / 360,
       _N ** 2 / 48 + _N ** 3 / 15 - 437 * _N ** 4 / 1440,
       17 * _N ** 3 / 480 - 37 * _N ** 4 / 840, 4397 * _N ** 4 / 161280]
_DE = [2 * _N - 2 * _N ** 2 / 3 - 2 * _N ** 3 + 116 * _N ** 4 / 45,
       7 * _N ** 2 / 3 - 8 * _N ** 3 / 5 - 227 * _N ** 4 / 45,
       56 * _N ** 3 / 15 - 136 * _N ** 4 / 35, 4279 * _N ** 4 / 630]


def ll2j(lat, lon):
    p, lam = math.radians(lat), math.radians(lon) - _L0
    s = math.sin(p)
    q = 2 * math.sqrt(_N) / (1 + _N)
    t = math.sinh(math.atanh(s) - q * math.atanh(q * s))
    xi = math.atan2(t, math.cos(lam))
    eta = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    a, b = xi, eta
    for j in range(1, 5):
        a += _AL[j - 1] * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        b += _AL[j - 1] * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
    return _E0 + _K * _AA * b, _N0 + _K * _AA * a


def j2ll(e, n):
    xi, eta = (n - _N0) / (_K * _AA), (e - _E0) / (_K * _AA)
    a, b = xi, eta
    for j in range(1, 5):
        a -= _BE[j - 1] * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        b -= _BE[j - 1] * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
    chi = math.asin(math.sin(a) / math.cosh(b))
    phi = chi + sum(_DE[k - 1] * math.sin(2 * k * chi) for k in range(1, 5))
    return math.degrees(phi), math.degrees(_L0 + math.atan2(math.sinh(b), math.cos(a)))


# ---------------------------------------------------------------- أدوات هندسية
def length(P):
    return sum(math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]) for i in range(1, len(P)))


def poly_area(P):
    if len(P) < 3:
        return 0.0
    return abs(sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))) / 2


def dist_seg(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if not L2 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
    return math.hypot(px - a[0] - t * dx, py - a[1] - t * dy)


def nearest_on_seg(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if not L2 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
    return a[0] + t * dx, a[1] + t * dy, t


# ---------------------------------------------------------------- مجموعة بيانات
class Dataset:
    """طبقة واحدة من المخطط: مضلعات/خطوط مع أرقام القطع وفهرس مكاني."""

    def __init__(self, name, ox, oy, polys, layers, nums, builtin=False):
        self.name, self.ox, self.oy, self.builtin = name, ox, oy, builtin
        self.polys = polys          # [QPolygonF] بإحداثيات نسبية
        self.layers = layers        # str: طبقة كل عنصر
        self.nums = nums            # [str] رقم القطعة
        self.bbox = [p.boundingRect() for p in polys]
        self.cells = {}             # (layer, cx, cy) -> QPainterPath
        self.grid = {}              # (cx, cy) -> [indices] للالتقاط والتحديد
        self.by_num = {}
        for i, p in enumerate(polys):
            r = self.bbox[i]
            c = r.center()
            key = (layers[i], int(c.x() // CELL), int(c.y() // CELL))
            path = self.cells.get(key)
            if path is None:
                path = self.cells[key] = QPainterPath()
            if layers[i] == LAYER_PARCEL or self._closed(p):
                path.addPolygon(p)
                path.closeSubpath()
            else:
                path.addPolygon(p)
            for gx in range(int(r.left() // CELL), int(r.right() // CELL) + 1):
                for gy in range(int(r.top() // CELL), int(r.bottom() // CELL) + 1):
                    self.grid.setdefault((gx, gy), []).append(i)
            if layers[i] == LAYER_PARCEL and nums[i]:
                self.by_num.setdefault(normalize_piece(nums[i]), []).append(i)
        self.cell_bounds = {k: v.boundingRect() for k, v in self.cells.items()}
        self.extent = QRectF()
        for i, r in enumerate(self.bbox):
            if layers[i] == LAYER_PARCEL:
                self.extent = self.extent.united(r)
        if self.extent.isNull() and self.bbox:
            for r in self.bbox:
                self.extent = self.extent.united(r)
        self._areas = {}

    @staticmethod
    def _closed(p):
        return p.size() > 2 and (p.first() - p.last()).manhattanLength() < 1.5

    def area(self, i):
        if i not in self._areas:
            p = self.polys[i]
            self._areas[i] = poly_area([(p.at(k).x(), p.at(k).y()) for k in range(p.size())])
        return self._areas[i]

    def candidates(self, x, y, pad=0.0):
        out = set()
        for gx in range(int((x - pad) // CELL), int((x + pad) // CELL) + 1):
            for gy in range(int((y - pad) // CELL), int((y + pad) // CELL) + 1):
                out.update(self.grid.get((gx, gy), ()))
        return out

    def pick(self, x, y):
        """القطعة تحت النقطة (إحداثيات نسبية)."""
        pt = QPointF(x, y)
        best = None
        for i in self.candidates(x, y):
            if self.layers[i] == LAYER_PARCEL and self.bbox[i].contains(pt) and \
                    self.polys[i].containsPoint(pt, Qt.FillRule.OddEvenFill):
                if best is None or self.area(i) < self.area(best):
                    best = i
        return best

    def abs_points(self, i):
        p = self.polys[i]
        return [(p.at(k).x() + self.ox, p.at(k).y() + self.oy) for k in range(p.size())]

    def find(self, query, target_area=None):
        """بحث برقم القطعة مع ترتيب حسب قرب المساحة من مساحة مخطط الموقع (الأرقام تتكرر بين الأحواض)."""
        q = normalize_piece(query)
        hits = list(self.by_num.get(q, [])) if q else []
        if q and not hits and len(q) >= 2:
            for k, v in self.by_num.items():
                if q in k:
                    hits.extend(v)
        if not hits and target_area:
            hits = [i for i, L in enumerate(self.layers) if L == LAYER_PARCEL
                    and abs(self.area(i) - target_area) / target_area <= 0.03]
        ranked = []
        for i in set(hits):
            a = self.area(i)
            score = 100 if normalize_piece(self.nums[i]) == q else 55
            rel = abs(a - target_area) / target_area if target_area and a else None
            if rel is not None:
                score += max(-70, 80 - rel * 400)
            ranked.append({"i": i, "score": score, "area": a, "rel": rel})
        ranked.sort(key=lambda r: (-r["score"], r["i"]))
        return ranked


def _load_builtin():
    meta = json.load(open(resource_path("parcels.json"), encoding="utf-8"))
    buf = zlib.decompress(open(resource_path("parcels.bin"), "rb").read())
    nv, n = meta["nv"], meta["n"]
    d = array.array("i")
    d.frombytes(buf[:nv * 8])
    off = array.array("I")
    off.frombytes(buf[nv * 8:nv * 8 + (n + 1) * 4])
    xs = itertools.accumulate(d[0::2])
    ys = itertools.accumulate(d[1::2])
    pts = [QPointF(x / 100, y / 100) for x, y in zip(xs, ys)]
    polys = [QPolygonF(pts[off[i]:off[i + 1]]) for i in range(n)]
    return Dataset("المخطط التنظيمي — وادي موسى", meta["ox"], meta["oy"], polys, meta["lay"], meta["num"], True)


# ---------------------------------------------------------------- طبقات مستوردة من DXF
def imported_dir():
    p = os.path.join(data_dir(), "maps")
    os.makedirs(p, exist_ok=True)
    return p


def import_dxf(path, name, ox, oy):
    """يقرأ ملف DXF (إحداثيات JTM): المضلعات المغلقة قطع، والخطوط المفتوحة طبقة إضافية،
    والنصوص داخل القطع تصبح أرقامها. يحفظ الطبقة في مجلد البيانات ويرجع عدد القطع."""
    from ezdxf import disassemble, recover
    from ezdxf import path as dxf_path

    doc, _ = recover.readfile(path)
    shapes, texts = [], []
    for e in disassemble.recursive_decompose(doc.modelspace()):
        kind = e.dxftype()
        if kind in ("TEXT", "MTEXT"):
            try:
                t = e.plain_text() if kind == "MTEXT" else e.dxf.text
                ins = e.dxf.insert
                if t and normalize_piece(t):
                    texts.append((ins.x, ins.y, t.strip()))
            except Exception:  # noqa: BLE001
                pass
            continue
        try:
            pp = dxf_path.make_path(e)
            pts = [(v.x, v.y) for v in pp.flattening(0.2)]
        except Exception:  # noqa: BLE001
            continue
        if len(pts) >= 2:
            closed = len(pts) > 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 0.05
            shapes.append({"pts": [[round(x, 3), round(y, 3)] for x, y in pts], "closed": closed})
    if not shapes:
        raise ValueError("الملف لا يحتوي على خطوط أو مضلعات")
    xs = [p[0] for s in shapes for p in s["pts"]]
    if not (100000 < sum(xs) / len(xs) < 600000):
        raise ValueError("إحداثيات الملف ليست بنظام JTM (المتر) — لا يمكن مطابقتها مع المخطط")
    polys = [QPolygonF([QPointF(x, y) for x, y in s["pts"]]) for s in shapes]
    nums = [""] * len(shapes)
    for tx, ty, t in texts:
        pt = QPointF(tx, ty)
        for i, s in enumerate(shapes):
            if s["closed"] and not nums[i] and polys[i].boundingRect().contains(pt) and \
                    polys[i].containsPoint(pt, Qt.FillRule.OddEvenFill):
                nums[i] = t
                break
    data = {"name": name, "shapes": [{"pts": s["pts"], "closed": s["closed"], "num": nums[i]}
                                     for i, s in enumerate(shapes)]}
    fn = os.path.join(imported_dir(), f"{abs(hash((name, len(shapes)))) % 10 ** 8}.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return sum(1 for s in shapes if s["closed"]), fn


def _load_imported(fn, ox, oy):
    with open(fn, encoding="utf-8") as f:
        data = json.load(f)
    shapes = data["shapes"]
    polys = [QPolygonF([QPointF(x - ox, y - oy) for x, y in s["pts"]]) for s in shapes]
    layers = "".join(LAYER_PARCEL if s["closed"] else LAYER_EXTRA for s in shapes)
    ds = Dataset(data.get("name") or os.path.basename(fn), ox, oy, polys, layers,
                 [s.get("num") or "" for s in shapes])
    ds.file = fn
    return ds


class GeoStore:
    """كل طبقات المخطط (المضمّنة + المستوردة) بأصل إحداثيات واحد."""
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        base = _load_builtin()
        self.ox, self.oy = base.ox, base.oy
        self.datasets = [base]
        for fn in sorted(os.listdir(imported_dir())):
            if fn.endswith(".json"):
                try:
                    self.datasets.append(_load_imported(os.path.join(imported_dir(), fn), self.ox, self.oy))
                except Exception:  # noqa: BLE001
                    pass

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = GeoStore()
            return cls._instance

    @classmethod
    def preload(cls):
        """تحميل المخطط في الخلفية عند بدء التطبيق حتى تُفتح صفحة المخطط فوراً."""
        threading.Thread(target=lambda: cls.get(), daemon=True).start()

    def add_imported(self, fn):
        ds = _load_imported(fn, self.ox, self.oy)
        self.datasets.append(ds)
        return ds

    def remove_imported(self, ds):
        if ds.builtin:
            return
        self.datasets.remove(ds)
        try:
            os.remove(ds.file)
        except OSError:
            pass

    def extent(self):
        r = QRectF()
        for ds in self.datasets:
            r = r.united(ds.extent)
        return r

    def pick(self, x, y):
        for ds in reversed(self.datasets):
            i = ds.pick(x, y)
            if i is not None:
                return ds, i
        return None, None

    def find(self, query, target_area=None):
        out = []
        for ds in self.datasets:
            for r in ds.find(query, target_area):
                out.append(dict(r, ds=ds))
        out.sort(key=lambda r: -r["score"])
        return out
