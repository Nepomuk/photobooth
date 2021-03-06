#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pyPhotoBooth - Python tool to take pictures and print them
# http://github.com/Nepomuk/pyPhotoBooth

# general libraries
import sys, os
import psutil
import glob
import time

# used for the webcam
import numpy as np
import cv, cv2

# used for the camera
sys.path.append('piggyphoto/')
import piggyphoto
import gphoto2 as gp

# the UI
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from photoBoothUI import Ui_photoBooth

# which camera input should be used?
#  auto: use external camera if connected
#  ext: try to force external camera (might crash)
#  webcam: use internal webcam
CAM_MODE = 'auto'

# paths to generated files
DELETED_PATH = "deleted/"
PICTURE_PATH = "pictures/"
PRINTS_PATH = "prints/"
SERIES_PATH = "series/"
THUMBNAIL_PATH = "thumbnails/"

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
S_HIBERNATE = 'hibernate'
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


def createThumbnails(redoAll = False):
    pictureFiles = filter(os.path.isfile, glob.glob(PICTURE_PATH + "*.jpg"))
    for f in pictureFiles:
        thumbnailFile = f.replace(PICTURE_PATH, THUMBNAIL_PATH)
        if ( redoAll or not os.path.isfile(thumbnailFile) ):
            image = QImage(f)
            thumbnail = image.scaledToWidth(200)
            thumbnail.save(thumbnailFile, "JPG", 90)


