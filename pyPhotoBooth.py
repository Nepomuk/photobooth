#!/usr/bin/env python

# pyPhotoBooth - Python tool to take pictures and print them
# http://github.com/Nepomuk/pyPhotoBooth

import sys

import numpy as np
import cv2

from PyQt4 import QtGui, QtCore
from photoBoothUI import Ui_photoBooth


class BoothUI(QtGui.QWidget):
    def __init__(self, parent=None):
        """Initialize QWidget"""
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_photoBooth()
        self.ui.setupUi(self)

        # init the webcam
        self.video_size = QtCore.QSize(711, 400)
        self.setupCamera()

        # quit shortcut & button
        quit_action = QtGui.QAction('Quit', self)
        quit_action.setShortcuts(['Ctrl+Q', 'Ctrl+W'])
        quit_action.triggered.connect(QtGui.qApp.closeAllWindows)
        self.addAction(quit_action)


    def setupCamera(self):
        """ Initialize camera """
        self.capture = cv2.VideoCapture(0)
        self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_WIDTH, self.video_size.width())
        self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT, self.video_size.height())

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.displayVideoStream)
        self.timer.start(50)

    def displayVideoStream(self):
        """ Read frame from camera and repaint QLabel widget. """
        _, frame = self.capture.read()
        frame = cv2.cvtColor(frame, cv2.cv.CV_BGR2RGB)
        frame = cv2.flip(frame, 1)
        image = QtGui.QImage(frame, frame.shape[1], frame.shape[0],
                       frame.strides[0], QtGui.QImage.Format_RGB888)
        self.ui.label_pictureView.setPixmap(QtGui.QPixmap.fromImage(image))


if __name__ == "__main__":
    # gp.check_result(gp.use_python_logging())
    app = QtGui.QApplication([])
    myGui = BoothUI()
    myGui.show()
    myGui.raise_()
    sys.exit(app.exec_())
