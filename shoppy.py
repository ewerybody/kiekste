import os
import time
from PySide2 import QtCore, QtGui, QtWidgets


NAME = 'Shoppy'
DIM_OPACITY = 150
DIM_DURATION = 200
DIM_INTERVAL = 20
PATH = os.path.abspath(os.path.dirname(__file__))


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

        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self, self.escape)
        for seq in QtCore.Qt.Key_S, QtCore.Qt.CTRL + QtCore.Qt.Key_S:
            QtWidgets.QShortcut(QtGui.QKeySequence(seq), self, self.save_shot)

        self.toolbox = None
        QtCore.QTimer(self).singleShot(500, self._build_toolbox)

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
        self.activateWindow()

    def set_cursor(self, shape: QtCore.Qt.CursorShape):
        cursor = self.cursor()
        cursor.setShape(shape)
        self.setCursor(cursor)

    def save_shot(self):
        if not self._dragtangle:
            return

        file_path, file_type = QtWidgets.QFileDialog.getSaveFileName(
            self, NAME + ' Save Screenshot', PATH, 'PNG (*.png)')
        if not file_path:
            return

        cutout = self.original_pixmap.copy(self._dragtangle)
        cutout.save(file_path)


class Dimmer(QtCore.QObject):
    finished = QtCore.Signal()

    def __init__(self, parent):
        super(Dimmer, self).__init__(parent)

        self.geo = parent.geometry()
        self.r1 = QtWidgets.QGraphicsRectItem()
        self.r2 = QtWidgets.QGraphicsRectItem()
        self.r3 = QtWidgets.QGraphicsRectItem()
        self.r4 = QtWidgets.QGraphicsRectItem()
        self.rects = (self.r1, self.r2, self.r3, self.r4)

        self.color = QtGui.QColor()
        self.color.setAlpha(0)
        scene = parent.scene()

        for r in self.rects:
            scene.addItem(r)
            # self.rect.setRect()
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

        self.dim()
        self.cutout(QtCore.QRect(0, 0, 0, 0))

    def cutout(self, rect: QtCore.QRect):
        rect = rect.normalized()
        gw, gh = self.geo.width(), self.geo.height()
        rw, rh = rect.width(), rect.height()
        self.r1.setRect(0, 0, gw, rect.y())
        self.r2.setRect(0, rect.y(), rect.x(), rh)
        self.r3.setRect(rect.x() + rw, rect.y(), gw - rw - rect.x(), rh)
        self.r4.setRect(0, rh + rect.y(), gw, gh - rh - rect.y())
        self.rx.setRect(rect)

    def dim(self):
        self._ticks = DIM_DURATION / DIM_INTERVAL
        self._delta = DIM_OPACITY / self._ticks
        self._timer.start()

    def undim(self):
        self._ticks = DIM_DURATION / DIM_INTERVAL
        self._delta = -self.color.alpha() / self._ticks
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


class ToolBox(QtWidgets.QWidget):
    close_requested = QtCore.Signal()

    def __init__(self, parent):
        super(ToolBox, self).__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        button = QtWidgets.QToolButton()
        x_button = QtWidgets.QToolButton()
        x_button.clicked.connect(self.x)
        layout.addWidget(button)
        layout.addWidget(x_button)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)

        toolgeo = self.geometry()
        toolgeo.moveCenter(parent.geometry().center())
        toolgeo.moveTop(0)
        self.setGeometry(toolgeo)
        self.show()

    def x(self):
        self.close_requested.emit()
        self.hide()


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    view = Shoppy()
    view.show()
    app.exec_()
