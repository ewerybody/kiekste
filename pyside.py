from PySide2 import QtCore, QtGui, QtWidgets

# patch PySide2 to work like 6
if QtCore.__version_info__[0] == 5:
    QtGui.QShortcut = QtWidgets.QShortcut
