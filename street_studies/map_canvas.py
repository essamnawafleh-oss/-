"""لوحة الخريطة: رسم المخطط التنظيمي والصورة الجوية، التكبير والتحريك، والتقاط النقاط (OSNAP)."""
import math
import os
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTransform,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import QWidget

from . import geo
from .data import data_dir

TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


class TileCache:
    """بلاطات الصورة الجوية: ذاكرة + قرص (تبقى متاحة بدون إنترنت بعد أول تحميل)."""

    def __init__(self, on_ready):
        self.on_ready = on_ready
        self.mem = {}
        self.pending = set()
        self.failed = {}   # key -> وقت الفشل (يُعاد المحاولة بعد 20 ثانية)
        self.net = QNetworkAccessManager()
        self.net.finished.connect(self._done)
        self.folder = os.path.join(data_dir(), "tiles")

    def _path(self, z, x, y):
        return os.path.join(self.folder, str(z), str(x), f"{y}.jpg")

    def peek(self, z, x, y):
        """البلاطة من الذاكرة أو القرص فقط (بدون طلب من الإنترنت)."""
        key = (z, x, y)
        img = self.mem.get(key)
        if img is not None:
            return img
        p = self._path(z, x, y)
        if os.path.exists(p):
            img = QImage(p)
            if not img.isNull():
                if len(self.mem) > 1500:
                    self.mem.clear()
                self.mem[key] = img
                return img
        return None

    def get(self, z, x, y):
        key = (z, x, y)
        img = self.peek(z, x, y)
        if img is not None:
            return img
        if key in self.failed and time.time() - self.failed[key] > 20:
            del self.failed[key]
        if key not in self.pending and key not in self.failed and len(self.pending) < 64:
            self.pending.add(key)
            req = QNetworkRequest(QUrl(TILE_URL.format(z=z, x=x, y=y)))
            req.setRawHeader(b"User-Agent", b"StreetStudies-Desktop")
            req.setAttribute(QNetworkRequest.Attribute.User, key)
            self.net.get(req)
        return None

    def _done(self, reply):
        key = reply.request().attribute(QNetworkRequest.Attribute.User)
        self.pending.discard(key)
        data = bytes(reply.readAll())
        img = QImage.fromData(data)
        if reply.error() == reply.NetworkError.NoError and not img.isNull():
            z, x, y = key
            p = self._path(z, x, y)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(data)
            self.mem[key] = img
            self.on_ready()
        else:
            self.failed[key] = time.time()
        reply.deleteLater()


