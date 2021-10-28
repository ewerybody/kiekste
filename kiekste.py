import os
import json
import logging
import time

import image_stub
import video_man
import widgets
from pyside import QtCore, QtGui, QtWidgets, QShortcut

NAME = 'kiekste'
PATH = os.path.abspath(os.path.dirname(__file__))
LOG_LEVEL = logging.DEBUG
log = logging.getLogger(NAME)
log.setLevel(LOG_LEVEL)
DIM_OPACITY = 110
DIM_DURATION = 200
DIM_INTERVAL = 20
MODE_CAM = 'Image'
MODE_VID = 'Video'
IMG = image_stub.ImageStub()


cursor_keys = {'Left': (-1, 0), 'Up': (0, -1), 'Right': (1, 0), 'Down': (0, 1)}


class Kiekste(QtWidgets.QGraphicsView):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self._setup_ui()
        self._cursor_pos = None
        self.overlay = Overlay(self)
        self.overlay.cursor_change.connect(self.set_cursor)

        self.toolbox = None  # type: None | ToolBox
        self.videoman = video_man.VideoMan(self)
        self.videoman.video_found.connect(self._found_video_tool)

        QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self, self.escape)
        for seq in QtCore.Qt.Key_S, QtCore.Qt.CTRL + QtCore.Qt.Key_S:
            QShortcut(QtGui.QKeySequence(seq), self, self.save_shot)
        for seq in QtCore.Qt.Key_C, QtCore.Qt.CTRL + QtCore.Qt.Key_C:
            QShortcut(QtGui.QKeySequence(seq), self, self.clip)

        for seq in (QtCore.Qt.ALT + QtCore.Qt.Key_V, ):
            QShortcut(QtGui.QKeySequence(seq), self, self.video_capture)

        for side in cursor_keys:
            QShortcut(QtGui.QKeySequence.fromString(side), self, self.shift_rect)

        self.set_cursor(QtCore.Qt.CrossCursor)
        self.show()

    def showEvent(self, event):
        self.overlay.dim()
        if self.toolbox is None:
            self._build_toolbox()
            self._draw_last_tangle()
        return super().showEvent(event)

    def shift_rect(self):
        short_cut = self.sender()  # type: QShortcut
        if not isinstance(short_cut, QShortcut):
            return
        trigger_key = short_cut.key().toString()
        shift = cursor_keys.get(trigger_key)
        if shift:
            self.overlay.shift_rect(*shift)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        self.overlay.wheel_scroll(event.delta())
        return super().wheelEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() & QtCore.Qt.LeftButton:
            self.overlay.mouse_press(True)
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self.overlay.cursor_move(QtCore.QPointF(event.pos()))

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        if event.key() == QtCore.Qt.Key_Space:
            self.overlay.space_press(True)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        if event.key() == QtCore.Qt.Key_Space:
            self.overlay.space_press(False)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self.overlay.mouse_press(False)

    def escape(self):
        self.overlay.finished.connect(self.close)
        self.overlay.undim()

    def set_screenshot(self):
        screen = QtGui.QGuiApplication.primaryScreen()
        geo = screen.geometry()
        self._cursor_pos = self.cursor().pos()
        self.pixmap = screen.grabWindow(0)
        self.setBackgroundBrush(QtGui.QBrush(self.pixmap))
        return screen, geo

    def _setup_ui(self):
        self.setWindowTitle(NAME)
        self.setMouseTracking(True)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        screen, geo = self.set_screenshot()
        scene = QtWidgets.QGraphicsScene(0, 0, geo.width(), geo.height())
        self.setScene(scene)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.BoundingRectViewportUpdate)
        self.setCacheMode(QtWidgets.QGraphicsView.CacheBackground)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowFlags(
            QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setStyleSheet('QGraphicsView {background:transparent;}')

        # Because there is a white border that I can't get rid of,
        # lets shift and size the window a little:
        geo_hack = QtCore.QRect(-1, -1, geo.width() + 2, geo.height() + 3)
        self.setGeometry(geo_hack)

        # Now because of this we need to adjust the scaling to compensate for that.
        # on top of the scaling we do for HighDPI scaled desktop vs pixels grabbed.
        width_factor = geo.width() / geo_hack.width() + 0.001
        pix_rect = self.pixmap.rect()
        self.scale(geo.width() * width_factor / pix_rect.width(), geo.height() / pix_rect.height())

        self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        return screen

    def _build_toolbox(self):
        self.toolbox = ToolBox(self)

        self.toolbox.close_requested.connect(self.escape)
        self.toolbox.save.connect(self.save_shot)
        self.toolbox.clip.connect(self.clip)
        self.toolbox.coords_changed.connect(self.overlay.set_rect)
        self.toolbox.mode_switched.connect(self._change_mode)
        self.toolbox.pointer_toggled.connect(self.toggle_pointer)
        self.overlay.rect_change.connect(self.toolbox.set_spinners)
        self.activateWindow()

    def set_cursor(self, shape: QtCore.Qt.CursorShape):
        cursor = self.cursor()
        if cursor != shape:
            cursor.setShape(shape)
            self.setCursor(cursor)

    def save_shot(self):
        rect = self.overlay.rect
        if not rect:
            return
        file_path, file_type = QtWidgets.QFileDialog.getSaveFileName(
            self, NAME + ' Save Screenshot', self.settings.last_save_path or PATH, 'PNG (*.png)'
        )
        if not file_path:
            return

        self.overlay.flash()
        cutout = self.pixmap.copy(rect)
        cutout.save(file_path)
        self.settings.last_save_path = os.path.dirname(file_path)
        self._save_rect()

    def clip(self):
        rect = self.overlay.rect
        if not rect:
            return
        self.overlay.flash()
        cutout = self.pixmap.copy(rect)
        QtWidgets.QApplication.clipboard().setPixmap(cutout)
        self._save_rect()

    def _save_rect(self):
        rect_list = list(self.overlay.rect.getRect())
        if rect_list in self.settings.last_rectangles:
            if self.settings.last_rectangles[-1] == rect_list:
                return
            self.settings.last_rectangles.remove(rect_list)
        self.settings.last_rectangles.append(rect_list)
        if len(self.settings.last_rectangles) > self.settings.max_rectangles:
            del self.settings.last_rectangles[: -self.settings.max_rectangles]
        self.settings._save()

    def _draw_last_tangle(self):
        if self.settings.last_rectangles:
            rect = QtCore.QRect(*self.settings.last_rectangles[-1])
            self.overlay.set_rect(rect)
            if self.toolbox is None:
                return
            self.toolbox.set_spinners(rect)

    def _found_video_tool(self):
        if self.toolbox is None:
            return
        self.toolbox.add_mode(MODE_VID)

    def _change_mode(self, mode):
        print('mode: %s' % mode)

    def toggle_pointer(self, state):
        self.settings.draw_pointer = state
        self.settings._save()

    def video_capture(self):
        if not self.videoman.capturing:
            self._save_rect()
            self.overlay.undim()
            self.video_widget = VideoWidget(self, self.videoman)
            widget_geo = self.video_widget.geometry()
            widget_geo.setX(self.overlay.rect.x())
            widget_geo.setY(self.overlay.rect.bottom() + 10)
            self.video_widget.show()
            self.video_widget.setGeometry(widget_geo)
            self.setBackgroundBrush(QtGui.QBrush())
            self.videoman.capture(self.overlay.rect)
            self.videoman.capture_stopped.connect(self._on_capture_stopped)
        else:
            self.video_widget.stop()

    def _on_capture_stopped(self):
        self.hide()
        self.set_screenshot()
        self.show()


class Overlay(QtCore.QObject):
    finished = QtCore.Signal()
    cursor_change = QtCore.Signal(QtCore.Qt.CursorShape)
    rect_change = QtCore.Signal(QtCore.QRectF)

    def __init__(self, parent: Kiekste):
        super().__init__(parent)
        self._parent = parent
        self._lmouse = False
        self._space = False
        self._dragging = None
        self._panning = False
        self._rect_set = False
        self._pos = QtCore.QPointF()

        self.geo = parent.geometry()
        # have some rectangles around the center one tlrb being: top left right bottom
        self.rtl = QtWidgets.QGraphicsRectItem()
        self.rt = QtWidgets.QGraphicsRectItem()
        self.rtr = QtWidgets.QGraphicsRectItem()
        self.rl = QtWidgets.QGraphicsRectItem()
        self.rr = QtWidgets.QGraphicsRectItem()
        self.rbl = QtWidgets.QGraphicsRectItem()
        self.rb = QtWidgets.QGraphicsRectItem()
        self.rbr = QtWidgets.QGraphicsRectItem()
        self.rects = [self.rtl, self.rt, self.rtr, self.rl, self.rr, self.rbl, self.rb, self.rbr]

        self.dim_color = QtGui.QColor(QtCore.Qt.black)
        self.dim_color.setAlpha(0)
        scene = parent.scene()
        for r in self.rects:
            scene.addItem(r)
            r.setBrush(self.dim_color)
            r.setPen(QtGui.QPen(QtCore.Qt.transparent, 0))

        # have a central rectangle
        self.rx = QtWidgets.QGraphicsRectItem()
        scene.addItem(self.rx)
        self.rx.setBrush(QtCore.Qt.transparent)
        self.rx.setPen(QtGui.QPen(QtCore.Qt.white, 0.5))

        self._fader = _ColorFader(self)

        if parent.settings.draw_pointer:
            pointer = QtWidgets.QGraphicsPixmapItem(IMG.pointer_black.pixmap(64))
            pointer.setPos(parent.cursor().pos())
            scene.addItem(pointer)
        # pointer.move
        # pointer.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        # pointer.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)

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

        self._set_cursor()

        if not self._lmouse:
            return

        if self._dragging is None and self.rx.isUnderMouse():
            if not self._panning:
                self._panning = True
            self.shift_rect(diff)
        else:
            if self._dragging is None:
                self._dragging = QtCore.QRectF(pos, QtCore.QPointF(0, 0))
            if self._space:
                self.shift_rect(diff, self._dragging)
            else:
                self._dragging.setBottomRight(pos)
                self._set_rect(self._dragging)

    def _set_cursor(self):
        if self.rx.isUnderMouse():
            if self._lmouse:
                self.cursor_change.emit(QtCore.Qt.ClosedHandCursor)
            else:
                self.cursor_change.emit(QtCore.Qt.OpenHandCursor)
        else:
            self.cursor_change.emit(QtCore.Qt.CrossCursor)

    def mouse_press(self, state):
        self._lmouse = state
        self._set_cursor()
        if not state:
            self._panning = False
            self._dragging = None

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


class VideoWidget(QtWidgets.QWidget):
    def __init__(self, parent, videoman):
        super().__init__(parent)
        self.videoman = videoman
        self.hlayout = QtWidgets.QHBoxLayout(self)
        self.hlayout.setContentsMargins(5, 5, 5, 5)

        # QtWidgets.QLCDNumber
        self._t0 = time.time()
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._set_label)
        self._timer.setInterval(100)
        self.label = QtWidgets.QLabel()
        self.hlayout.addWidget(self.label)
        widgets._TbBtn(self, IMG.x, self.stop)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self._timer.start()

    def stop(self):
        self.videoman.stop()
        self._timer.stop()
        self.deleteLater()

    def _set_label(self):
        self.label.setText(str(time.time() - self._t0))


