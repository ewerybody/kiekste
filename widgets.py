from pyside import QtWidgets, QtCore


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
        self.setButtonSymbols(self.ButtonSymbols.NoButtons)
        self.setStyleSheet(
            'QSpinBox {'
            'border: 0; border-radius: 5px; font-size: 24px;'
            'background: transparent; color: grey;'
            '}'
            'QSpinBox:hover {background: white; color: black}'
        )

    def leaveEvent(self, event: QtCore.QEvent):
        self.setButtonSymbols(self.ButtonSymbols.NoButtons)
        return super().leaveEvent(event)

    def enterEvent(self, event: QtCore.QEvent):
        self.setButtonSymbols(self.ButtonSymbols.UpDownArrows)
        return super().leaveEvent(event)