class MapCanvas(QWidget):
    clicked = Signal(float, float, object)     # x, y (نسبي), الزر
    moved = Signal(float, float)
    finished = Signal()                         # زر أيمن / نقر مزدوج: إنهاء الخط الحالي
    cancelled = Signal()
    undo = Signal()

    STYLE = {
        geo.LAYER_PARCEL: (QColor("#E0B400"), QColor(255, 236, 150, 30)),
        geo.LAYER_ROAD: (QColor("#C62828"), None),
        geo.LAYER_WADI: (QColor("#01579B"), QColor(3, 169, 244, 45)),
        geo.LAYER_EXTRA: (QColor("#7B1FA2"), None),
    }

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.geo = store
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(400, 300)
        self.cx = self.cy = 0.0
        self.s = 0.05
        self.aerial = False
        self.opacity = 0.85
        self.offset = (20.0, 170.0)    # إزاحة الصورة الجوية بالمتر (X, Y)
        self.layers_on = {geo.LAYER_PARCEL: True, geo.LAYER_ROAD: True, geo.LAYER_WADI: True, geo.LAYER_EXTRA: True}
        self.selected = None           # (ds, i)
        self.candidates = []           # [(ds, i)]
        self.drawing = False
        self.osnap = True
        self.snap = None               # (x, y, kind)
        self.mouse = None              # (x, y) نسبي
        self.overlay = None            # دالة ترسم الطبقة العلوية: overlay(painter, canvas)
        self.extra_snap = None         # دالة ترجع خطوطاً إضافية للالتقاط [[(x,y)...]] نسبية
        self._drag = None
        self._cache = None             # (QPixmap, cx, cy, s)
        self._rerender = QTimer(self, singleShot=True, interval=120, timeout=self._invalidate)
        self.tiles = TileCache(self.update)
        self.fit(self.geo.extent())

    # ---------- التحويلات
    def to_screen(self, x, y):
        return QPointF((x - self.cx) * self.s + self.width() / 2, self.height() / 2 - (y - self.cy) * self.s)

    def to_world(self, px, py):
        return (px - self.width() / 2) / self.s + self.cx, self.cy - (py - self.height() / 2) / self.s

    def transform(self):
        return QTransform().translate(self.width() / 2, self.height() / 2).scale(self.s, -self.s) \
            .translate(-self.cx, -self.cy)

    def view_rect(self):
        x0, y1 = self.to_world(0, 0)
        x1, y0 = self.to_world(self.width(), self.height())
        return QRectF(x0, y0, x1 - x0, y1 - y0)

    def fit(self, r, k=0.9):
        if r.isNull() or r.width() <= 0:
            return
        self.cx, self.cy = r.center().x(), r.center().y()
        w, h = max(self.width(), 400), max(self.height(), 300)
        self.s = min(w / max(r.width(), 1), h / max(r.height(), 1)) * k
        self._invalidate()

    def fit_parcel(self, ds, i, pad=0.85):
        r = ds.bbox[i]
        m = max(r.width(), r.height(), 15) * pad
        self.fit(r.adjusted(-m, -m, m, m), 0.92)

    def _invalidate(self):
        self._cache = None
        self.update()

    def resizeEvent(self, e):
        self._invalidate()
        super().resizeEvent(e)

    # ---------- الرسم
    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#F4F1E8") if not self.aerial else QColor("#20262B"))
        if self.aerial:
            self._draw_aerial(p)
        self._draw_base(p)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # القطعة المحددة والمرشّحون
        tr = self.transform()
        if self.selected:
            ds, i = self.selected
            p.save()
            p.setTransform(tr)
            pen = QPen(QColor("#159895"), 2.6)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(QColor(21, 152, 149, 70))
            p.drawPolygon(ds.polys[i])
            p.restore()
        if len(self.candidates) > 1:
            p.setPen(QPen(QColor("#E8590C"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for ds, i in self.candidates:
                c = self.to_screen(ds.bbox[i].center().x(), ds.bbox[i].center().y())
                p.drawEllipse(c, 8, 8)
        self._draw_numbers(p)
        if self.overlay:
            self.overlay(p, self)
        self._draw_snap(p)
        if self.aerial:
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(QColor(255, 255, 255, 220))
            p.drawText(QRectF(8, self.height() - 20, 400, 16), Qt.AlignmentFlag.AlignLeft,
                       "Imagery: Esri, Maxar, Earthstar Geographics")
        p.end()

    def _draw_base(self, p):
        if self._drag is not None and self._cache is not None:
            pm, cx, cy, s = self._cache
            if abs(s - self.s) < 1e-12:
                p.drawPixmap(QPointF((cx - self.cx) * self.s, (self.cy - cy) * self.s), pm)
                return
        if self._cache is None or self._cache[1:] != (self.cx, self.cy, self.s):
            dpr = self.devicePixelRatioF()
            pm = QPixmap(QSize(int(self.width() * dpr), int(self.height() * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing, self.s > 0.08)
            q.setTransform(self.transform())
            view = self.view_rect()
            for ds in self.geo.datasets:
                for key, path in ds.cells.items():
                    layer = key[0]
                    if not self.layers_on.get(layer, True):
                        continue
                    if not ds.cell_bounds[key].intersects(view):
                        continue
                    line, fill = self.STYLE.get(layer, self.STYLE[geo.LAYER_EXTRA])
                    pen = QPen(line, 1.9 if layer == geo.LAYER_ROAD else (2.4 if layer == geo.LAYER_WADI else 1.1))
                    pen.setCosmetic(True)
                    if layer == geo.LAYER_WADI:
                        pen.setStyle(Qt.PenStyle.DashLine)
                    q.setPen(pen)
                    if layer == geo.LAYER_PARCEL:
                        q.setBrush(QColor(255, 230, 80, 18) if self.aerial else fill)
                    elif fill is not None and layer == geo.LAYER_WADI:
                        q.setBrush(fill)
                    else:
                        q.setBrush(Qt.BrushStyle.NoBrush)
                    q.drawPath(path)
            q.end()
            self._cache = (pm, self.cx, self.cy, self.s)
        p.drawPixmap(0, 0, self._cache[0])

    def _draw_numbers(self, p):
        if self.s < 0.9 or not self.layers_on.get(geo.LAYER_PARCEL, True):
            return
        view = self.view_rect()
        f = QFont()
        f.setPixelSize(11)
        p.setFont(f)
        count = 0
        for ds in self.geo.datasets:
            gx0, gx1 = int(view.left() // geo.CELL), int(view.right() // geo.CELL)
            gy0, gy1 = int(view.top() // geo.CELL), int(view.bottom() // geo.CELL)
            seen = set()
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    for i in ds.grid.get((gx, gy), ()):
                        if i in seen or ds.layers[i] != geo.LAYER_PARCEL or not ds.nums[i]:
                            continue
                        seen.add(i)
                        r = ds.bbox[i]
                        if not view.contains(r.center()) or max(r.width(), r.height()) * self.s < 28:
                            continue
                        c = self.to_screen(r.center().x(), r.center().y())
                        rect = QRectF(c.x() - 40, c.y() - 8, 80, 16)
                        if self.aerial:
                            p.setPen(QColor(0, 0, 0, 200))
                            p.drawText(rect.translated(1, 1), Qt.AlignmentFlag.AlignCenter, ds.nums[i])
                            p.setPen(QColor("#FFFFFF"))
                        else:
                            p.setPen(QColor("#5D4E00"))
                        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, ds.nums[i])
                        count += 1
                        if count > 700:
                            return

    def _draw_aerial(self, p):
        dx, dy = self.offset
        ox, oy = self.geo.ox, self.geo.oy
        w, h = self.width(), self.height()
        corners = [self.to_world(0, 0), self.to_world(w, 0), self.to_world(0, h), self.to_world(w, h)]
        lls = [geo.j2ll(x + ox - dx, y + oy - dy) for x, y in corners]
        la0, la1 = min(c[0] for c in lls), max(c[0] for c in lls)
        lo0, lo1 = min(c[1] for c in lls), max(c[1] for c in lls)
        # المستوى 18 أعلى دقة متوفرة لهذه المنطقة؛ عند التكبير أكثر نكبّر بلاطات المستوى 18 نفسها
        z = max(8, min(18, round(math.log2(156543.034 * math.cos(math.radians(la0)) * self.s))))

        def tiles_at(zz):
            ZZ = 2 ** zz

            def tyf(lat):
                return int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * ZZ)
            return int((lo0 + 180) / 360 * ZZ), int((lo1 + 180) / 360 * ZZ), tyf(la1), tyf(la0)
        tx0, tx1, ty0, ty1 = tiles_at(z)
        # عند التصغير الشديد نخفض المستوى بدل إخفاء الصورة
        while (tx1 - tx0 + 1) * (ty1 - ty0 + 1) > 140 and z > 8:
            z -= 1
            tx0, tx1, ty0, ty1 = tiles_at(z)
        Z = 2 ** z

        def tc(X, Y):
            lo = X / Z * 360 - 180
            la = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * Y / Z))))
            e, n = geo.ll2j(la, lo)
            return self.to_screen(e + dx - ox, n + dy - oy)

        p.save()
        p.setOpacity(self.opacity)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for X in range(tx0, tx1 + 1):
            for Y in range(ty0, ty1 + 1):
                img = self.tiles.get(z, X, Y)
                src = QRectF(0, 0, 256, 256)
                if img is None:
                    # إلى أن تصل البلاطة: نعرض جزءاً مكبّراً من بلاطة أقل دقة محفوظة
                    for d in range(1, 7):
                        anc = self.tiles.peek(z - d, X >> d, Y >> d)
                        if anc is not None:
                            size = 256 / (1 << d)
                            src = QRectF((X % (1 << d)) * size, (Y % (1 << d)) * size, size, size)
                            img = anc
                            break
                if img is None:
                    continue
                A, B, Cc = tc(X, Y), tc(X + 1, Y), tc(X, Y + 1)
                t = QTransform((B.x() - A.x()) / 256, (B.y() - A.y()) / 256, (Cc.x() - A.x()) / 256,
                               (Cc.y() - A.y()) / 256, A.x(), A.y())
                p.setTransform(t)
                p.drawImage(QRectF(0, 0, 256.6, 256.6), img, src)
        p.restore()

    def _draw_snap(self, p):
        if not (self.drawing and self.snap):
            return
        x, y, kind = self.snap
        c = self.to_screen(x, y)
        p.save()
        p.setPen(QPen(QColor("#00C853"), 2.4))
        p.setBrush(QColor(0, 255, 100, 50))
        p.drawEllipse(c, 13, 13)
        p.setPen(QPen(QColor("#FFFFFF"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if kind in ("vert", "end"):
            p.drawRect(QRectF(c.x() - 8, c.y() - 8, 16, 16))
        elif kind == "mid":
            p.drawPolygon(QPolygonF([QPointF(c.x(), c.y() - 9), QPointF(c.x() + 8, c.y() + 6),
                                     QPointF(c.x() - 8, c.y() + 6)]))
        else:
            p.drawLine(QPointF(c.x() - 9, c.y()), QPointF(c.x() + 9, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - 9), QPointF(c.x(), c.y() + 9))
        lab = {"vert": "نقطة رأس", "end": "طرف خط", "mid": "منتصف", "edge": "على الخط"}.get(kind, "")
        f = QFont()
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#003D1A"))
        p.drawText(QPointF(c.x() + 15, c.y() - 11), lab)
        p.restore()

    # ---------- الالتقاط
    def find_snap(self, x, y):
        if not self.osnap:
            return None
        tol = 26 / max(self.s, 1e-9)
        best = [None, tol]

        def consider(qx, qy, kind, t=tol):
            d = math.hypot(qx - x, qy - y)
            if d <= t and d < best[1]:
                best[0], best[1] = (qx, qy, kind), d

        def poly(P, t=tol):
            for k in range(len(P)):
                consider(P[k][0], P[k][1], "vert", t)
                if k:
                    qx, qy, tt = geo.nearest_on_seg(x, y, P[k - 1], P[k])
                    consider(qx, qy, "end" if tt <= .02 or tt >= .98 else "mid" if abs(tt - .5) <= .04 else "edge", t)
        for ds in self.geo.datasets:
            for i in ds.candidates(x, y, tol):
                r = ds.bbox[i]
                if r.adjusted(-tol, -tol, tol, tol).contains(QPointF(x, y)):
                    pg = ds.polys[i]
                    poly([(pg.at(k).x(), pg.at(k).y()) for k in range(pg.size())],
                         tol * (1.3 if ds.layers[i] == geo.LAYER_ROAD else 1.0))
        if self.extra_snap:
            for P in self.extra_snap():
                poly(P)
        return best[0]

    # ---------- الفأرة ولوحة المفاتيح
    def wheelEvent(self, e):
        f = 1.0015 ** e.angleDelta().y()
        pos = e.position()
        wx, wy = self.to_world(pos.x(), pos.y())
        self.s = max(0.004, min(80.0, self.s * f))
        nx, ny = self.to_world(pos.x(), pos.y())
        self.cx += wx - nx
        self.cy += wy - ny
        self._cache = None
        self.update()

    def mousePressEvent(self, e):
        self.setFocus()
        if e.button() == Qt.MouseButton.RightButton:
            if self.drawing:
                self.finished.emit()
            return
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._drag = (e.position(), self.cx, self.cy, False, e.button())

    def mouseMoveEvent(self, e):
        pos = e.position()
        x, y = self.to_world(pos.x(), pos.y())
        if self._drag is not None:
            start, cx, cy, moved, btn = self._drag
            d = pos - start
            if moved or d.manhattanLength() > 5:
                self._drag = (start, cx, cy, True, btn)
                self.cx = cx - d.x() / self.s
                self.cy = cy + d.y() / self.s
                self.update()
                return
        self.mouse = (x, y)
        if self.drawing:
            self.snap = self.find_snap(x, y)
            self.update()
        self.moved.emit(x, y)

    def mouseReleaseEvent(self, e):
        if self._drag is None:
            return
        start, _, _, moved, btn = self._drag
        self._drag = None
        if moved:
            self._invalidate()
            return
        if btn == Qt.MouseButton.LeftButton:
            pos = e.position()
            x, y = self.to_world(pos.x(), pos.y())
            if self.drawing and self.snap:
                x, y = self.snap[0], self.snap[1]
            self.clicked.emit(x, y, btn)

    def mouseDoubleClickEvent(self, e):
        if self.drawing and e.button() == Qt.MouseButton.LeftButton:
            self.finished.emit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        elif e.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) or \
                (e.key() == Qt.Key.Key_Z and e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.undo.emit()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finished.emit()
        else:
            super().keyPressEvent(e)

    # ---------- رسم أشكال المستخدم (للطبقة العلوية)
    def path_from(self, P, close=False):
        path = QPainterPath()
        if not P:
            return path
        path.moveTo(self.to_screen(*P[0]))
        for q in P[1:]:
            path.lineTo(self.to_screen(*q))
        if close:
            path.closeSubpath()
        return path

    def stroke(self, p, P, color, width_m=None, px=2.0, alpha=255, dash=False, close=False, fill=None):
        if len(P) < 2:
            return
        path = self.path_from(P, close)
        col = QColor(color)
        if width_m:
            c2 = QColor(col)
            c2.setAlpha(min(alpha, 120))
            pen = QPen(c2, max(width_m * self.s, 2.5))
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        col.setAlpha(alpha)
        pen = QPen(col, px)
        if dash:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(QBrush(fill) if fill is not None else Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    def label_at(self, p, P, text, color):
        if not P or self.s < 0.3:
            return
        mid = midpoint(P)
        c = self.to_screen(*mid)
        f = QFont()
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        r = QRectF(c.x() + 8, c.y() - 22, 260, 18)
        p.setPen(QColor(255, 255, 255, 230))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.drawText(r.translated(dx, dy), Qt.AlignmentFlag.AlignLeft, text)
        p.setPen(QColor(color))
        p.drawText(r, Qt.AlignmentFlag.AlignLeft, text)


def midpoint(P):
    if len(P) == 1:
        return P[0]
    total = geo.length(P)
    if total < 1e-6:
        return P[0]
    half = 0.0
    for j in range(1, len(P)):
        seg = math.hypot(P[j][0] - P[j - 1][0], P[j][1] - P[j - 1][1])
        if half + seg >= total / 2:
            t = (total / 2 - half) / seg
            return P[j - 1][0] + (P[j][0] - P[j - 1][0]) * t, P[j - 1][1] + (P[j][1] - P[j - 1][1]) * t
        half += seg
    return P[-1]
