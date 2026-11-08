"""نموذج سطح الأرض من خطوط الكنتور (DXF) — أي فاصل كنتور.

المنسوب عند أي نقطة: نطلق أشعة في عدة اتجاهات، ونأخذ أقرب خطي كنتور متقابلين بمنسوبين مختلفين
ونستوفي خطياً بينهما حسب المسافة. هذه طريقة الاستيفاء المعتادة بين خطوط الكنتور، ولا تحتاج مكتبات إضافية.
"""
import math
from collections import Counter

CELL = 20.0          # خلية الفهرس المكاني (م)
RAY_DIRS = 8         # أزواج الاتجاهات المتقابلة (كل 22.5°)


class Terrain:
    def __init__(self, contours, interval=None):
        """contours: [(z, [(x, y), ...])] بإحداثيات مطلقة (JTM)."""
        self.contours = [(z, P) for z, P in contours if len(P) >= 2]
        if not self.contours:
            raise ValueError("لا توجد خطوط كنتور بمناسيب في الملف")
        zs = sorted({round(z, 3) for z, _ in self.contours})
        self.zmin, self.zmax = zs[0], zs[-1]
        self.detected_interval = detect_interval(zs)
        self.interval = interval or self.detected_interval
        self.segments = []   # (x1, y1, x2, y2, z)
        self.grid = {}
        xs, ys = [], []
        for z, P in self.contours:
            for i in range(1, len(P)):
                (x1, y1), (x2, y2) = P[i - 1], P[i]
                k = len(self.segments)
                self.segments.append((x1, y1, x2, y2, z))
                for gx in range(int(min(x1, x2) // CELL), int(max(x1, x2) // CELL) + 1):
                    for gy in range(int(min(y1, y2) // CELL), int(max(y1, y2) // CELL) + 1):
                        self.grid.setdefault((gx, gy), []).append(k)
            xs += [p[0] for p in P]
            ys += [p[1] for p in P]
        self.bounds = (min(xs), min(ys), max(xs), max(ys))

    def covers(self, x, y, pad=0.0):
        x0, y0, x1, y1 = self.bounds
        return x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad

    def _ray(self, x, y, dx, dy, max_d):
        """أول تقاطع للشعاع مع خط كنتور: (المسافة، المنسوب) أو None."""
        best = None
        step = CELL
        d = 0.0
        seen = set()
        while d <= max_d:
            px, py = x + dx * d, y + dy * d
            gx, gy = int(px // CELL), int(py // CELL)
            for cx in (gx - 1, gx, gx + 1):
                for cy in (gy - 1, gy, gy + 1):
                    for k in self.grid.get((cx, cy), ()):
                        if k in seen:
                            continue
                        seen.add(k)
                        x1, y1, x2, y2, z = self.segments[k]
                        t = _ray_seg(x, y, dx, dy, x1, y1, x2, y2)
                        if t is not None and t <= max_d and (best is None or t < best[0]):
                            best = (t, z)
            if best is not None and best[0] < d - CELL:
                break
            d += step
        return best

    def elevation(self, x, y, max_d=None):
        """منسوب الأرض عند (x, y) أو None إن كانت النقطة خارج تغطية الكنتور."""
        max_d = max_d or max(4 * (self.interval or 10) * 10, 250.0)
        best = None
        nearest = None
        for k in range(RAY_DIRS):
            a = math.pi * k / RAY_DIRS
            dx, dy = math.cos(a), math.sin(a)
            r1 = self._ray(x, y, dx, dy, max_d)
            r2 = self._ray(x, y, -dx, -dy, max_d)
            for r in (r1, r2):
                if r and (nearest is None or r[0] < nearest[0]):
                    nearest = r
            if r1 and r2 and abs(r1[1] - r2[1]) > 1e-6:
                span = r1[0] + r2[0]
                if best is None or span < best[0]:
                    z = r1[1] + (r2[1] - r1[1]) * r1[0] / span if span > 0 else r1[1]
                    best = (span, z)
        if best is not None:
            return best[1]
        if nearest is not None and nearest[0] < (self.interval or 10) * 3:
            return nearest[1]   # قمة أو قاع بين خطين بنفس المنسوب
        return None


def _ray_seg(ox, oy, dx, dy, x1, y1, x2, y2):
    """مسافة تقاطع الشعاع مع القطعة المستقيمة، أو None."""
    ex, ey = x2 - x1, y2 - y1
    den = dx * ey - dy * ex
    if abs(den) < 1e-12:
        return None
    wx, wy = x1 - ox, y1 - oy
    t = (wx * ey - wy * ex) / den
    u = (wx * dy - wy * dx) / den
    if t >= 0 and -1e-9 <= u <= 1 + 1e-9:
        return t
    return None


def detect_interval(zs):
    """الفاصل الأكثر تكراراً بين المناسيب المتتالية (مقرّب لأقرب 0.1 م)."""
    diffs = [round(b - a, 1) for a, b in zip(zs, zs[1:]) if b - a > 0.05]
    if not diffs:
        return None
    return Counter(diffs).most_common(1)[0][0]


def load_dxf(path, interval=None):
    """يقرأ خطوط الكنتور من DXF: POLYLINE ثلاثية الأبعاد، LWPOLYLINE بمنسوب، LINE، SPLINE.
    العناصر ذات المنسوب صفر (حدود القطع وغيرها) تُتجاهل."""
    from ezdxf import disassemble, recover
    from ezdxf import path as dxf_path

    doc, _ = recover.readfile(path)
    contours = []
    for e in disassemble.recursive_decompose(doc.modelspace()):
        kind = e.dxftype()
        try:
            if kind == "LWPOLYLINE":
                z = float(e.dxf.elevation or 0)
                P = [(p[0], p[1]) for p in e.get_points("xy")]
                if e.closed and P:
                    P.append(P[0])
            elif kind == "POLYLINE":
                V = list(e.points())
                if not V:
                    continue
                z = float(V[0].z)
                P = [(v.x, v.y) for v in V]
                if e.is_closed:
                    P.append(P[0])
            elif kind == "LINE":
                z = float(e.dxf.start.z)
                P = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
            elif kind in ("SPLINE", "ARC"):
                pp = dxf_path.make_path(e)
                V = list(pp.flattening(0.5))
                z = float(V[0].z) if V else 0
                P = [(v.x, v.y) for v in V]
            else:
                continue
        except Exception:  # noqa: BLE001
            continue
        if abs(z) > 1e-6 and len(P) >= 2:
            contours.append((z, P))
    if not contours:
        raise ValueError("لم أجد خطوط كنتور لها مناسيب (Z) في الملف — تأكد أن الخطوط ثلاثية الأبعاد")
    return Terrain(contours, interval)
