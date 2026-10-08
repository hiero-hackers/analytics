FROM gcr.io/oss-fuzz-base/base-builder-python:v1@sha256:7c97d379ceb773b0bd345f0ced72b037d26e9bb6c4a0c9a176525e65975c5694


COPY . $SRC/analytics
WORKDIR $SRC/analytics
COPY .clusterfuzzlite/build.sh $SRC/
