#!/bin/bash

pyuic4 photoBooth.ui > photoBoothUI.py
pyrcc4 photoBooth.qrc > photoBooth_rc.py
python pyPhotoBooth.py
