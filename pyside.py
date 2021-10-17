from PySide2 import QtCore, QtGui, QtWidgets

try:
    QShortcut = QtWidgets.QShortcut
except AttributeError:
    QShortcut = QtGui.QShortcut
