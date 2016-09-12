#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pyPhotoBooth - Python tool to take pictures and print them
# http://github.com/Nepomuk/pyPhotoBooth

# general libraries
import sys, os
import psutil
import glob
import time
import random
from subprocess import call

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
from portraitBoothUI import Ui_portraitBooth

# which camera input should be used?
#  auto: use external camera if connected
#  ext: try to force external camera (might crash)
#  webcam: use internal webcam
CAM_MODE = 'auto'

# paths to generated files
DELETED_PATH = "deleted/"
PICTURE_PATH = "pictures/"
PRINTS_PATH = "prints/"
RAWPICS_PATH = "pictures_raw/"
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

# cropping frame
class CropFrame():
    def __init__(self, parent=None):
        # relative values (size + offset < 100!)
        self.height = 0.8
        self.offsetX = 0.2
        self.offsetY = 0.05
        self.shift = 0.005

        # ratio defined as width/height; >1 is a wide image, <1 a tall one
        self.ratio = 1.0
        self.paperDimension = Dimensions()

    def setBaseImageSize(self, pixmap):
        self.baseWidth = pixmap.width()
        self.baseHeight = pixmap.height()
        self.baseRatio = float(pixmap.width())/pixmap.height()

    def getOffsetTop(self):
        offsetTop = self.baseHeight * self.offsetY
        return int(offsetTop)

    def getOffsetRight(self):
        croppedWidth = self.height * self.ratio / self.baseRatio
        offsetRight = self.baseWidth * (croppedWidth + self.offsetX)
        return int(offsetRight)

    def getOffsetBottom(self):
        offsetBottom = self.baseHeight * (self.height + self.offsetY)
        return int(offsetBottom)

    def getOffsetLeft(self):
        offsetLeft = self.baseWidth * self.offsetX
        return int(offsetLeft)


    def getCroppedHeight(self):
        return self.baseHeight * self.height

    def getCroppedWidth(self):
        croppedWidth = self.height * self.ratio / self.baseRatio
        return self.baseWidth * croppedWidth

    def getCanvasHeight(self):
        return self.getCroppedHeight()

    def getCanvasWidth(self):
        return self.getCroppedHeight() * self.paperDimension.getRatio()


    def moveFrameToRight(self):
        croppedWidth = self.height * self.ratio / self.baseRatio
        newOffset = self.offsetX + self.shift
        if newOffset <= 1.0 - croppedWidth:
            self.offsetX = newOffset
        else:
            self.offsetX = 1.0 - croppedWidth

    def moveFrameToLeft(self):
        newOffset = self.offsetX - self.shift
        if newOffset >= 0:
            self.offsetX = newOffset
        else:
            self.offsetX = 0.0

    def moveFrameToBottom(self):
        newOffset = self.offsetY + self.shift
        if newOffset <= 1.0 - self.height:
            self.offsetY = newOffset
        else:
            self.offsetY = 1.0 - self.height

    def moveFrameToTop(self):
        newOffset = self.offsetY - self.shift
        if newOffset >= 0:
            self.offsetY = newOffset
        else:
            self.offsetY = 0.0

    def enlargeFrame(self):
        newHeight = self.height + self.shift
        if newHeight + self.offsetY <= 1.0:
            self.height = newHeight

    def shrinkFrame(self):
        newHeight = self.height - self.shift
        if newHeight > 0.3:
            self.height = newHeight
        else:
            self.height = 0.3


WEBCAM_WIDTH_PX = 740
WEBCAM_HEIGHT_PX = 500

# some states the UI can be in
S_LIVEVIEW = 'liveView'
S_HIBERNATE = 'hibernate'
S_DISPLAY = 'displayImage'


def getFilePath():
    """ Generate a file name for the picture. """
    currentTimeString = time.strftime("%Y-%m-%d_%H-%M-%S")
    basename = currentTimeString
    extension = ".jpg"
    filename = basename + extension
    rawfilepath = RAWPICS_PATH + filename
    filepath = PICTURE_PATH + filename

    return rawfilepath, filepath


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


def getCurrentTone():
    # define colors
    color_ah = [["#80bfff", "#99ccff", "#b3d9ff"], ["#5799d7"], ["#6792ab"], ["#9eb9bb"], ["#5e937d"]]
    color_aw = [["#b482c9"], ["#8787de"], ["#a6cbfc", "#bfdafd", "#cee2fd"], ["#dfafe4"], ["#8e9fcb"]]
    colors = [x[0] for x in (color_ah + color_aw)]

    # extract one random value
    rndIdx = int(random.uniform(0, len(colors)))
    return QColor(colors[rndIdx])


