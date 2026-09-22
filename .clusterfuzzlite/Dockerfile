FROM gcr.io/oss-fuzz-base/base-builder-python:v1@sha256:140e90791e768fdcbbbd9f7299e5d4d9fc8cfd1ed3c906aa1ca555c9dfe69fa6


COPY . $SRC/analytics
WORKDIR $SRC/analytics
COPY .clusterfuzzlite/build.sh $SRC/
