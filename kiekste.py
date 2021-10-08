import os
import time
import logging
from PySide2 import QtCore, QtGui, QtWidgets

try:
    QShortcut = QtWidgets.QShortcut
except AttributeError:
    QShortcut = QtGui.QShortcut

NAME = 'kiekste'
LOG_LEVEL = logging.DEBUG
log = logging.getLogger(NAME)
log.setLevel(LOG_LEVEL)

DIM_OPACITY = 110
DIM_DURATION = 200
DIM_INTERVAL = 20
PATH = os.path.abspath(os.path.dirname(__file__))
IMG_PATH = os.path.join(PATH, 'img')
MODE_CAM = 'Image'
MODE_VID = 'Video'


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

        # self.setBackgroundBrush(QtGui.QBrush())

        self.overlay = Overlay(self)
        self.set_cursor(QtCore.Qt.CrossCursor)
        QtCore.QTimer(self).singleShot(200, self.overlay.dim)

        QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self, self.escape)
        for seq in QtCore.Qt.Key_S, QtCore.Qt.CTRL + QtCore.Qt.Key_S:
            QShortcut(QtGui.QKeySequence(seq), self, self.save_shot)
        for seq in QtCore.Qt.Key_C, QtCore.Qt.CTRL + QtCore.Qt.Key_C:
            QShortcut(QtGui.QKeySequence(seq), self, self.clip)

        for side in cursor_keys:
            QShortcut(QtGui.QKeySequence.fromString(side), self, self.tl_view)

        self.toolbox = None  # type: None | ToolBox
        QtCore.QTimer(self).singleShot(400, self._build_toolbox)
        self.settings = Settings()
        self.settings.loaded.connect(self._drag_last_tangle)
        self._ffmpeg = ''
        QtCore.QTimer(self).singleShot(400, self._find_ffmpeg)

    def tl_view(self):
        trigger_key = self.sender().key().toString()
        for side, shift in cursor_keys.items():
            if trigger_key == side:
                # print('side: %s' % side)
                # print('(scale_x %f _scale_y): %f' % (self._scale_x, self._scale_y))
                # self._scale_x += (shift[0] * 0.01)
                # self._scale_y += (shift[1] * 0.01)
                # print('(scale_x %f _scale_y): %f' % (self._scale_x, self._scale_y))
                self.scale((1 + (shift[0] * 0.0001)), (1 + (shift[1] * 0.0001)))
                return

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() & QtCore.Qt.LeftButton:
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
        self.show()
        return screen

    def _build_toolbox(self):
        self.toolbox = ToolBox(self)
        self.toolbox.close_requested.connect(self.escape)
        self.toolbox.save.connect(self.save_shot)
        self.toolbox.clip.connect(self.clip)
        self.toolbox.coords_changed.connect(self._on_toolbox_coords_change)
        self.toolbox.mode_switched.connect(self._change_mode)
        self.toolbox.pointer_toggled.connect(self.toggle_pointer)
        self.activateWindow()

    def _on_toolbox_coords_change(self, rect):
        self._dragtangle.setRect(*rect.getRect())
        self.overlay.cutout(rect)

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
        cutout = self.pixmap.copy(self._dragtangle)
        cutout.save(file_path)
        self.settings.last_save_path = os.path.dirname(file_path)
        self._save_rect()

    def clip(self):
        self.overlay.flash()
        cutout = self.pixmap.copy(self._dragtangle)
        print('self._dragtangle: %s' % self._dragtangle)
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
        rect = rect.normalized()
        self.overlay.cutout(rect)
        self.toolbox.set_spinners(rect)

    def _drag_last_tangle(self):
        if self.settings.last_rectangles:
            self._dragtangle.setRect(*self.settings.last_rectangles[-1])
            self._set_rectangle(self._dragtangle)

    def _find_ffmpeg(self):
        thread = FFMPegFinder(self)
        thread.found.connect(self._found_ffmpeg)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _found_ffmpeg(self, path):
        self._ffmpeg = path
        self.toolbox.add_mode(MODE_VID)

    def _change_mode(self, mode):
        print('mode: %s' % mode)

    def toggle_pointer(self, state):
        self.settings.draw_pointer = state
        self.settings._save()


