#!/usr/bin/env python

# pyPhotoBooth - Python tool to take pictures and print them
# http://github.com/Nepomuk/pyPhotoBooth

# general libraries
import sys, os
import subprocess32 as subprocess
import glob
import time

# used for the webcam
import numpy as np
import cv, cv2

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
        self.width = 148
        self.height = 100

    def getRatio(self):
        return float(self.width) / self.height

    def getPageSize(self):
        return QSizeF(self.width, self.height)

    def getPageSizeUnit(self):
        return QPrinter.Millimeter


WEBCAM_WIDTH_PX = 740
WEBCAM_HEIGHT_PX = 500

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
        self.ui.pushButton_capture.clicked.connect(self.takeImage)

        # select an image
        self.ui.listWidget_lastPictures.itemSelectionChanged.connect(self.displayImage)

        # print the selected image
        self.ui.pushButton_print.clicked.connect(self.printSelectedImage)


    def initObjects(self):
        self.printDim = Dimensions()
        self.liveViewIcon = {
            "title": "",
            "pic":   QIcon("graphics/liveview.png"),
            "path":  "graphics/liveview.png"
        }
        self.title = {
            'liveview':     "Vorschau",
            'display':      "Bild von {0}",
            'countdown1':   "Foto in 3, ...",
            'countdown2':   "Foto in 3, 2, ...",
            'countdown3':   "Foto in 3, 2, 1, ...",
            'countdown4':   "Laecheln!",
        }

        self.printerPDF = QPrinter()
        self.printerPDF.setOrientation(QPrinter.Portrait)
        self.printerPDF.setPaperSize(self.printDim.getPageSize(), self.printDim.getPageSizeUnit())
        self.printerPDF.setFullPage(True)
        self.printerPDF.setOutputFormat(QPrinter.PdfFormat)


    def setupWebcam(self):
        """ Initialize webcam camera and get regular pictures """
        self.capture = cv2.VideoCapture(0)
        # self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_WIDTH, self.liveViewSize.width())
        # self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT, self.liveViewSize.height())

        self.camRefresh = QTimer()
        self.camRefresh.timeout.connect(self.displayWebcamStream)
        self.camRefresh.start(self.refreshTimout)


    def captureFrame(self):
        _, frame = self.capture.read()

        # get the current ratio
        frameSize = cv.GetSize(cv.fromarray(frame))
        frameRatio = float(frameSize[0]) / frameSize[1]

        # which direction should be cut?
        if frameRatio > self.printDim.getRatio():
            # image is wider than it should be, keep height
            newWidth = self.printDim.getRatio() * frameSize[1]
            cutWidth = ( frameSize[0] - newWidth ) / 2
            newFrame = frame[0:frameSize[1], cutWidth:(cutWidth+newWidth)]
        else:
            # image is higher than it should be, keep width
            newHeigth = float(frameSize[0]) / self.printDim.getRatio()
            cutHeigth = ( frameSize[1] - newHeigth ) / 2
            newFrame = frame[cutHeigth:(cutHeigth+newHeigth), 0:frameSize[0]]

        return newFrame


    def scaleImageToLabel(self, pixmap):
        """ Scale the image to the label's area. """
        labelWidth = self.ui.label_pictureView.width()
        labelHeight = self.ui.label_pictureView.height()
        return pixmap.scaled(labelWidth, labelHeight, Qt.KeepAspectRatio)


    def displayWebcamStream(self):
        """ Read frame from camera and repaint QLabel widget. """
        frame = self.captureFrame()

        # apply some corrections to the live feed
        frame = cv2.cvtColor(frame, cv2.cv.CV_BGR2RGB)
        frame = cv2.flip(frame, 1)
        image = QImage(frame, frame.shape[1], frame.shape[0],
                       frame.strides[0], QImage.Format_RGB888)

        # scale the image down if necessary
        pixmap = self.scaleImageToLabel(QPixmap.fromImage(image))

        # set image and labels
        self.ui.label_pictureView.setPixmap(pixmap)
        self.ui.label_title.setText(self.title['liveview'])
        self.ui.pushButton_print.setEnabled(False)


    def takeImage(self):
        """ Read frame from camera and repaint QLabel widget. """
        # first, block the webcam stream for a while
        self.camRefresh.stop()
        self.ui.label_title.setText(self.title['countdown4'])

        # now take a picture
        frame = self.captureFrame()
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
            # first, stop the live feed
            self.camRefresh.stop()
            self.ui.pushButton_print.setEnabled(True)

            # load the image and display it
            # (Note: It scales the image only once when it loads it.
            #        Resizing the window after that doesn't change scaling.)
            selectedImage = self.pictureList[selectedImageID]
            selectedImagePixmap = QPixmap(selectedImage['path'])
            selectedImagePixmap = self.scaleImageToLabel(selectedImagePixmap)
            self.ui.label_pictureView.setPixmap(selectedImagePixmap)
            self.ui.label_title.setText(self.title['display'].format(selectedImage['title']))
        else:
            # reactivate the live feed
            if not self.camRefresh.isActive():
                self.camRefresh.start(self.refreshTimout)


    def printSelectedImage(self):
        """ Get the currently selected image and print it. """
        selectedImageID = self.ui.listWidget_lastPictures.currentRow()
        if selectedImageID > 0:
            selectedImage = self.pictureList[selectedImageID]
            self.printImage(selectedImage)


    def printImage(self, image):
        """ Print a page with a single image. """

        # first, write the image to a PDF, just in case
        self.printToPDF(image)

        # open the dialog
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if ( dialog.exec_() != QDialog.Accepted ):
            return

        # start the painting process
        canvas = QPainter()
        canvas.begin(printer)

        # fill the image
        target = QRectF(0.0, 0.0, canvas.device().width(), canvas.device().height())
        canvas.drawImage(target, QImage(image['path']))

        # finish the job (i.e.: print)
        canvas.end()


    def printToPDF(self, image):
        """ Generate a PDF with a single image. """
        # create the PDF
        pdfPath = PRINTS_PATH + image['base'] + ".pdf"
        self.printerPDF.setOutputFileName(pdfPath)

        # start the painting process
        canvas = QPainter()
        canvas.begin(self.printerPDF)

        # fill the image
        target = QRectF(0.0, 0.0, canvas.device().width(), canvas.device().height())
        canvas.drawImage(target, QImage(image['path']))

        # finish the job (i.e.: print)
        canvas.end()
        return pdfPath


if __name__ == "__main__":
    # the GUI
    app = QApplication([])
    myGui = BoothUI()
    myGui.show()
    myGui.raise_()
    sys.exit(app.exec_())
