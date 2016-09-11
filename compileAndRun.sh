#!/bin/bash

pyuic4 photoBooth.ui > photoBoothUI.py
pyuic4 portraitBooth.ui > portraitBoothUI.py
pyrcc4 photoBooth.qrc > photoBooth_rc.py
python pyPhotoBooth.py
