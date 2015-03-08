#!/usr/bin/env python

# pyPhotoBooth - Python tool to take pictures and print them
# http://github.com/Nepomuk/pyPhotoBooth

# general libraries
import sys, os
import glob
import time

# printing
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

# used for the webcam
import numpy as np
import cv2

# the UI
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from photoBoothUI import Ui_photoBooth


# paths to generated files
PICTURE_PATH = "pictures/"
PRINTS_PATH = "prints/"

# dimensions
class Dimensions():
    def __init__(self, parent=None):
        self.width_raw = 148
        self.height_raw = 100
        self.width = self.width_raw * mm
        self.height = self.height_raw * mm

    def getRatio(self):
        return self.width_raw / self.height_raw

    def getPageSize(self):
        return (self.width, self.height)


WEBCAM_WIDTH_PX = 700
WEBCAM_HEIGHT_PX = 400

# some states the UI can be in
S_LIVEVIEW = 'liveView'
S_DISPLAY = 'displayImage'


def getFileName(singlePicture = True):
    """ Generate a file name for the picture. """
    currentTimeString = time.strftime("%Y-%m-%d_%H-%M-%S")
    basename = currentTimeString + "_" + ("single" if singlePicture else "series")
    extension = ".jpg"
    return PICTURE_PATH + basename + extension


def getPictureList():
    # get a sorted list of files
    pictureFiles = filter(os.path.isfile, glob.glob(PICTURE_PATH + "*.jpg"))
    pictureFiles.sort(key=lambda x: os.path.getctime(x))
    pictureFiles.reverse()

    # go through the filenames and create QIcons
    pictures = []
    for f in pictureFiles:
        timeInfo = time.strftime( "%H:%M:%S", time.localtime(os.path.getctime(f)) )
        pictures.append({
            "title": timeInfo,
            "pic":   QIcon(f),
            "path":  f,
            "base":  os.path.splitext( os.path.basename(f) )[0]
        })
    return pictures


class BoothUI(QWidget):
    def __init__(self, parent=None):
        """Initialize QWidget"""
        QWidget.__init__(self, parent)
        self.ui = Ui_photoBooth()
        self.ui.setupUi(self)
        self.ui.currentState = S_LIVEVIEW
        self.initObjects()

        # display the latest pictures
        self.updatePictureList()

        # init the webcam
        self.liveViewSize = QSize(WEBCAM_WIDTH_PX, WEBCAM_HEIGHT_PX)
        self.refreshTimout = 50
        self.setupWebcam()

        # quit shortcut & button
        quit_action = QAction('Quit', self)
        quit_action.setShortcuts(['Ctrl+Q', 'Ctrl+W'])
        quit_action.triggered.connect(qApp.closeAllWindows)
        self.addAction(quit_action)

        # take an image
        self.ui.pushButton_capture.clicked.connect(self.captureImage)

        # select an image
        self.ui.listWidget_lastPictures.itemSelectionChanged.connect(self.displayImage)

        # print the selected image
        self.ui.pushButton_print.clicked.connect(self.printImage)


    def initObjects(self):
        self.printDim = Dimensions()
        self.liveViewIcon = {
            "title": "",
            "pic":   QIcon("liveview.png"),
            "path":  "liveview.png"
        }
        self.title = {
            'liveview':     "Vorschau",
            'display':      "Bild von {0}",
            'countdown1':   "Foto in 3, ...",
            'countdown2':   "Foto in 3, 2, ...",
            'countdown3':   "Foto in 3, 2, 1, ...",
            'countdown4':   "Laecheln!",
        }


    def setupWebcam(self):
        """ Initialize webcam camera and get regular pictures """
        self.capture = cv2.VideoCapture(0)
        self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_WIDTH, self.liveViewSize.width())
        self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT, self.liveViewSize.height())

        self.camRefresh = QTimer()
        self.camRefresh.timeout.connect(self.displayWebcamStream)
        self.camRefresh.start(self.refreshTimout)


    def displayWebcamStream(self):
        """ Read frame from camera and repaint QLabel widget. """
        _, frame = self.capture.read()
        frame = cv2.cvtColor(frame, cv2.cv.CV_BGR2RGB)
        frame = cv2.flip(frame, 1)
        image = QImage(frame, frame.shape[1], frame.shape[0],
                       frame.strides[0], QImage.Format_RGB888)
        self.ui.label_pictureView.setPixmap(QPixmap.fromImage(image))
        self.ui.label_title.setText(self.title['liveview'])
        self.ui.pushButton_print.setEnabled(False)


    def captureImage(self):
        """ Read frame from camera and repaint QLabel widget. """
        # first, block the webcam stream for a while
        self.camRefresh.stop()
        self.ui.label_title.setText(self.title['countdown4'])

        # now take a picture
        _, frame = self.capture.read()
        cv2.imwrite(getFileName(), frame)
        # print "Written {0} to disk.".format(getFileName())
        self.updatePictureList()

        # get the live feed running again
        self.camRefresh.start(self.refreshTimout)


    def updatePictureList(self):
        """ Gets a list of QPixmaps from the latest images. """
        self.pictureList = getPictureList()
        self.pictureList.insert(0, self.liveViewIcon)

        # put the pictures in the list
        self.ui.listWidget_lastPictures.clear()
        for p in self.pictureList:
            newItem = QListWidgetItem(p['pic'], p['title'], self.ui.listWidget_lastPictures)


    def displayImage(self):
        """ Get the currently selected image and display it. """
        selectedImageID = self.ui.listWidget_lastPictures.currentRow()
        if selectedImageID > 0:
            selectedImage = self.pictureList[selectedImageID]
            selectedImagePixmap = QPixmap(selectedImage['path'])
            self.camRefresh.stop()
            self.ui.pushButton_print.setEnabled(True)
            self.ui.label_pictureView.setPixmap(selectedImagePixmap)
            self.ui.label_title.setText(self.title['display'].format(selectedImage['title']))
        else:
            if not self.camRefresh.isActive():
                self.camRefresh.start(self.refreshTimout)


    def printImage(self):
        """ Get the currently selected image and print it. """
        selectedImageID = self.ui.listWidget_lastPictures.currentRow()
        if selectedImageID > 0:
            # The idea is the following: create a pdf that is stored in a
            # temporary directory. When this is created, it is sent to the
            # printer via popen2.popen4
            selectedImage = self.pictureList[selectedImageID]
            generatedPDF = generatePDFsingle(selectedImage)


    def generatePDFsingle(self, image):
        """ Generate a PDF with a single image. """
        # create the PDF
        pdfPath = PRINTS_PATH + image['base'] + ".pdf"
        c = canvas.Canvas(pdfPath)
        c.setPageSize(self.printDim.getPageSize())

        # insert the image
        c.drawImage(image['path'], 0, 0, self.printDim.width, self.printDim.height)

        # save everything and return file path
        c.showPage()
        c.save()
        return pdfPath


if __name__ == "__main__":
    # the GUI
    app = QApplication([])
    myGui = BoothUI()
    myGui.show()
    myGui.raise_()
    sys.exit(app.exec_())
