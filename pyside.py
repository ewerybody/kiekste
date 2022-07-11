import sys
from PySide6 import QtCore, QtGui, QtWidgets

import common

# patch PySide2 to work like 6
if QtCore.__version_info__[0] == 5:
    QtGui.QShortcut = QtWidgets.QShortcut

log = common.get_logger('pyside')
_py_ver = '.'.join(str(i) for i in sys.version_info[:3])
log.info(f'{common.NAME} running on: Python {_py_ver} and Qt for Python: {QtCore.__version__}')
