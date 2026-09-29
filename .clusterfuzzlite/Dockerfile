FROM gcr.io/oss-fuzz-base/base-builder-python:v1@sha256:6a90ec89a18436e057a06f54266c3f120eb87d96c095b0c67a2b15cab33ec1f4


COPY . $SRC/analytics
WORKDIR $SRC/analytics
COPY .clusterfuzzlite/build.sh $SRC/