class ToolBox(QtWidgets.QWidget):
    close_requested = QtCore.Signal()
    mode_switched = QtCore.Signal(str)
    save = QtCore.Signal()
    clip = QtCore.Signal()
    coords_changed = QtCore.Signal(QtCore.QRect)
    pointer_toggled = QtCore.Signal(bool)

    def __init__(self, parent: Kiekste):
        super().__init__(parent)
        self._parent = parent
        self.hlayout = QtWidgets.QHBoxLayout(self)
        self.hlayout.setContentsMargins(5, 5, 5, 5)

        widgets._TbBtn(self, None)
        self.spinners = []
        QtCore.QTimer(self).singleShot(100, self._add_spinners)

        widgets._TbBtn(self, IMG.down)
        widgets._TbBtn(self, IMG.save, self.save.emit)
        widgets._TbBtn(self, IMG.clipboard, self.clip.emit)
        if parent.settings.draw_pointer:
            self.pointer_btn = widgets._TbBtn(self, IMG.pointer, self.toggle_pointer)
        else:
            self.pointer_btn = widgets._TbBtn(self, IMG.pointer_off, self.toggle_pointer)
        self.mode_button = widgets._TbBtn(self, IMG.camera, self.toggle_mode)
        self.settings_btn = widgets._TbBtn(self, IMG.settings)
        widgets._TbBtn(self, IMG.x, self.x)

        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self._mode = MODE_CAM
        self._modes = [self._mode]
        self._modes_db = {MODE_CAM: IMG.camera, MODE_VID: IMG.video}
        self.show()
        self.setWindowOpacity(0.4)

    def _add_spinners(self):
        last_rects = self._parent.settings.last_rectangles
        for i in range(4):
            spin = widgets._TbSpin(self)
            if last_rects:
                spin.setValue(last_rects[-1][i])
            self.hlayout.insertWidget(1 + i, spin)
            self.spinners.append(spin)
            spin.valueChanged.connect(self.on_spin)
        QtCore.QTimer(self).singleShot(5, self._center_box)

    def showEvent(self, event):
        self._center_box()
        return super().showEvent(event)

    def _center_box(self):
        toolgeo = self.geometry()
        toolgeo.moveCenter(self._parent.geometry().center())
        toolgeo.moveTop(0)
        self.setGeometry(toolgeo)

    def add_mode(self, mode):
        if mode in self._modes_db:
            self._modes.append(mode)
        else:
            RuntimeError('No Mode "%s"' % mode)

    def toggle_mode(self):
        i = self._modes.index(self._mode) + 1
        if i == len(self._modes):
            i = 0

        new_mode = self._modes[i]
        if new_mode == self._mode:
            return

        self._mode = new_mode
        self.mode_button.setIcon(self._modes_db[self._mode])
        self.mode_switched.emit(self._mode)

    def x(self):
        self.close_requested.emit()
        self.hide()

    def on_spin(self):
        coords = QtCore.QRect()
        coords.setRect(*(s.value() for s in self.spinners))
        self.coords_changed.emit(coords)

    def set_spinners(self, rect):
        # type: (QtCore.QRectF | QtCore.QRect) -> None
        rect = rect.normalized()
        for value, spinbox in zip(rect.getRect(), self.spinners):
            spinbox.blockSignals(True)
            spinbox.setValue(value)
            spinbox.setEnabled(True)
            spinbox.blockSignals(False)

    def toggle_pointer(self):
        if self._parent.settings.draw_pointer:
            self.pointer_btn.setIcon(IMG.pointer_off)
            self.pointer_toggled.emit(False)
        else:
            self.pointer_btn.setIcon(IMG.pointer)
            self.pointer_toggled.emit(True)

    def leaveEvent(self, event: QtCore.QEvent):
        self.setWindowOpacity(0.4)
        return super().leaveEvent(event)

    def enterEvent(self, event: QtCore.QEvent):
        self.setWindowOpacity(0.8)
        return super().leaveEvent(event)


