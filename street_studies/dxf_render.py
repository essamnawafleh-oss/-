"""قراءة ملف DXF (أوتوكاد) ورسمه كصورة لمعاينة قطعة الأرض وللتقرير."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QTransform

try:
    import ezdxf
    from ezdxf import colors as dxf_colors
    from ezdxf import disassemble, recover
    from ezdxf import path as dxf_path
except ImportError:  # pragma: no cover
    ezdxf = None

_cache = {}


class CadDrawing:
    def __init__(self):
        self.paths = []     # [(color, [(x, y), ...])]
        self.texts = []     # [(color, x, y, height, rotation, text)]
        self.bounds = None  # (minx, miny, maxx, maxy)
        self.layers = 0
        self.entities = 0

    def _extend(self, pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        b = (min(xs), min(ys), max(xs), max(ys))
        self.bounds = b if self.bounds is None else (min(self.bounds[0], b[0]), min(self.bounds[1], b[1]),
                                                      max(self.bounds[2], b[2]), max(self.bounds[3], b[3]))

    @property
    def empty(self):
        return self.bounds is None


def _color(entity, doc, ink):
    try:
        aci = entity.dxf.color
        if aci == 256:  # BYLAYER
            layer = doc.layers.get(entity.dxf.layer)
            aci = abs(layer.color) if layer else 7
        if entity.dxf.hasattr("true_color"):
            r, g, b = dxf_colors.int2rgb(entity.dxf.true_color)
            return QColor(r, g, b)
        if aci in (0, 7, 255, 256) or aci > 255:
            return QColor(ink)
        r, g, b = dxf_colors.aci2rgb(aci)
        c = QColor(r, g, b)
        # الألوان الفاتحة جداً لا تظهر على خلفية بيضاء
        if c.lightness() > 200:
            c = c.darker(160)
        return c
    except Exception:  # noqa: BLE001
        return QColor(ink)


def load(path, ink="#1B2428"):
    """يرجع CadDrawing أو يرفع ValueError برسالة عربية."""
    if ezdxf is None:
        raise ValueError("مكتبة قراءة DXF غير متوفرة")
    key = (path, ink)
    if key in _cache:
        return _cache[key]
    try:
        doc, _auditor = recover.readfile(path)
    except Exception as e:  # noqa: BLE001
        raise ValueError("تعذّر قراءة ملف DXF — تأكد أنه ملف DXF صالح (DWG لا يمكن معاينته)") from e

    msp = doc.modelspace()
    off_layers = {ly.dxf.name for ly in doc.layers if not ly.is_on() or ly.is_frozen()}
    d = CadDrawing()
    d.layers = len(doc.layers)
    for e in disassemble.recursive_decompose(msp):
        try:
            if e.dxf.layer in off_layers:
                continue
        except Exception:  # noqa: BLE001
            pass
        kind = e.dxftype()
        d.entities += 1
        color = _color(e, doc, ink)
        if kind in ("TEXT", "ATTRIB", "MTEXT"):
            try:
                text = e.plain_text() if kind == "MTEXT" else e.dxf.text
                ins = e.dxf.insert
                h = e.dxf.char_height if kind == "MTEXT" else e.dxf.height
                rot = e.dxf.get("rotation", 0) or 0
                if text and text.strip():
                    d.texts.append((color, ins.x, ins.y, h or 1.0, rot, text.strip()))
                    d._extend([(ins.x, ins.y)])
            except Exception:  # noqa: BLE001
                pass
            continue
        if kind == "POINT":
            continue
        try:
            p = dxf_path.make_path(e)
        except Exception:  # noqa: BLE001
            continue
        if not p or len(p) == 0:
            continue
        verts = [(v.x, v.y) for v in p.control_vertices()]
        if verts:
            d._extend(verts)
        d.paths.append((color, p))
    if d.empty:
        raise ValueError("ملف DXF لا يحتوي على رسومات قابلة للعرض")

    # تقريب المنحنيات بدقة مناسبة لحجم الرسم
    minx, miny, maxx, maxy = d.bounds
    tol = max(maxx - minx, maxy - miny, 1e-9) / 3000
    flat = []
    for color, p in d.paths:
        try:
            pts = [(v.x, v.y) for v in p.flattening(tol)]
        except Exception:  # noqa: BLE001
            continue
        if len(pts) >= 2:
            flat.append((color, pts))
    d.paths = flat
    _cache[key] = d
    return d


def render(drawing, width, height, background="#FFFFFF", margin=0.04, line_width=1.2):
    """يرسم المخطط في صورة بالحجم المطلوب مع الحفاظ على النسبة."""
    img = QImage(int(width), int(height), QImage.Format.Format_ARGB32)
    img.fill(QColor(background))
    minx, miny, maxx, maxy = drawing.bounds
    w, h = max(maxx - minx, 1e-9), max(maxy - miny, 1e-9)
    m = min(width, height) * margin
    scale = min((width - 2 * m) / w, (height - 2 * m) / h)
    ox = (width - w * scale) / 2
    oy = (height - h * scale) / 2

    def tx(x, y):  # محور Y في أوتوكاد للأعلى
        return QPointF(ox + (x - minx) * scale, height - (oy + (y - miny) * scale))

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for color, pts in drawing.paths:
        pen = QPen(color, line_width)
        pen.setCosmetic(True)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        path = QPainterPath(tx(*pts[0]))
        for x, y in pts[1:]:
            path.lineTo(tx(x, y))
        p.drawPath(path)
    for color, x, y, th, rot, text in drawing.texts:
        px = th * scale
        if px < 4:
            continue
        f = QFont()
        f.setPixelSize(max(4, int(px)))
        p.save()
        pt = tx(x, y)
        p.setTransform(QTransform().translate(pt.x(), pt.y()).rotate(-rot))
        p.setPen(color)
        p.setFont(f)
        p.drawText(QRectF(0, -px * 1.3, px * len(text) * 0.8 + 10, px * 1.6),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, text)
        p.restore()
    p.end()
    return img


def render_file(path, width, height, **kw):
    """يرسم الملف مباشرة؛ يرجع (QImage أو None، رسالة خطأ أو None)."""
    try:
        return render(load(path), width, height, **kw), None
    except ValueError as e:
        return None, str(e)


def size_text(drawing):
    minx, miny, maxx, maxy = drawing.bounds
    return f"{maxx - minx:,.2f} × {maxy - miny:,.2f}"


def area_of_largest_closed(drawing):
    """مساحة أكبر شكل مغلق (تقديرية) — تفيد كمرجع لمساحة القطعة."""
    best = 0.0
    for _, pts in drawing.paths:
        if len(pts) < 4 or math.dist(pts[0], pts[-1]) > 1e-6 * max(1.0, abs(pts[0][0]) + abs(pts[0][1])):
            continue
        a = 0.5 * abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])))
        best = max(best, a)
    return best
