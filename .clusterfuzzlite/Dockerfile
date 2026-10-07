FROM gcr.io/oss-fuzz-base/base-builder-python:v1@sha256:ea2c86745d082ab30d6717ede1492fbe488af681cf5b70586510d4ada8766024


COPY . $SRC/analytics
WORKDIR $SRC/analytics
COPY .clusterfuzzlite/build.sh $SRC/