class Settings(QtCore.QObject):
    def __init__(self):
        super(Settings, self).__init__()
        self.last_save_path = ''
        self.last_rectangles = []
        self.max_rectangles = 12
        self.draw_pointer = True
        self.video_fps = 10
        self.video_quality = 5000

        self._settings_file = NAME.lower() + '.json'
        self._settings_path = os.path.join(PATH, self._settings_file)
        self._load()

    def _load(self):
        for key, value in self._get_json().items():
            if key not in self.__dict__:
                log.warning(f'Key {key} not yet listed in Settings obj!1')
            self.__dict__[key] = value

    def _get_json(self):
        import json

        if os.path.isfile(self._settings_path):
            with open(self._settings_path) as file_obj:
                return json.load(file_obj)
        return {}

    def _save(self):
        current = self._get_json()
        do_write = False
        for name, value in self.__dict__.items():
            if name.startswith('_'):
                continue
            if not isinstance(value, (str, int, list, bool)):
                continue
            if name not in current:
                do_write = True
                current[name] = value
            if current[name] == value:
                continue
            do_write = True
            current[name] = value

        if not do_write:
            return

        with open(self._settings_path, 'w') as file_obj:
            json.dump(current, file_obj, indent=2, sort_keys=True)


def show():
    app = QtWidgets.QApplication([])
    win = Kiekste()
    win.show()
    app.exec_()


if __name__ == '__main__':
    show()
