import os
import logging

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

        self._dragging = False
        self._cursor_pos = QtGui.QCursor.pos()
        self._dragtangle = QtCore.QRect()
        self._panning = False
        self._pan_point = None

        self._setup_ui()
        self.overlay = Overlay(self)
        self.overlay.cursor_change.connect(self.set_cursor)

        # self.setBackgroundBrush(QtGui.QBrush())

        QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self, self.escape)
        for seq in QtCore.Qt.Key_S, QtCore.Qt.CTRL + QtCore.Qt.Key_S:
            QShortcut(QtGui.QKeySequence(seq), self, self.save_shot)
        for seq in QtCore.Qt.Key_C, QtCore.Qt.CTRL + QtCore.Qt.Key_C:
            QShortcut(QtGui.QKeySequence(seq), self, self.clip)

        for side in cursor_keys:
            QShortcut(QtGui.QKeySequence.fromString(side), self, self.shift_view)

        self.toolbox = None  # type: None | ToolBox
        self.settings = Settings()
        self.settings.loaded.connect(self._drag_last_tangle)
        self.videoman = video_man.VideoMan(self)
        self.videoman.video_found.connect(self._found_video_tool)

        self.set_cursor(QtCore.Qt.CrossCursor)
        self.show()

    def showEvent(self, event):
        self.overlay.dim()
        self._build_toolbox()
        return super().showEvent(event)

    def shift_view(self):
        trigger_key = self.sender().key().toString()
        for side, shift in cursor_keys.items():
            if trigger_key == side:
                self._dragtangle.moveTo(
                    self._dragtangle.x() + shift[0], self._dragtangle.y() + shift[1]
                )
                self._set_rectangle(self._dragtangle)
                return

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self.overlay.cursor_move(event.pos())

        if event.buttons() & QtCore.Qt.LeftButton:
            self.overlay.mouse_press(True)

            if not self._dragging and not self._panning:
                self._dragtangle.setTopLeft(event.pos())
                self._dragging = True
            else:
                if self._panning:
                    if self._pan_point is None:
                        self._pan_point = event.pos() - self._dragtangle.center()
                        self.set_cursor(QtCore.Qt.ClosedHandCursor)

                    self._dragtangle.moveCenter(event.pos() - self._pan_point)
                else:
                    self._dragtangle.setBottomRight(event.pos())
                self._set_rectangle(self._dragtangle)
        else:
            if self._dragtangle.contains(event.pos()):
                if self._panning:
                    return
                self._panning = True
                self.set_cursor(QtCore.Qt.OpenHandCursor)
            else:
                self._pan_off()
                self.set_cursor(QtCore.Qt.CrossCursor)

        return super().mouseMoveEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key_Space:
            if event.isAutoRepeat():
                return
            self.overlay.space_press(True)

        if self._dragging and not self._panning and event.key() == QtCore.Qt.Key_Space:
            if event.isAutoRepeat():
                return
            self._panning = True
            self._pan_point = QtGui.QCursor.pos() - self._dragtangle.center()
            self.set_cursor(QtCore.Qt.ClosedHandCursor)
            return
        return super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if self._panning and event.key() == QtCore.Qt.Key_Space:
            if event.isAutoRepeat():
                return
            self._pan_off()
            self.set_cursor(QtCore.Qt.CrossCursor)
            return
        return super().keyReleaseEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self.overlay.mouse_press(False)

        if self._dragging:
            self._dragging = False
        if self._dragtangle.contains(event.pos()):
            self.set_cursor(QtCore.Qt.OpenHandCursor)
        self._pan_off()
        return super().mouseReleaseEvent(event)

    def _pan_off(self):
        self._panning = False
        self._pan_point = None

    def escape(self):
        self.overlay.finished.connect(self.close)
        self.overlay.undim()

    def _setup_ui(self):
        self.setWindowTitle(NAME)
        self.setMouseTracking(True)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        screen = QtGui.QGuiApplication.primaryScreen()
        geo = screen.geometry()
        self.pixmap = screen.grabWindow(0)
        self.setBackgroundBrush(QtGui.QBrush(self.pixmap))

        scene = QtWidgets.QGraphicsScene(0, 0, geo.width(), geo.height())
        self.setScene(scene)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.BoundingRectViewportUpdate)
        self.setCacheMode(QtWidgets.QGraphicsView.CacheBackground)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
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
        self.activateWindow()

    def set_cursor(self, shape: QtCore.Qt.CursorShape):
        cursor = self.cursor()
        cursor.setShape(shape)
        self.setCursor(cursor)

    def save_shot(self):
        if not self._dragtangle:
            return

        file_path, file_type = QtWidgets.QFileDialog.getSaveFileName(
            self, NAME + ' Save Screenshot', self.settings.last_save_path or PATH, 'PNG (*.png)'
        )
        if not file_path:
            return

        self.overlay.flash()
        cutout = self.pixmap.copy(self._dragtangle.normalized())
        cutout.save(file_path)
        self.settings.last_save_path = os.path.dirname(file_path)
        self._save_rect()

    def clip(self):
        self.overlay.flash()
        cutout = self.pixmap.copy(self._dragtangle.normalized())
        QtWidgets.QApplication.clipboard().setPixmap(cutout)
        self._save_rect()

    def _save_rect(self):
        rect_list = list(self._dragtangle.getRect())
        if rect_list in self.settings.last_rectangles:
            if self.settings.last_rectangles[-1] == rect_list:
                return
            self.settings.last_rectangles.remove(rect_list)
        self.settings.last_rectangles.append(rect_list)
        if len(self.settings.last_rectangles) > self.settings.max_rectangles:
            del self.settings.last_rectangles[: -self.settings.max_rectangles]
        self.settings._save()

    def _set_rectangle(self, rect: QtCore.QRect):
        if self.toolbox is None:
            return
        rect = rect.normalized()
        self.overlay.set_rect(rect)
        self.toolbox.set_spinners(rect)

    def _drag_last_tangle(self):
        if self.settings.last_rectangles:
            self._dragtangle.setRect(*self.settings.last_rectangles[-1])
            self._set_rectangle(self._dragtangle)

    def _found_video_tool(self):
        if self.toolbox is None:
            return
        self.toolbox.add_mode(MODE_VID)

    def _change_mode(self, mode):
        print('mode: %s' % mode)

    def toggle_pointer(self, state):
        self.settings.draw_pointer = state
        self.settings._save()


