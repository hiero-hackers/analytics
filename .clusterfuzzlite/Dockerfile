FROM gcr.io/oss-fuzz-base/base-builder-python:v1@sha256:f606cee856c34585c314af4fbc41940bce398f5244fbfc757116188828f473c6


COPY . $SRC/analytics
WORKDIR $SRC/analytics
COPY .clusterfuzzlite/build.sh $SRC/
