import os
from pyside import QtCore


class VideoMan(QtCore.QObject):
    video_found = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.path = ''
        QtCore.QTimer(self).singleShot(500, self._find_ffmpeg)

    def _find_ffmpeg(self):
        thread = FFMPegFinder(self)
        thread.found.connect(self._ffmpeg_found)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _ffmpeg_found(self, path: str):
        if not os.path.isfile(path):
            return
        self.path = path
        self.video_found.emit()


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