class Overlay(QtCore.QObject):
    finished = QtCore.Signal()
    cursor_change = QtCore.Signal(QtCore.Qt.CursorShape)

    def __init__(self, parent: Kiekste):
        super().__init__(parent)
        self._parent = parent
        self._lmouse = False

        self.geo = parent.geometry()
        self.r1 = QtWidgets.QGraphicsRectItem()
        self.r2 = QtWidgets.QGraphicsRectItem()
        self.r3 = QtWidgets.QGraphicsRectItem()
        self.r4 = QtWidgets.QGraphicsRectItem()
        self.rects = ()
        self._set_outer()
        self.color.setAlpha(0)
        scene = parent.scene()

        for r in self.rects:
            scene.addItem(r)
            r.setBrush(self.color)
            r.setPen(QtGui.QPen(QtCore.Qt.transparent, 0))

        self.rx = QtWidgets.QGraphicsRectItem()
        scene.addItem(self.rx)
        self.rx.setBrush(QtCore.Qt.transparent)
        self.rx.setPen(QtGui.QPen(QtCore.Qt.white, 1))

        self._ticks = 0
        self._delta = 0
        self._timer = QtCore.QTimer(parent)
        self._timer.timeout.connect(self._update)
        self._timer.setInterval(DIM_INTERVAL)
        self._rect_set = False

    @property
    def rect(self):
        return

    def cursor_move(self, pos: QtCore.QPoint):
        pass

    def mouse_press(self, state):
        self._lmouse = state

    def space_press(self, state):
        self._space = state

    def set_rect(self, rect: QtCore.QRect):
        self._rect_set = True
        geow, geoh = self.geo.width(), self.geo.height()
        recw, rech = rect.width(), rect.height()
        self.r1.setRect(0, 0, geow, rect.y())
        self.r2.setRect(0, rect.y(), rect.x(), rech)
        self.r3.setRect(rect.x() + recw, rect.y(), geow - recw - rect.x(), rech)
        self.r4.setRect(0, rech + rect.y(), geow, geoh - rech - rect.y())
        self.rx.setRect(rect)

    def _set_outer(self):
        self.rects = (self.r1, self.r2, self.r3, self.r4)
        self.color = QtGui.QColor(QtCore.Qt.black)

    def dim(self):
        if not self._rect_set:
            self.set_rect(QtCore.QRect())
        self._ticks = DIM_DURATION / DIM_INTERVAL
        self._delta = DIM_OPACITY / self._ticks
        self._timer.start()

    def undim(self):
        self._set_outer()
        self.color.setAlpha(DIM_OPACITY)
        self._ticks = DIM_DURATION / DIM_INTERVAL
        self._delta = -DIM_OPACITY / self._ticks
        self._timer.start()

    def _update(self):
        self._ticks -= 1
        if self._ticks < 0:
            self._timer.stop()
            self.finished.emit()
            return

        new_value = self.color.alpha() + self._delta
        self.color.setAlpha(max(new_value, 0))
        for r in self.rects:
            r.setBrush(self.color)

    def flash(self):
        self.rects = (self.rx,)
        self.color = QtGui.QColor(QtCore.Qt.white)
        self._ticks = DIM_DURATION / DIM_INTERVAL
        self.color.setAlpha(100)
        self._delta = -DIM_OPACITY / self._ticks
        self._timer.start()


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
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

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
        layout = self.layout()
        last_rects = self._parent.settings.last_rectangles
        for i in range(4):
            spin = widgets._TbSpin(self)
            if last_rects:
                spin.setValue(last_rects[-1][i])
            layout.insertWidget(1 + i, spin)
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

    def set_spinners(self, rect: QtCore.QRect):
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
    loaded = QtCore.Signal()

    def __init__(self):
        super(Settings, self).__init__()
        self.last_save_path = ''
        self.last_rectangles = []
        self.max_rectangles = 12
        self.draw_pointer = True

        self._settings_file = NAME.lower() + '.json'
        self._settings_path = os.path.join(PATH, self._settings_file)
        QtCore.QTimer(self).singleShot(500, self._load)

    def _load(self):
        for key, value in self._get_json().items():
            if key not in self.__dict__:
                log.warning(f'Key {key} not yet listed in Settings obj!1')
            self.__dict__[key] = value
        self.loaded.emit()

    def _get_json(self):
        import json

        if os.path.isfile(self._settings_path):
            with open(self._settings_path) as file_obj:
                return json.load(file_obj)
        return {}

    def _save(self):
        import json

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
