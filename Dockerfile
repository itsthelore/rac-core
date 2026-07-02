# Official rac container image. Built from the release wheel in dist/ so the
# image carries exactly the distribution published to PyPI for the same CalVer
# tag (rac/roadmaps/future/oci-image.md). Packaging only: no behaviour,
# flags, or configuration beyond the CLI's own.
#
# Local build:
#   python -m build && docker build -t rac .
#   docker run --rm -v "$PWD:/work" rac validate rac/
FROM python:3.12-slim

ARG RAC_VERSION=dev
LABEL org.opencontainers.image.title="rac" \
      org.opencontainers.image.description="RAC (Lore) requirements-as-code CLI" \
      org.opencontainers.image.source="https://github.com/itsthelore/rac-core" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${RAC_VERSION}"

COPY dist/ /tmp/dist/
RUN pip install --no-cache-dir /tmp/dist/*.whl && rm -rf /tmp/dist

WORKDIR /work
ENTRYPOINT ["rac"]
CMD ["--help"]
