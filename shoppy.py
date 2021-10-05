import os
import time
from PySide2 import QtCore, QtGui, QtWidgets

NAME = 'Shoppy'
import logging

LOG_LEVEL = logging.DEBUG
log = logging.getLogger(NAME)
log.setLevel(LOG_LEVEL)

DIM_OPACITY = 150
DIM_DURATION = 200
DIM_INTERVAL = 20
PATH = os.path.abspath(os.path.dirname(__file__))
IMG_PATH = os.path.join(PATH, 'img')
MODE_CAM = 'Image'
MODE_VID = 'Video'


class Shoppy(QtWidgets.QGraphicsView):
    def __init__(self):
        super(Shoppy, self).__init__()

        self._dragging = False
        self._cursor_pos = QtGui.QCursor.pos()
        self._dragtangle = QtCore.QRect()
        self._panning = False
        self._pan_point = None

        self.set_cursor(QtCore.Qt.CrossCursor)

        screen = self._setup_ui()
        self.original_pixmap = screen.grabWindow(0)
        self.setBackgroundBrush(QtGui.QBrush(self.original_pixmap))

        self.dimmer = Dimmer(self)
        QtCore.QTimer(self).singleShot(300, self.dimmer.dim)

        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self, self.escape)
        for seq in QtCore.Qt.Key_S, QtCore.Qt.CTRL + QtCore.Qt.Key_S:
            QtWidgets.QShortcut(QtGui.QKeySequence(seq), self, self.save_shot)
        for seq in QtCore.Qt.Key_C, QtCore.Qt.CTRL + QtCore.Qt.Key_C:
            QtWidgets.QShortcut(QtGui.QKeySequence(seq), self, self.clip)

        self.toolbox = None
        QtCore.QTimer(self).singleShot(400, self._build_toolbox)
        self.settings = Settings()
        self.settings.loaded.connect(self._drag_last_tangle)

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
                self.dimmer.cutout(self._dragtangle)
        else:
            if self._dragtangle.contains(event.pos()):
                if self._panning:
                    return
                self._panning = True
                self.set_cursor(QtCore.Qt.OpenHandCursor)
            else:
                self.pan_off()
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
            self.pan_off()
            self.set_cursor(QtCore.Qt.CrossCursor)
            return
        return super().keyReleaseEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._dragging:
            self._dragging = False
        if self._dragtangle.contains(event.pos()):
            self.set_cursor(QtCore.Qt.OpenHandCursor)
        self.pan_off()
        return super().mouseReleaseEvent(event)

    def pan_off(self):
        self._panning = False
        self._pan_point = None

    def escape(self):
        self.dimmer.finished.connect(self.close)
        self.dimmer.undim()

    def resizeEvent(self, event):
        super(Shoppy, self).resizeEvent(event)
        self.fitInView(self.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def _setup_ui(self):
        self.setWindowTitle(NAME)
        self.setMouseTracking(True)
        screen = QtGui.QGuiApplication.primaryScreen()
        geo = screen.geometry()

        scene = QtWidgets.QGraphicsScene(0, 0, geo.width(), geo.height())
        self.setScene(scene)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.BoundingRectViewportUpdate)
        self.setCacheMode(QtWidgets.QGraphicsView.CacheBackground)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)

        # I wonder if this magic formula is the key to all desktops :|
        self.setGeometry(QtCore.QRect(-3, -6, geo.width() + 6, geo.height() + 12))
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        return screen

    def _build_toolbox(self):
        self.toolbox = ToolBox(self)
        self.toolbox.close_requested.connect(self.escape)
        self.toolbox.save.connect(self.save_shot)
        self.toolbox.clip.connect(self.clip)
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

        self.dimmer.flash()
        cutout = self.original_pixmap.copy(self._dragtangle)
        cutout.save(file_path)
        self.settings.last_save_path = os.path.dirname(file_path)
        self._save_rect()

    def clip(self):
        self.dimmer.flash()
        cutout = self.original_pixmap.copy(self._dragtangle)
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
            del self.settings.last_rectangles[self.settings.max_rectangles :]
        self.settings._save()

    def _drag_last_tangle(self):
        if self.settings.last_rectangles:
            self._dragtangle.setRect(*self.settings.last_rectangles[-1])
            self.dimmer.cutout(self._dragtangle)


class Dimmer(QtCore.QObject):
    finished = QtCore.Signal()

    def __init__(self, parent):
        super(Dimmer, self).__init__(parent)

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

    def cutout(self, rect: QtCore.QRect):
        rect = rect.normalized()
        gw, gh = self.geo.width(), self.geo.height()
        rw, rh = rect.width(), rect.height()
        self.r1.setRect(0, 0, gw, rect.y())
        self.r2.setRect(0, rect.y(), rect.x(), rh)
        self.r3.setRect(rect.x() + rw, rect.y(), gw - rw - rect.x(), rh)
        self.r4.setRect(0, rh + rect.y(), gw, gh - rh - rect.y())
        self.rx.setRect(rect)

    def _set_outer(self):
        self.rects = (self.r1, self.r2, self.r3, self.r4)
        self.color = QtGui.QColor(QtCore.Qt.black)

    def dim(self):
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
        self.color.setAlpha(new_value)
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

    def __init__(self, parent):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        _TbBtn(self, img.save, self.save.emit)
        _TbBtn(self, img.clipboard, self.clip.emit)
        self.mode_button = _TbBtn(self, img.camera, self.toggle_mode)
        self.settings_btn = _TbBtn(self, img.settings)
        _TbBtn(self, img.x, self.x)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self._mode = MODE_CAM
        self.show()

    def showEvent(self, event):
        toolgeo = self.geometry()
        toolgeo.moveCenter(self.parent().geometry().center())
        toolgeo.moveTop(0)
        self.setGeometry(toolgeo)
        return super().showEvent(event)

    def toggle_mode(self):
        if self._mode == MODE_CAM:
            self._mode = MODE_VID
            self.mode_button.setIcon(img.video)
        else:
            self._mode = MODE_CAM
            self.mode_button.setIcon(img.camera)
        self.mode_switched.emit(self._mode)

    def x(self):
        self.close_requested.emit()
        self.hide()


class _TbBtn(QtWidgets.QToolButton):
    def __init__(self, parent, icon, func=None):
        super().__init__(parent)
        if func is None:
            self.setEnabled(False)
        else:
            self.clicked.connect(func)
        self.setIcon(icon)
        self.setAutoRaise(True)
        self.setIconSize(QtCore.QSize(48, 48))
        parent.layout().addWidget(self)


class Settings(QtCore.QObject):
    loaded = QtCore.Signal()

    def __init__(self):
        super(Settings, self).__init__()
        self.last_save_path = ''
        self.last_rectangles = []
        self.max_rectangles = 12

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
            if not isinstance(value, (str, int, list)):
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


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    view = Shoppy()
    view.show()
    app.exec_()
