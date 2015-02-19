#!/usr/bin/env python
"""
A script to constantly save images from the webcam
"""

import numpy as np
import cv2
import time

cap = cv2.VideoCapture(0)

# we need some initial delay to adjust camera brightness settings
cap.read()
time.sleep(1)

imageCount = 0
while(True):
    # Capture frame-by-frame
    ret, frame = cap.read()

    # Save the image
    filename = "img_{0:05d}.jpg".format( imageCount )
    cv2.imwrite(filename, frame)
    print "captured image '{0}'".format( filename )

    # Display the resulting frame
    # cv2.imshow('frame',frame)
    # if cv2.waitKey(1) & 0xFF == ord('q'):
    #     break

    imageCount = imageCount + 1

    # wait a bit
    time.sleep(1)

# When everything done, release the capture
cap.release()
cv2.destroyAllWindows()
