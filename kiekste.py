import os
import logging
import traceback

import common
import image_stub
import video_man
import widgets
import overlay
from pyside import QtCore, QtGui, QtWidgets, QShortcut

LOG_LEVEL = logging.DEBUG
log = logging.getLogger(common.NAME)
log.setLevel(LOG_LEVEL)
MODE_CAM = 'Image'
MODE_VID = 'Video'

IMG = image_stub.IMG
SETTINGS = common.SETTINGS


cursor_keys = {'Left': (-1, 0), 'Up': (0, -1), 'Right': (1, 0), 'Down': (0, 1)}


class Kiekste(QtWidgets.QGraphicsView):
    def __init__(self):
        super().__init__()
        self.paint_layer = PaintLayer(self)

        self._setup_ui()
        self._cursor_pos = None

        self.overlay = overlay.Overlay(self)
        self.overlay.cursor_change.connect(self.set_cursor)

        self.toolbox = None  # type: None | ToolBox
        self.videoman = video_man.VideoMan(self)
        self.videoman.video_found.connect(self._found_video_tool)

        QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self, self.escape)
        for seq in QtCore.Qt.Key_S, QtCore.Qt.CTRL + QtCore.Qt.Key_S:
            QShortcut(QtGui.QKeySequence(seq), self, self.save_shot)
        for seq in QtCore.Qt.Key_C, QtCore.Qt.CTRL + QtCore.Qt.Key_C:
            QShortcut(QtGui.QKeySequence(seq), self, self.clip)

        for seq in (QtCore.Qt.ALT + QtCore.Qt.Key_V,):
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

        if SETTINGS.draw_pointer:
            self.paint_layer.toggle(True)
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
            if self.paint_layer.has_item_under_mouse():
                pass
            else:
                self.overlay.mouse_press(True)
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self.paint_layer.has_item_under_mouse():
            self.set_cursor(QtCore.Qt.ArrowCursor)
            return
        self.overlay.cursor_move(QtCore.QPointF(event.pos()))
        return super().mouseMoveEvent(event)

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
        import time
        x = 7
        d = 0.2
        for i in range(1, x + 1):
            self.setWindowOpacity(1 - ((1/x) * i))
            time.sleep(d / x)
        self.close()

    def set_screenshot(self):
        screen = QtGui.QGuiApplication.primaryScreen()
        geo = screen.geometry()
        self._cursor_pos = self.cursor().pos()
        self.pixmap = screen.grabWindow(0)
        self.setBackgroundBrush(QtGui.QBrush(self.pixmap))
        self.paint_layer.set_cursor_pos(self._cursor_pos)
        return screen, geo

    def _setup_ui(self):
        self.setWindowTitle(common.NAME)
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
            # QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
            QtCore.Qt.Window
            | QtCore.Qt.FramelessWindowHint
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
            self,
            common.NAME + ' Save Screenshot',
            SETTINGS.last_save_path or common.PATH,
            'PNG (*.png)',
        )
        if not file_path:
            return

        self.overlay.flash()
        cutout = self.pixmap.copy(rect)
        cutout.save(file_path)
        SETTINGS.last_save_path = os.path.dirname(file_path)
        self._save_rect()

    def clip(self):
        rect = self.overlay.rect
        if not rect:
            return
        cutout = self.pixmap.copy(rect)
        if SETTINGS.draw_pointer:
            painter = QtGui.QPainter()
            painter.begin(cutout)
            trg_rect = QtCore.QRectF(0,0,rect.width(), rect.height())
            self.scene().render(painter, trg_rect, rect)
            painter.end()

        self.overlay.flash()
        QtWidgets.QApplication.clipboard().setPixmap(cutout)

        self._save_rect()

    def _save_rect(self):
        rect_list = list(self.overlay.rect.getRect())
        if rect_list in SETTINGS.last_rectangles:
            if SETTINGS.last_rectangles[-1] == rect_list:
                return
            SETTINGS.last_rectangles.remove(rect_list)
        SETTINGS.last_rectangles.append(rect_list)
        if len(SETTINGS.last_rectangles) > SETTINGS.max_rectangles:
            del SETTINGS.last_rectangles[: -SETTINGS.max_rectangles]
        SETTINGS._save()

    def _draw_last_tangle(self):
        if SETTINGS.last_rectangles:
            rect = QtCore.QRect(*SETTINGS.last_rectangles[-1])
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
        SETTINGS.draw_pointer = state
        SETTINGS._save()
        self.paint_layer.toggle(state)

    def video_capture(self):
        if not self.videoman.capturing:
            self._save_rect()
            self.overlay.undim()
            self.video_widget = video_man.VideoWidget(self, self.videoman)
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


class PaintLayer(QtCore.QObject):
    item_under_cursor = QtCore.Signal()

    def __init__(self, parent: Kiekste):
        super().__init__(parent)
        self._parent = parent
        self._cursor_pos = QtCore.QPointF()

        self.items = []  # type: list[QtWidgets.QGraphicsItem]
        self.pointer = None

    def set_cursor_pos(self, cursor_pos):
        # type: (QtCore.QPointF | QtCore.QPoint) -> None
        self._cursor_pos = cursor_pos

    def has_item_under_mouse(self):
        for item in self.items:
            if item.isUnderMouse():
                return True
        return False

    def toggle(self, state):
        scene = self._parent.scene()
        if state and self.pointer is None and SETTINGS.draw_pointer:
            self.pointer = QtWidgets.QGraphicsPixmapItem(IMG.pointer_black.pixmap(64))
            self.pointer.setPos(self._cursor_pos)
            scene.addItem(self.pointer)
            self.pointer.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
            # self.pointer.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
            # self.pointer.setZValue(1000)
            self.items.append(self.pointer)

        for item in self.items:
            item.setVisible(state)


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
        if SETTINGS.draw_pointer:
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
        last_rects = SETTINGS.last_rectangles
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
        if SETTINGS.draw_pointer:
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


def show():
    app = QtWidgets.QApplication([])
    win = Kiekste()
    win.show()
    app.exec_()


if __name__ == '__main__':
    try:
        common.setup_logger()
        show()
    except BaseException:
        error_msg = traceback.format_exc().strip()
        print(error_msg)
        with open(os.path.join(common.TMP_PATH, '_startup_error.log'), 'w') as fobj:
            fobj.write(error_msg)