class Overlay(QtCore.QObject):
    finished = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
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

    def cutout(self, rect: QtCore.QRect = None):
        if rect is None:
            rect = QtCore.QRect()
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
            self.cutout()
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
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        _TbBtn(self, None)
        self.spinners = []
        QtCore.QTimer(self).singleShot(100, self._add_spinners)

        _TbBtn(self, img.down)
        _TbBtn(self, img.save, self.save.emit)
        _TbBtn(self, img.clipboard, self.clip.emit)
        if parent.settings.draw_pointer:
            self.pointer_btn = _TbBtn(self, img.pointer, self.toggle_pointer)
        else:
            self.pointer_btn = _TbBtn(self, img.pointer_off, self.toggle_pointer)
        self.mode_button = _TbBtn(self, img.camera, self.toggle_mode)
        self.settings_btn = _TbBtn(self, img.settings)
        _TbBtn(self, img.x, self.x)

        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self._mode = MODE_CAM
        self._modes = [self._mode]
        self._modes_db = {MODE_CAM: img.camera, MODE_VID: img.video}
        self.show()
        self.setWindowOpacity(0.4)

    def _add_spinners(self):
        layout = self.layout()
        last_rects = self.parent().settings.last_rectangles
        for i in range(4):
            spin = _TbSpin(self)
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
        toolgeo.moveCenter(self.parent().geometry().center())
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
        if self.parent().settings.draw_pointer:
            self.pointer_btn.setIcon(img.pointer_off)
            self.pointer_toggled.emit(False)
        else:
            self.pointer_btn.setIcon(img.pointer)
            self.pointer_toggled.emit(True)

    def leaveEvent(self, event: QtCore.QEvent):
        self.setWindowOpacity(0.4)
        return super().leaveEvent(event)

    def enterEvent(self, event: QtCore.QEvent):
        self.setWindowOpacity(0.8)
        return super().leaveEvent(event)


class _TbBtn(QtWidgets.QToolButton):
    def __init__(self, parent, icon=None, func=None):
        super().__init__(parent)
        if func is None:
            self.setEnabled(False)
        else:
            self.clicked.connect(func)
        if icon is not None:
            self.setIcon(icon)
        self.setAutoRaise(True)
        self.setIconSize(QtCore.QSize(48, 48))
        parent.layout().addWidget(self)


class _TbSpin(QtWidgets.QSpinBox):
    def __init__(self, parent):
        super().__init__(parent)
        self.setMinimum(0)
        self.setMaximum(6384)
        self.setValue(0)
        self.setButtonSymbols(self.NoButtons)
        self.setStyleSheet(
            'QSpinBox {'
            'border: 0; border-radius: 5px; font-size: 24px;'
            'background: transparent; color: grey;'
            '}'
            'QSpinBox:hover {background: white; color: black}'
        )

    def leaveEvent(self, event: QtCore.QEvent):
        self.setButtonSymbols(self.NoButtons)
        return super().leaveEvent(event)

    def enterEvent(self, event: QtCore.QEvent):
        self.setButtonSymbols(self.UpDownArrows)
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


class _ImgStub:
    """
    Load-only-once image library object.

    For convenience this already lists all usable icons and for speed it
    just loads them up when actually needed.
    """

    def __init__(self):
        self._blank = self._get_ico()
        self.camera = self._blank
        self.check = self._blank
        self.clipboard = self._blank
        self.crop = self._blank
        self.down = self._blank
        self.edit = self._blank
        self.file = self._blank
        self.film = self._blank
        self.folder = self._blank
        self.github = self._blank
        self.info = self._blank
        self.link = self._blank
        self.maximize = self._blank
        self.monitor = self._blank
        self.move = self._blank
        self.pen = self._blank
        self.plus = self._blank
        self.pointer = self._blank
        self.pointer_off = self._blank
        self.question = self._blank
        self.refresh = self._blank
        self.save = self._blank
        self.settings = self._blank
        self.type = self._blank
        self.update = self._blank
        self.upload = self._blank
        self.upload2 = self._blank
        self.video = self._blank
        self.x = self._blank

    def __getattribute__(self, name):
        try:
            obj = super(_ImgStub, self).__getattribute__(name)
        except AttributeError:
            log.error('Icons lib got request for inexistent icon:\n  "%s"!', name)
            return self._blank

        if not name.startswith('_'):
            if obj is self._blank:
                icon = self._get_ico(name)
                setattr(self, name, icon)
                return icon
        return obj

    def _get_ico(self, name=''):
        if name:
            path = os.path.join(IMG_PATH, name + '.svg')
            if os.path.isfile(path):
                return QtGui.QIcon(path)
            log.error('No such file: {path}')
        return QtGui.QIcon()


img = _ImgStub()


class FFMPegFinder(QtCore.QThread):
    found = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

    def run(self):
        found = _find_ffmpeg()
        if found:
            self.found.emit(found)


def _find_ffmpeg():
    import subprocess

    nfo = subprocess.STARTUPINFO()
    nfo.wShowWindow = subprocess.SW_HIDE
    nfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        found = subprocess.check_output(['where', 'ffmpeg'], startupinfo=nfo)
        return found.decode().strip()
    except subprocess.CalledProcessError:
        return ''


def show():
    app = QtWidgets.QApplication([])
    win = Kiekste()
    win.show()
    app.exec_()


if __name__ == '__main__':
    show()
