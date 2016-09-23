#!/bin/bash

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 ARCHIVE_DIR" >&2
  exit 1
fi

if [ -d "$1" ]; then
  echo "Archive directory already exists, choose another name." >&2
  exit 1
fi

folders="deleted pictures pictures_raw prints series thumbnails"
archive=$1

mkdir $archive
for folder in $folders
do
    mv $folder $archive
    mkdir $folder
done
