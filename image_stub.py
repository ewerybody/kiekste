import os
import logging
from pyside import QtGui

LOG_LEVEL = logging.DEBUG
log = logging.getLogger(__name__)
log.setLevel(LOG_LEVEL)
IMG_PATH = os.path.join(__file__, '..', 'img')


class ImageStub:
    """
    Load-only-once image library object.

    * For convenience: this already lists all usable icons and
    * for speed it just loads them up when actually needed.
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
        self.pointer_black = self._blank
        self.pointer_white = self._blank
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
        obj = None
        try:
            obj = super().__getattribute__(name)
        except AttributeError:
            if not name.startswith('__'):
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


IMG = ImageStub()
