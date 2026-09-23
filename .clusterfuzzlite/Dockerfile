FROM gcr.io/oss-fuzz-base/base-builder-python:v1@sha256:2ad0b742d9375b89173186beafc97492fd9dfd0f38e1e77467594b784f376969


COPY . $SRC/analytics
WORKDIR $SRC/analytics
COPY .clusterfuzzlite/build.sh $SRC/
