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
SERIES_PATH = "series/"

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
S_COUNTDOWN = 'countdown'
S_COUNTDOWN_MULTI = 'countdown_multi'
S_DISPLAY = 'displayImage'

M_SINGLE = 's'
M_MULTI = 'm'


def getFilePath(pictureMode, seriesFolder = "", composedImage = False):
    """ Generate a file name for the picture. """
    currentTimeString = time.strftime("%Y-%m-%d_%H-%M-%S")
    basename = currentTimeString
    if pictureMode == M_SINGLE:
        suffix = "_single"
    elif pictureMode == M_MULTI:
        if not composedImage:
            suffix = "_partial"
        else:
            suffix = "_series"
            basename = seriesFolder
    extension = ".jpg"
    filename = basename + suffix + extension

    if pictureMode == M_MULTI and not composedImage:
        filepath = SERIES_PATH + seriesFolder + '/' + filename
    else:
        filepath = PICTURE_PATH + filename

    return filepath


def getSeriesFolder():
    """ Generate a folder name for the picture series. """
    currentTimeString = time.strftime("%Y-%m-%d_%H-%M-%S")
    seriesPath = SERIES_PATH + currentTimeString
    if not os.path.exists(seriesPath):
        os.makedirs(seriesPath)
    return currentTimeString


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
        self.initObjects()

        # display the latest pictures
        self.updatePictureList()

        # init the webcam
        self.liveViewSize = QSize(WEBCAM_WIDTH_PX, WEBCAM_HEIGHT_PX)
        self.setupWebcam()

        # quit shortcut & button
        quit_action = QAction('Quit', self)
        quit_action.setShortcuts(['Ctrl+Q', 'Ctrl+W'])
        quit_action.triggered.connect(qApp.closeAllWindows)
        self.addAction(quit_action)

        # toggle mode
        self.ui.pushButton_switchMode.clicked.connect(self.toggleMode)

        # take an image
        self.ui.pushButton_main.clicked.connect(self.startMainAction)
        # self.ui.pushButton_capture.clicked.connect(self.startPictureProcess)

        # select an image
        self.ui.listWidget_lastPictures.itemSelectionChanged.connect(self.displayImage)

        # print the selected image
        # self.ui.pushButton_print.clicked.connect(self.printSelectedImage)


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
            'countdown': [
                "Laecheln!",
                "Foto in 3, 2, 1, ...",
                "Foto in 3, 2, ...",
                "Foto in 3, ..."
            ]
        }
        self.modeTitle = { 's': "Einzelbild", 'm': "Bilderserie" }
        self.modeIcon = {
            's': QPixmap(":/icon/graphics/picture_single.png"),
            'm': QPixmap(":/icon/graphics/picture_multi.png")
        }
        self.ui.currentState = S_LIVEVIEW
        self.ui.currentMode = M_SINGLE
        self.multiShotFolder = ""

        self.countDownTimer = QTimer()
        self.countDownTimer.timeout.connect(self.shotCountDown)
        self.countDownTimer.setInterval(1000)

        self.printerPDF = QPrinter()
        self.printerPDF.setOrientation(QPrinter.Portrait)
        self.printerPDF.setPaperSize(self.printDim.getPageSize(), self.printDim.getPageSizeUnit())
        self.printerPDF.setFullPage(True)
        self.printerPDF.setOutputFormat(QPrinter.PdfFormat)

        self.adjustMainButton()


    def toggleMode(self):
        """ Toggle the mode between single and multiple photos """
        # switch mode
        if self.ui.currentMode == M_SINGLE:
            self.ui.currentMode = M_MULTI
        else:
            self.multiShotFolder = ""
            self.ui.currentMode = M_SINGLE

        # update the UI
        self.ui.label_captureMode.setText(self.modeTitle[self.ui.currentMode])
        self.ui.label_captureModeIcon.setPixmap(self.modeIcon[self.ui.currentMode])


    def setupWebcam(self):
        """ Initialize webcam camera and get regular pictures """
        self.capture = cv2.VideoCapture(0)
        # self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_WIDTH, self.liveViewSize.width())
        # self.capture.set(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT, self.liveViewSize.height())

        self.ui.label_title.setText(self.title['liveview'])

        self.camRefresh = QTimer()
        self.camRefresh.timeout.connect(self.displayWebcamStream)
        self.camRefresh.setInterval(50)
        self.camRefresh.start()


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
        # self.ui.pushButton_print.setEnabled(False)


    def adjustMainButton(self):
        """ Depending on the current state, modify the main button. """
        icon = QIcon()
        if self.ui.currentState == S_LIVEVIEW:
            self.ui.pushButton_main.setText("Foto!")
            icon.addPixmap(QPixmap(":/icon/graphics/camera.png"), QIcon.Normal, QIcon.Off)
            self.ui.pushButton_main.setIcon(icon)
        elif self.ui.currentState == S_DISPLAY:
            self.ui.pushButton_main.setText("Drucken")
            icon.addPixmap(QPixmap(":/icon/graphics/printer.png"), QIcon.Normal, QIcon.Off)
            self.ui.pushButton_main.setIcon(icon)


    def startMainAction(self):
        """ Depending on the current state, take a picture or print. """
        if self.ui.currentState == S_LIVEVIEW:
            self.startPictureProcess()
        elif self.ui.currentState == S_DISPLAY:
            self.printSelectedImage()


    def takeImage(self):
        """ Read frame from camera and repaint QLabel widget. """
        # first, block the webcam stream for a while
        self.camRefresh.stop()

        # now take a picture
        filePath = getFilePath(self.ui.currentMode, self.multiShotFolder)
        frame = self.captureFrame()
        frame = cv2.flip(frame, 1)
        cv2.imwrite(filePath, frame)

        # things required for multiple shots
        if self.ui.currentMode == M_MULTI:
            self.multiShotCount = self.multiShotCount + 1

            # not finished yet, repeat
            if self.multiShotCount < 4:
                self.displayImage(filePath)

                self.countDownValue = 2
                self.shotCountDown()
                self.countDownTimer.start()
            else:
                self.buildMultiShotImage()

        # update picture list and select the most recent one
        if not (self.ui.currentMode == M_MULTI and self.multiShotCount < 4):
            self.ui.pushButton_main.setEnabled(True)
            self.updatePictureList()
            self.ui.listWidget_lastPictures.setCurrentRow(1)
            self.displayImage()


    def startPictureProcess(self):
        """ Starts the process taking pichture(s) depending on the set mode. """
        self.ui.pushButton_main.setEnabled(False)

        # prepare the picture series
        if self.ui.currentMode == M_MULTI:
            self.multiShotCount = 0
            self.multiShotFolder = getSeriesFolder()

        self.countDownValue = 3
        self.shotCountDown()
        self.countDownTimer.start()


    def shotCountDown(self):
        newTitle = self.title['countdown'][self.countDownValue]
        self.ui.label_title.setText(newTitle)

        if self.countDownValue > 0:
            self.countDownValue = self.countDownValue - 1
        else:
            self.countDownTimer.stop()
            QTimer.singleShot(500, self.takeImage)


    def buildMultiShotImage(self):
        """ Combine the 4 taken images into one single picture. """

        # get a sorted list of files
        seriesPath = SERIES_PATH + self.multiShotFolder + '/'
        pictureFiles = filter(os.path.isfile, glob.glob(seriesPath + "*.jpg"))
        pictureFiles.sort(key=lambda x: os.path.getctime(x))

        # create the base of the image
        pictureSize = QImage(pictureFiles[0]).size()
        spacing = pictureSize.height() / 42
        image = QImage(pictureSize.width() + 3*spacing, pictureSize.height() + 3*spacing, QImage.Format_RGB32)
        image.fill(Qt.white)

        # use a QPainter to place the other images inside
        canvas = QPainter()
        canvas.begin(image)

        if len(pictureFiles) > 0:
            target = QRectF(
                spacing, spacing,
                pictureSize.width()/2, pictureSize.height()/2
            )
            canvas.drawImage(target, QImage(pictureFiles[0]))
        if len(pictureFiles) > 1:
            target = QRectF(
                pictureSize.width()/2 + 2*spacing, spacing,
                pictureSize.width()/2, pictureSize.height()/2
            )
            canvas.drawImage(target, QImage(pictureFiles[1]))
        if len(pictureFiles) > 2:
            target = QRectF(
                spacing, pictureSize.height()/2 + 2*spacing,
                pictureSize.width()/2, pictureSize.height()/2
            )
            canvas.drawImage(target, QImage(pictureFiles[2]))
        if len(pictureFiles) > 3:
            target = QRectF(
                pictureSize.width()/2 + 2*spacing, pictureSize.height()/2 + 2*spacing,
                pictureSize.width()/2, pictureSize.height()/2
            )
            canvas.drawImage(target, QImage(pictureFiles[3]))

        canvas.end()
        image.save(getFilePath(M_MULTI, self.multiShotFolder, True), "JPG", 92)


    def updatePictureList(self):
        """ Gets a list of QPixmaps from the latest images. """
        self.pictureList = getPictureList()
        self.pictureList.insert(0, self.liveViewIcon)

        # put the pictures in the list
        self.ui.listWidget_lastPictures.clear()
        for p in self.pictureList:
            newItem = QListWidgetItem(p['pic'], p['title'], self.ui.listWidget_lastPictures)


    def displayImage(self, filePath = ""):
        """ Get the currently selected image and display it. """
        selectedImageID = self.ui.listWidget_lastPictures.currentRow()
        if selectedImageID > 0 or filePath != "":
            # first, stop the live feed
            self.camRefresh.stop()

            # load the image and display it
            # (Note: It scales the image only once when it loads it.
            #        Resizing the window after that doesn't change scaling.)
            if filePath == "":
                selectedImage = self.pictureList[selectedImageID]
                selectedImagePixmap = QPixmap(selectedImage['path'])
                self.ui.label_title.setText(self.title['display'].format(selectedImage['title']))
            else:
                selectedImagePixmap = QPixmap(filePath)

            self.ui.currentState = S_DISPLAY
            selectedImagePixmap = self.scaleImageToLabel(selectedImagePixmap)
            self.ui.label_pictureView.setPixmap(selectedImagePixmap)
        else:
            # reactivate the live feed
            self.ui.label_title.setText(self.title['liveview'])
            self.ui.currentState = S_LIVEVIEW
            self.camRefresh.start()
        self.adjustMainButton()


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