def getPictureList():
    # get a sorted list of files
    pictureFiles = filter(os.path.isfile, glob.glob(PICTURE_PATH + "*.jpg"))
    pictureFiles.sort(key=lambda x: os.path.getctime(x))
    pictureFiles.reverse()

    # go through the filenames and create QIcons
    pictures = []
    for f in pictureFiles:
        timeInfo = time.strftime( "%H:%M:%S", time.localtime(os.path.getctime(f)) )

        # use the thumbnail if it exists
        thumbnailFile = f.replace(PICTURE_PATH, THUMBNAIL_PATH)
        if not os.path.isfile(thumbnailFile):
            thumbnailFile = f
        thumbnail = QIcon(thumbnailFile)

        pictures.append({
            "title": timeInfo,
            "pic":   thumbnail,
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

        # detect if an external camera has been connected
        global USE_WEBCAM
        if CAM_MODE == 'auto':
            if piggyphoto.CameraList(autodetect=True).count() > 0:
                USE_WEBCAM = False
            else:
                USE_WEBCAM = True
        elif CAM_MODE == 'ext':
            USE_WEBCAM = False
        else:
            USE_WEBCAM = True

        # init the webcam / camera
        if USE_WEBCAM:
            self.setupWebcam()
        else:
            self.setupCamera()

        # quit shortcut & button
        quit_action = QAction('Quit', self)
        quit_action.setShortcuts(['Ctrl+Q', 'Ctrl+W'])
        quit_action.triggered.connect(qApp.closeAllWindows)
        self.addAction(quit_action)

        # toggle mode
        self.ui.pushButton_switchMode.clicked.connect(self.toggleMode)
        scMode = QShortcut(QKeySequence(Qt.Key_M), self, self.toggleMode)

        # take an image
        self.ui.pushButton_main.clicked.connect(self.startMainActionClick)
        scMain = QShortcut(QKeySequence(Qt.Key_Space), self, self.startMainAction)
        scMain2 = QShortcut(QKeySequence(Qt.Key_B), self, self.startMainAction)
        scPrint = QShortcut(QKeySequence(Qt.Key_Return), self, self.printSelectedImage)

        # select an image
        self.ui.listWidget_lastPictures.itemSelectionChanged.connect(self.displayImage)

        # delete an image
        self.ui.pushButton_delete.clicked.connect(self.deleteSelectedImage)
        scDelete = QShortcut(QKeySequence(Qt.Key_L), self, self.deleteSelectedImage)


    def initObjects(self):
        self.printDim = Dimensions()
        self.liveViewIcon = {
            "title": "Neues Foto",
            "pic":   QIcon("graphics/picture_single.png"),
            "path":  "graphics/picture_single.png"
        }
        self.modeTitle = { 's': "Einzelbild", 'm': "Bilderserie" }
        self.modeIcon = {
            's': QPixmap(":/icon/graphics/picture_single.png"),
            'm': QPixmap(":/icon/graphics/picture_multi.png")
        }
        self.ui.currentState = S_LIVEVIEW
        self.ui.currentMode = M_SINGLE
        self.multiShotFolder = ""
        self.multiShotLastImage = ""
        self.countDownOverlayActive = False

        self.countDownTimer = QTimer()
        self.countDownTimer.timeout.connect(self.shotCountDown)
        self.countDownTimer.setInterval(1000)

        self.camHibernate = QTimer()
        self.camHibernate.timeout.connect(self.pauseLiveview)
        self.camHibernate.setInterval(3*60*1000)

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

        createThumbnails()


    def setupWebcam(self):
        """ Initialize webcam camera and get regular pictures """
        self.capture = cv2.VideoCapture(0)

        self.camRefresh = QTimer()
        self.camRefresh.timeout.connect(self.displayWebcamStream)
        self.camRefresh.setInterval(50)
        self.camRefresh.start()

        self.camHibernate.start()


    def setupCamera(self):
        """ Initialize the camera and get regular preview pictures. """
        self.camera = piggyphoto.Camera()
        self.camera.leave_locked()

        self.camRefresh = QTimer()
        self.camRefresh.timeout.connect(self.displayCameraPreview)
        self.camRefresh.setInterval(100)
        self.camRefresh.start()
        self.camHibernate.start()


    def displayCameraPreview(self):
        """ Read frame from camera and repaint QLabel widget. """
        preview = self.camera.capture_preview()

        # load from temporary file
        pixmap = QPixmap()
        pixmap.loadFromData(preview.to_pixbuf(), "JPG")

        # scale the image down if necessary
        pixmap = self.scaleImageToLabel(pixmap)

        # overlay the countdown on the image if activated
        if self.countDownOverlayActive:
            pixmap = self.overlayCountdown(pixmap)

        # set image
        self.ui.label_pictureView.setPixmap(pixmap)

        # free unused memory (not tested if this works)
        preview.clean()


    def captureFrame(self):
        _, frame = self.capture.read()

        # get the current ratio
        frameSize = cv.GetSize(cv.fromarray(frame))
        frameRatio = float(frameSize[0]) / frameSize[1]

        # which direction should be cut?
        if frameRatio > self.printDim.getRatio():
            # image is wider than it should be, keep height
            newWidth = int(self.printDim.getRatio() * frameSize[1])
            cutWidth = int(( frameSize[0] - newWidth ) / 2)
            newFrame = frame[0:frameSize[1], cutWidth:(cutWidth+newWidth)]
        else:
            # image is higher than it should be, keep width
            newHeigth = int(float(frameSize[0]) / self.printDim.getRatio())
            cutHeigth = int(( frameSize[1] - newHeigth ) / 2)
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

        # overlay the countdown on the image if activated
        if self.countDownOverlayActive:
            pixmap = self.overlayCountdown(pixmap)

        # set image
        self.ui.label_pictureView.setPixmap(pixmap)


    def overlayCountdown(self, pixmap):
        canvas = QPainter()
        canvas.begin(pixmap)
        shadowOffset = 2

        counterTitle = "Foto in"
        if self.ui.currentMode == M_MULTI:
            if self.multiShotCount == 1:
                counterTitle = "Noch ein Foto in"
            elif self.multiShotCount == 2:
                counterTitle = "Noch einmal in"
            elif self.multiShotCount == 3:
                counterTitle = "Letztes Foto in"
        counterValue = "{0}".format(self.countDownValue+1)

        # the counter title
        counterTitleRect = pixmap.rect()
        counterTitleRect.setHeight(pixmap.height()/2)
        counterTitleFont = QFont("Helvetica Neue")
        counterTitleFont.setPointSize(100)
        canvas.setFont( counterTitleFont )

        canvas.setPen( Qt.black )
        rect1 = counterTitleRect
        rect1.translate(0,shadowOffset)
        canvas.drawText( rect1, Qt.AlignCenter, counterTitle )

        rect2 = counterTitleRect
        rect2.translate(0,-shadowOffset)
        canvas.drawText( rect2, Qt.AlignCenter, counterTitle )

        rect3 = counterTitleRect
        rect3.translate(shadowOffset,0)
        canvas.drawText( rect3, Qt.AlignCenter, counterTitle )

        rect4 = counterTitleRect
        rect4.translate(-shadowOffset,0)
        canvas.drawText( rect4, Qt.AlignCenter, counterTitle )

        canvas.setPen( Qt.white )
        canvas.drawText( counterTitleRect, Qt.AlignCenter, counterTitle )

        # the counter value
        counterValueFont = QFont("Helvetica Neue")
        counterValueFont.setPointSize(180)
        canvas.setFont( counterValueFont )

        canvas.setPen( Qt.black )
        rect1 = pixmap.rect()
        rect1.translate(0,shadowOffset)
        canvas.drawText( rect1, Qt.AlignCenter, counterValue )

        rect2 = pixmap.rect()
        rect2.translate(0,-shadowOffset)
        canvas.drawText( rect2, Qt.AlignCenter, counterValue )

        rect3 = pixmap.rect()
        rect3.translate(shadowOffset,0)
        canvas.drawText( rect3, Qt.AlignCenter, counterValue )

        rect4 = pixmap.rect()
        rect4.translate(-shadowOffset,0)
        canvas.drawText( rect4, Qt.AlignCenter, counterValue )

        canvas.setPen( Qt.white )
        canvas.drawText( pixmap.rect(), Qt.AlignCenter, counterValue )


        canvas.end()
        return pixmap


    def overlayShutter(self):
        # first, block the webcam stream for a while
        self.camRefresh.stop()
        self.camHibernate.stop()

        # now produce an overlay to indicate the picture taking process
        pixmap = self.ui.label_pictureView.pixmap()

        # white shadow
        canvas = QPainter()
        canvas.begin(pixmap)
        canvas.fillRect(0,0, pixmap.width(), pixmap.height(), QColor(255,255,255,150))

        # message if in camera mode
        if not USE_WEBCAM:
            message = "Aufnahme..."
            shadowOffset = 2
            messageRect = pixmap.rect()
            messageRect.setHeight(pixmap.height()/2)
            messageFont = QFont("Helvetica Neue")
            messageFont.setPointSize(100)
            canvas.setFont( messageFont )

            canvas.setPen( Qt.black )
            rect1 = messageRect
            rect1.translate(0,shadowOffset)
            canvas.drawText( rect1, Qt.AlignCenter, message )

            rect2 = messageRect
            rect2.translate(0,-shadowOffset)
            canvas.drawText( rect2, Qt.AlignCenter, message )

            rect3 = messageRect
            rect3.translate(shadowOffset,0)
            canvas.drawText( rect3, Qt.AlignCenter, message )

            rect4 = messageRect
            rect4.translate(-shadowOffset,0)
            canvas.drawText( rect4, Qt.AlignCenter, message )

            canvas.setPen( Qt.white )
            canvas.drawText( messageRect, Qt.AlignCenter, message )

        canvas.end()

        pixmap = self.scaleImageToLabel(pixmap)
        self.ui.label_pictureView.setPixmap(pixmap)


    def pauseLiveview(self):
        """ Pause the live preview for now. """
        if self.camHibernate.isActive():
            self.camRefresh.stop()
            self.camHibernate.stop()
            QTimer.singleShot(100, self.displayHibernateImage)
            self.ui.currentState = S_HIBERNATE
        else:
            self.camHibernate.start()
            self.camRefresh.start()
            self.ui.currentState = S_LIVEVIEW


    def adjustMainButton(self):
        """ Depending on the current state, modify the main button. """
        icon = QIcon()
        if self.ui.currentState == S_LIVEVIEW:
            self.ui.pushButton_main.setText(" Foto!")
            icon.addPixmap(QPixmap(":/icon/graphics/camera_white.png"), QIcon.Normal, QIcon.Off)
            self.ui.pushButton_main.setIcon(icon)
        elif self.ui.currentState == S_DISPLAY:
            self.ui.pushButton_main.setText(" Drucken")
            icon.addPixmap(QPixmap(":/icon/graphics/printer_white.png"), QIcon.Normal, QIcon.Off)
            self.ui.pushButton_main.setIcon(icon)


    def startMainAction(self):
        """ Depending on the current state, take a picture or print. """
        if self.ui.currentState == S_LIVEVIEW:
            self.startPictureProcess()
        elif self.ui.currentState == S_DISPLAY:
            self.ui.listWidget_lastPictures.setCurrentRow(0)
            self.displayImage()
        elif self.ui.currentState == S_HIBERNATE:
            self.pauseLiveview()


    def startMainActionClick(self):
        """ Depending on the current state, take a picture or print. """
        if self.ui.currentState == S_LIVEVIEW:
            self.startPictureProcess()
        elif self.ui.currentState == S_DISPLAY:
            self.printSelectedImage()
        elif self.ui.currentState == S_HIBERNATE:
            self.pauseLiveview()


    def takeImage(self):
        """ Read frame from camera and repaint QLabel widget. """

        # now take a picture
        filePath = getFilePath(self.ui.currentMode, self.multiShotFolder)
        if USE_WEBCAM:
            frame = self.captureFrame()
            frame = cv2.flip(frame, 1)
            cv2.imwrite(filePath, frame)
        else:
            self.camera.capture_image(filePath)

        # things required for multiple shots
        if self.ui.currentMode == M_MULTI:
            self.multiShotCount = self.multiShotCount + 1

            # not finished yet, repeat
            if self.multiShotCount < 4:
                self.countDownValue = 2
                self.countDownOverlayActive = True
                self.multiShotLastImage = filePath

                self.displayImage(filePath)
                self.shotCountDown()
                self.countDownTimer.start()
            else:
                self.buildMultiShotImage()

        # update picture list and select the most recent one
        if not (self.ui.currentMode == M_MULTI and self.multiShotCount < 4):
            # create thumbnails for new pictures
            createThumbnails()

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

        self.countDownOverlayActive = True
        self.countDownValue = 2
        self.shotCountDown()
        self.countDownTimer.start()


    def shotCountDown(self):
        if self.countDownValue > 0:
            self.countDownValue = self.countDownValue - 1
            if self.multiShotLastImage != "":
                self.displayImage(self.multiShotLastImage)
        else:
            self.countDownTimer.stop()
            self.countDownOverlayActive = False
            QTimer.singleShot(100, self.overlayShutter)
            QTimer.singleShot(200, self.takeImage)


    def buildMultiShotImage(self):
        """ Combine the 4 taken images into one single picture. """
        self.multiShotLastImage = ""

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
            self.camHibernate.stop()

            # load the image and display it
            # (Note: It scales the image only once when it loads it.
            #        Resizing the window after that doesn't change scaling.)
            if filePath == "":
                if selectedImageID >= len(self.pictureList):
                    selectedImageID = len(self.pictureList) - 1
                selectedImage = self.pictureList[selectedImageID]
                selectedImagePixmap = QPixmap(selectedImage['path'])
            else:
                selectedImagePixmap = QPixmap(filePath)

            self.ui.currentState = S_DISPLAY
            selectedImagePixmap = self.scaleImageToLabel(selectedImagePixmap)

            # overlay the countdown on the image if activated
            if self.countDownOverlayActive:
                selectedImagePixmap = self.overlayCountdown(selectedImagePixmap)

            self.ui.label_pictureView.setPixmap(selectedImagePixmap)
            self.ui.pushButton_delete.setEnabled(True)
        else:
            # reactivate the live feed
            self.ui.pushButton_delete.setEnabled(False)
            self.ui.currentState = S_LIVEVIEW
            self.camRefresh.start()
            self.camHibernate.start()
        self.adjustMainButton()


    def displayHibernateImage(self):
        """ Make a black image with a tip how to reactivate the stream. """
        pixmap = QPixmap(WEBCAM_WIDTH_PX*2, WEBCAM_HEIGHT_PX*2)
        pixmap.fill(Qt.black)

        canvas = QPainter()
        canvas.begin(pixmap)
        canvas.setPen( Qt.white )

        canvasFont = QFont("Helvetica Neue")
        canvasFont.setPointSize(50)
        canvas.setFont( canvasFont )
        canvas.drawText( pixmap.rect(), Qt.AlignCenter, QString.fromUtf8("Vorschau mit Fußtaster oder Leertaste reaktivieren.") )
        canvas.end()

        pixmap = self.scaleImageToLabel(pixmap)
        self.ui.label_pictureView.setPixmap(pixmap)


    def printSelectedImage(self):
        """ Get the currently selected image and delete it (i.e. move somewhere). """
        selectedImageID = self.ui.listWidget_lastPictures.currentRow()
        if selectedImageID > 0:
            selectedImage = self.pictureList[selectedImageID]
            self.printImage(selectedImage)
            self.ui.listWidget_lastPictures.setCurrentRow(0)
            self.displayImage()


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


    def deleteSelectedImage(self):
        """ Get the currently selected image and print it. """
        selectedImageID = self.ui.listWidget_lastPictures.currentRow()
        if selectedImageID > 0:
            selectedImage = self.pictureList[selectedImageID]

            # move the file into the deleted folder
            oldPath = selectedImage['path']
            newPath = oldPath.replace(PICTURE_PATH, DELETED_PATH)
            os.rename(oldPath, newPath)

            # update the picture list and show the next image
            self.updatePictureList()
            if selectedImageID >= len(self.pictureList):
                selectedImageID = len(self.pictureList)-1
            self.ui.listWidget_lastPictures.setCurrentRow(selectedImageID)
            self.displayImage()


if __name__ == "__main__":
    # check, if PTPCamera is running and kill it
    for proc in psutil.process_iter():
        try:
            pinfo = proc.as_dict(attrs=['pid', 'name'])
        except psutil.NoSuchProcess:
            pass
        else:
            if pinfo['name'] == "PTPCamera":
                proc.kill()

    # the GUI
    app = QApplication([])
    myGui = BoothUI()
    myGui.show()
    myGui.raise_()
    sys.exit(app.exec_())