class BoothUI(QWidget):
    def __init__(self, parent=None):
        """Initialize QWidget"""
        QWidget.__init__(self, parent)
        self.ui = Ui_portraitBooth()
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

        # take an image
        self.ui.pushButton_main.clicked.connect(self.startMainActionClick)
        scMain = QShortcut(QKeySequence(Qt.Key_Space), self, self.startMainAction)
        scMain2 = QShortcut(QKeySequence(Qt.Key_B), self, self.startMainAction)
        scPrint = QShortcut(QKeySequence(Qt.Key_Return), self, self.printSelectedImage)

        # modify the crop frame
        scCFleft = QShortcut(QKeySequence(Qt.Key_Left), self, self.cropFrameLeft)
        scCFright = QShortcut(QKeySequence(Qt.Key_Right), self, self.cropFrameRight)
        scCFup = QShortcut(QKeySequence(Qt.Key_Up), self, self.cropFrameUp)
        scCFdown = QShortcut(QKeySequence(Qt.Key_Down), self, self.cropFrameDown)
        scCFplus = QShortcut(QKeySequence(Qt.Key_Plus), self, self.cropFrameEnlarge)
        scCFminus = QShortcut(QKeySequence(Qt.Key_Minus), self, self.cropFrameShrink)

        # select an image
        self.ui.listWidget_lastPictures.itemSelectionChanged.connect(self.displayImage)

        # delete an image
        self.ui.pushButton_delete.clicked.connect(self.deleteSelectedImage)
        scDelete = QShortcut(QKeySequence(Qt.Key_L), self, self.deleteSelectedImage)


    def initObjects(self):
        self.printDim = Dimensions()
        self.croppedFrame = CropFrame()
        self.liveViewIcon = {
            "title": "Neues Foto",
            "pic":   QIcon("graphics/picture_single.png"),
            "path":  "graphics/picture_single.png"
        }
        self.ui.currentState = S_LIVEVIEW
        self.lastRawPicture = ""
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

        # show the frame of cropped areas
        pixmap = self.overlayCroppingFrame(pixmap)

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
            newHeight = int(float(frameSize[0]) / self.printDim.getRatio())
            cutHeight = int(( frameSize[1] - newHeight ) / 2)
            newFrame = frame[cutHeight:(cutHeight+newHeight), 0:frameSize[0]]

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

        # show the frame of cropped areas
        pixmap = self.overlayCroppingFrame(QPixmap.fromImage(image))

        # scale the image down if necessary
        pixmap = self.scaleImageToLabel(pixmap)

        # overlay the countdown on the image if activated
        if self.countDownOverlayActive:
            pixmap = self.overlayCountdown(pixmap)

        # set image
        self.ui.label_pictureView.setPixmap(pixmap)


    def overlayCroppingFrame(self, pixmap):
        canvas = QPainter()
        canvas.begin(pixmap)
        self.croppedFrame.setBaseImageSize(pixmap)
        whiteTransparent = QBrush(QColor(255, 255, 255, 160))

        topRect = QRect()
        topRect.setTop(0)
        topRect.setLeft(0)
        topRect.setBottom(self.croppedFrame.getOffsetTop())
        topRect.setRight(pixmap.width())

        bottomRect = QRect()
        bottomRect.setTop(self.croppedFrame.getOffsetBottom())
        bottomRect.setLeft(0)
        bottomRect.setBottom(pixmap.height())
        bottomRect.setRight(pixmap.width())

        leftRect = QRect()
        leftRect.setTop(self.croppedFrame.getOffsetTop()+1)
        leftRect.setLeft(0)
        leftRect.setBottom(self.croppedFrame.getOffsetBottom()-1)
        leftRect.setRight(self.croppedFrame.getOffsetLeft())

        rightRect = QRect()
        rightRect.setTop(self.croppedFrame.getOffsetTop()+1)
        rightRect.setLeft(self.croppedFrame.getOffsetRight())
        rightRect.setBottom(self.croppedFrame.getOffsetBottom()-1)
        rightRect.setRight(pixmap.width())

        canvas.fillRect(topRect, whiteTransparent)
        canvas.fillRect(bottomRect, whiteTransparent)
        canvas.fillRect(leftRect, whiteTransparent)
        canvas.fillRect(rightRect, whiteTransparent)

        return pixmap


    def overlayCountdown(self, pixmap):
        canvas = QPainter()
        canvas.begin(pixmap)
        shadowOffset = 2

        counterTitle = "Foto in"
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
        pixmap = self.ui.label_pictureView.pixmap()

        canvas = QPainter()
        canvas.begin(pixmap)
        canvas.fillRect(0,0, pixmap.width(), pixmap.height(), QColor(255,255,255,150))
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


    def cropFrameLeft(self):
        self.croppedFrame.moveFrameToLeft()
    def cropFrameRight(self):
        self.croppedFrame.moveFrameToRight()
    def cropFrameUp(self):
        self.croppedFrame.moveFrameToTop()
    def cropFrameDown(self):
        self.croppedFrame.moveFrameToBottom()
    def cropFrameEnlarge(self):
        self.croppedFrame.enlargeFrame()
    def cropFrameShrink(self):
        self.croppedFrame.shrinkFrame()


    def takeImage(self):
        """ Read frame from camera and repaint QLabel widget. """
        # first, block the webcam stream for a while
        self.camRefresh.stop()
        self.camHibernate.stop()
        self.overlayShutter()

        # now take a picture
        rawFilePath, filePath = getFilePath()
        if USE_WEBCAM:
            frame = self.captureFrame()
            frame = cv2.flip(frame, 1)
            cv2.imwrite(rawFilePath, frame)
        else:
            self.camera.capture_image(rawFilePath)

        # adjust image for the portrait wall
        self.cropAndColorImage(rawFilePath, filePath)

        # update picture list and select the most recent one
        createThumbnails()

        self.ui.pushButton_main.setEnabled(True)
        self.updatePictureList()
        self.ui.listWidget_lastPictures.setCurrentRow(1)
        self.displayImage()


    def startPictureProcess(self):
        """ Starts the process taking pichture(s) depending on the set mode. """
        self.ui.pushButton_main.setEnabled(False)
        self.countDownOverlayActive = True
        self.countDownValue = 2
        self.shotCountDown()
        self.countDownTimer.start()


    def shotCountDown(self):
        if self.countDownValue > 0:
            self.countDownValue = self.countDownValue - 1
            # if self.multiShotLastImage != "":
            #     self.displayImage(self.multiShotLastImage)
        else:
            self.countDownTimer.stop()
            self.countDownOverlayActive = False
            QTimer.singleShot(100, self.takeImage)


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


    def cropAndColorImage(self, rawFilePath, filePath):
        # load the picture
        rawPicture = QImage(rawFilePath)
        self.croppedFrame.setBaseImageSize(rawPicture.size())

        # create the base of the image including white space
        canvas = QPainter()
        canvasImage = QImage(self.croppedFrame.getCanvasWidth(), self.croppedFrame.getCanvasHeight(), QImage.Format_RGB32)
        canvasImage.fill(Qt.white)
        canvas.begin(canvasImage)

        # crop the raw image
        picture = self.cropImage(rawPicture)

        # place the actual image on one side
        target = QRectF(0, 0, self.croppedFrame.getCroppedWidth(), self.croppedFrame.getCroppedHeight())
        canvas.drawImage(target, picture)

        # finish and save
        canvas.end()
        canvasImage.save(filePath, "JPG", 93)

        # finally color the image (last step because it needs a physical file)
        self.colorImage(filePath)


    def cropImage(self, rawPicture):
        cropArea = QRect()
        cropArea.setTop(self.croppedFrame.getOffsetTop())
        cropArea.setRight(self.croppedFrame.getOffsetRight())
        cropArea.setBottom(self.croppedFrame.getOffsetBottom())
        cropArea.setLeft(self.croppedFrame.getOffsetLeft())

        croppedPicture = rawPicture.copy(cropArea)
        return croppedPicture


    def colorImage(self, filePath):
        # get a random tone and normalize it
        tone = getCurrentTone()

        # extract gray value for each pixel and color it then
        # coloredPicture = picture
        # for x in range(picture.width()):
        #     for y in range(picture.height()):
        #         gray = qGray(picture.pixel(x,y))
        #         monotone = QColor().fromHsv(tone.hue(), tone.saturation()*1.2, gray)
        #         monotone = monotone.lighter(130)
        #         coloredPicture.setPixel(x,y, monotone.rgb())

        # return coloredPicture

        # use imagemagick to convert the color of the image
        levelColors = "'rgb({0},{1},{2})',".format(tone.red(), tone.green(), tone.blue())
        call(["convert", filePath, "-colorspace", "Gray", "+level-colors", levelColors, filePath])


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
