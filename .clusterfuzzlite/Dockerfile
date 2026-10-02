FROM gcr.io/oss-fuzz-base/base-builder-python:v1@sha256:1de9e4ac301ddea42b8846480d5e4903580ed5071357c9173a4d26a4af65a6fa


COPY . $SRC/analytics
WORKDIR $SRC/analytics
COPY .clusterfuzzlite/build.sh $SRC/
