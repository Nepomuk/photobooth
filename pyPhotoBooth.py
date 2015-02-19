#!/usr/bin/env python

# pyPhotoBooth - Python tool to take pictures and print them
# http://github.com/Nepomuk/pyPhotoBooth

import sys

from PyQt4 import QtGui, QtCore

from photoBoothUI import Ui_photoBooth


class BoothUI(QtGui.QMainWindow):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_photoBooth()
        self.ui.setupUi(self)

        # quit shortcut & button
        quit_action = QtGui.QAction('Quit', self)
        quit_action.setShortcuts(['Ctrl+Q', 'Ctrl+W'])
        quit_action.triggered.connect(QtGui.qApp.closeAllWindows)
        self.addAction(quit_action)
        self.ui.pushButton_quit.clicked.connect(QtGui.qApp.closeAllWindows)


if __name__ == "__main__":
    # gp.check_result(gp.use_python_logging())
    app = QtGui.QApplication([])
    myGui = BoothUI()
    myGui.show()
    sys.exit(app.exec_())
