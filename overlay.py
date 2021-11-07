from pyside import QtCore, QtGui, QtWidgets


DIM_OPACITY = 70
DIM_DURATION = 200
DIM_INTERVAL = 20
RESIZE_HANDLE_WIDTH = 40


class Overlay(QtCore.QObject):
    finished = QtCore.Signal()
    cursor_change = QtCore.Signal(QtCore.Qt.CursorShape)
    rect_change = QtCore.Signal(QtCore.QRectF)

    def __init__(self, parent):
        super().__init__(parent)
        self._lmouse = False
        self._space = False
        self._drawing = None
        self._panning = False
        self._rect_set = False
        self._pos = QtCore.QPointF()
        self._under_mouse = None

        self.geo = parent.geometry()
        # have some rectangles around the center one. tlrb being: top left right bottom
        self.rtl = QtWidgets.QGraphicsRectItem()
        self.rt = QtWidgets.QGraphicsRectItem()
        self.rtr = QtWidgets.QGraphicsRectItem()
        self.rl = QtWidgets.QGraphicsRectItem()
        self.rr = QtWidgets.QGraphicsRectItem()
        self.rbl = QtWidgets.QGraphicsRectItem()
        self.rb = QtWidgets.QGraphicsRectItem()
        self.rbr = QtWidgets.QGraphicsRectItem()
        self.rects = (self.rtl, self.rt, self.rtr, self.rl, self.rr, self.rbl, self.rb, self.rbr)
        self._sides = (self.rl, self.rt, self.rr, self.rb)
        self._corners = (self.rtl, self.rtr, self.rbl, self.rbr)

        self.dim_color = QtGui.QColor(QtCore.Qt.black)
        self.dim_color.setAlpha(0)
        scene = parent.scene()
        for r in self.rects:
            scene.addItem(r)
            r.setZValue(100)
            r.setBrush(self.dim_color)
            r.setPen(QtGui.QPen(QtCore.Qt.transparent, 0))

        # have a central rectangle
        self.rx = QtWidgets.QGraphicsRectItem()
        scene.addItem(self.rx)
        self.rx.setBrush(QtCore.Qt.transparent)
        self.rx.setPen(QtGui.QPen(QtCore.Qt.white, 0.5))

        self._fader = _ColorFader(self)
        self._side_highlight_pen = QtGui.QPen(QtCore.Qt.white, 0.3)
        self._side_no_highlight_pen = QtGui.QPen(QtCore.Qt.transparent)

        self.rrz = QtWidgets.QGraphicsRectItem()
        self.handle_color = QtGui.QColor(QtCore.Qt.white)
        self.handle_color.setAlpha(30)
        self.handle_color_hover =  QtGui.QColor(QtCore.Qt.white)
        self.handle_color_hover.setAlpha(60)
        self.rrz.setBrush(self.handle_color)
        self.rrz.setPen(self._side_no_highlight_pen)
        scene.addItem(self.rrz)

        self._cursors = {
            None: QtCore.Qt.SizeAllCursor,
            self.rx: QtCore.Qt.SizeAllCursor,
            self.rl: QtCore.Qt.SizeHorCursor,
            self.rr: QtCore.Qt.SizeHorCursor,
            self.rt: QtCore.Qt.SizeVerCursor,
            self.rb: QtCore.Qt.SizeVerCursor,
            self.rtl: QtCore.Qt.SizeFDiagCursor,
            self.rbr: QtCore.Qt.SizeFDiagCursor,
            self.rtr: QtCore.Qt.SizeBDiagCursor,
            self.rbl: QtCore.Qt.SizeBDiagCursor,
        }

    @property
    def rect(self):
        return self.rx.rect().toAlignedRect()

    def shift_rect(self, vector: QtCore.QPointF, rect: QtCore.QRectF = None):
        if rect is None:
            rect = self.rx.rect()
        center = rect.center()
        rect.moveCenter(center + vector)
        self._set_rect(rect)

    def cursor_move(self, pos: QtCore.QPointF):
        diff = QtCore.QPointF(pos) - self._pos
        self._pos.setX(pos.x())
        self._pos.setY(pos.y())

        self._check_rect_change()
        self._set_cursor()

        if not self._lmouse:
            return

        if self._drawing is None and self.rx.isUnderMouse():
            if not self._panning:
                self._panning = True
            self.shift_rect(diff)
        else:
            if self._drawing is None:
                self._drawing = QtCore.QRectF(pos, QtCore.QPointF(0, 0))
            if self._space:
                self.shift_rect(diff, self._drawing)
            else:
                self._drawing.setBottomRight(pos)
                self._set_rect(self._drawing)

    def _check_rect_change(self):
        if self.rx.isUnderMouse():
            under_mouse = self.rx
        else:
            for rect in self.rects:
                if rect.isUnderMouse():
                    under_mouse = rect
                    break
            else:
                under_mouse = self.rx

        if under_mouse is self._under_mouse:
            return
        self._under_mouse = under_mouse

        # highlight side rectangles
        for side_rect in self._sides:
            if side_rect is under_mouse and not self._lmouse:
                side_rect.setPen(self._side_highlight_pen)
            else:
                side_rect.setPen(self._side_no_highlight_pen)
        # show resize handle
        if under_mouse in self.rects:
            center_rect = self.rx.rect()
            tl, br = center_rect.topLeft(), center_rect.bottomRight()
            tl.setX(tl.x() - RESIZE_HANDLE_WIDTH)
            tl.setY(tl.y() - RESIZE_HANDLE_WIDTH)
            br.setX(br.x() + RESIZE_HANDLE_WIDTH)
            br.setY(br.y() + RESIZE_HANDLE_WIDTH)
            center_rect.setTopLeft(tl)
            center_rect.setBottomRight(br)
            handle_rect = center_rect.intersected(under_mouse.rect())
            self.rrz.setRect(handle_rect)
            self.rrz.show()
        else:
            self.rrz.hide()

    def _set_cursor(self):
        if self._under_mouse is self.rx:
            if self._lmouse:
                self.cursor_change.emit(QtCore.Qt.ClosedHandCursor)
            else:
                self.cursor_change.emit(self._cursors[self.rx])
        else:
            if self.rrz.isUnderMouse():
                self.rrz.setBrush(self.handle_color_hover)
                if self._lmouse:
                    self.cursor_change.emit(QtCore.Qt.ClosedHandCursor)
                else:
                    self.cursor_change.emit(self._cursors[self._under_mouse])
            else:
                self.rrz.setBrush(self.handle_color)
                self.cursor_change.emit(QtCore.Qt.CrossCursor)

    def mouse_press(self, state):
        self._lmouse = state
        self._set_cursor()
        if not state:
            self._panning = False
            self._drawing = None

    def space_press(self, state):
        self._space = state

    def wheel_scroll(self, delta):
        rect = self.rx.rect()
        for r, value_func, rect_func in (
            (self.rl, rect.x, rect.setX),
            (self.rt, rect.y, rect.setY),
            (self.rr, rect.right, rect.setRight),
            (self.rb, rect.bottom, rect.setBottom),
        ):
            if not r.isUnderMouse():
                continue
            rect_func(value_func() + delta / 10.0)
            self._set_rect(rect)
            return rect

    def set_rect(self, rect):
        # type: (QtCore.QRectF | QtCore.QRect) -> QtCore.QRectF | QtCore.QRect
        """Set the inner rectangle."""
        self._rect_set = True
        if not rect.isValid():
            rect = rect.normalized()
        recw, rech = rect.width(), rect.height()
        wr = self.geo.right() - rect.right()
        hb = self.geo.bottom() - rect.bottom()

        self.rtl.setRect(0, 0, rect.x(), rect.y())
        self.rt.setRect(rect.x(), 0, recw, rect.y())
        self.rtr.setRect(rect.right(), 0, wr, rect.y())
        self.rl.setRect(0, rect.y(), rect.x(), rech)
        self.rr.setRect(rect.right(), rect.y(), wr, rech)
        self.rbl.setRect(0, rect.bottom(), rect.x(), hb)
        self.rb.setRect(rect.x(), rect.bottom(), recw, hb)
        self.rbr.setRect(rect.right(), rect.bottom(), wr, hb)

        self.rx.setRect(rect)
        return rect

    def _set_rect(self, rect: QtCore.QRectF):
        """Set the inner rectangle and signal the change."""
        self.rect_change.emit(rect)
        self.set_rect(rect)
        return rect

    def dim(self):
        self._fader.fade(self.rects, self.dim_color, DIM_OPACITY)

    def undim(self):
        self._fader.finished.connect(self.finished.emit)
        self._fader.fade(self.rects, self.dim_color, 0)

    def flash(self):
        self.color = QtGui.QColor(QtCore.Qt.white)
        self.color.setAlpha(100)
        self._fader.fade([self.rx], self.color, 0)


class _ColorFader(QtCore.QObject):
    finished = QtCore.Signal()

    def __init__(self, parent):
        super().__init__()
        self._ticks = 0
        self._delta = 0
        self._timer = QtCore.QTimer(parent)
        self._timer.timeout.connect(self._update)
        self._timer.setInterval(DIM_INTERVAL)
        self._color = None  # type: QtGui.QColor | None
        self._objs = []

    def fade(self, objs, color, target_opacity):
        self._color = color
        self._objs[:] = objs
        self._ticks = DIM_DURATION / DIM_INTERVAL
        self._delta = (target_opacity - color.alpha()) / self._ticks
        self._timer.start()

    def _update(self):
        if self._color is None:
            return

        self._ticks -= 1
        if self._ticks < 0:
            self._timer.stop()
            self.finished.emit()
            return

        new_value = self._color.alpha() + self._delta
        self._color.setAlpha(max(new_value, 0))
        for obj in self._objs:
            obj.setBrush(self._color)
