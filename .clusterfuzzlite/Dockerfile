FROM gcr.io/oss-fuzz-base/base-builder-python:v1@sha256:182f0e4543c1285088fea0dd685febf7e623ba0c4035d24e574bc79bc239c33b


COPY . $SRC/analytics
WORKDIR $SRC/analytics
COPY .clusterfuzzlite/build.sh $SRC/
