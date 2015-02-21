#!/usr/bin/env python

# pyPhotoBooth - Python tool to take pictures and print them
# http://github.com/Nepomuk/pyPhotoBooth

import sys, os

import numpy as np
import cv2

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from photoBoothUI import Ui_photoBooth


PICTURE_PATH = "pictures/"

def getFileName():
    """ Generate a file name for the picture. """
    basename = "test"   # make this based on timestamps
    extension = ".jpg"
    return PICTURE_PATH + basename + extension


def getLastPictures():
    pictures = {}
    for f in os.listdir(PICTURE_PATH):
        filepath = os.path.join(PICTURE_PATH, f)
        if not os.path.isfile(filepath):
            continue

        picture = QIcon(filepath)
        pictures[f] = picture
    return pictures


class BoothUI(QWidget):
    def __init__(self, parent=None):
        """Initialize QWidget"""
        QWidget.__init__(self, parent)
        self.ui = Ui_photoBooth()
        self.ui.setupUi(self)

        # display the latest pictures
        self.updatePictureList()

        # init the webcam
        self.liveViewSize = QSize(711, 400)
        self.setupWebcam()

        # quit shortcut & button
        quit_action = QAction('Quit', self)
        quit_action.setShortcuts(['Ctrl+Q', 'Ctrl+W'])
        quit_action.triggered.connect(qApp.closeAllWindows)
        self.addAction(quit_action)

        # take an image
        self.ui.pushButton_capture.clicked.connect(self.captureImage)


    def setupWebcam(self):
        """ Initialize webcam camera and get regular pictures """
        self.capture = cv2.VideoCapture(0)
        self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_WIDTH, self.liveViewSize.width())
        self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT, self.liveViewSize.height())

        self.camRefresh = QTimer()
        self.camRefresh.timeout.connect(self.displayWebcamStream)
        self.camRefresh.start(50)


    def displayWebcamStream(self):
        """ Read frame from camera and repaint QLabel widget. """
        _, frame = self.capture.read()
        frame = cv2.cvtColor(frame, cv2.cv.CV_BGR2RGB)
        frame = cv2.flip(frame, 1)
        image = QImage(frame, frame.shape[1], frame.shape[0],
                       frame.strides[0], QImage.Format_RGB888)
        self.ui.label_pictureView.setPixmap(QPixmap.fromImage(image))


    def captureImage(self):
        """ Read frame from camera and repaint QLabel widget. """
        _, frame = self.capture.read()
        cv2.imwrite(getFileName(), frame)
        # print "Written {0} to disk.".format(getFileName())
        self.updatePictureList()


    def updatePictureList(self):
        """ Gets a list of QPixmaps from the latest images. """
        pictures = getLastPictures()
        self.ui.listWidget_lastPictures.clear()
        for p in pictures:
            newItem = QListWidgetItem(pictures[p], p, self.ui.listWidget_lastPictures)




if __name__ == "__main__":
    # the GUI
    app = QApplication([])
    myGui = BoothUI()
    myGui.show()
    myGui.raise_()
    sys.exit(app.exec_())
