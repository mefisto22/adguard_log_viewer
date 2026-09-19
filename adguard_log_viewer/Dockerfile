ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

SHELL ["/bin/ash", "-o", "pipefail", "-c"]

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/opt/adguard_log_viewer

WORKDIR /opt/adguard_log_viewer

# `--only-binary :all:` makes a missing wheel a loud build failure instead of a
# silent attempt to compile Rust or C on a Raspberry Pi. Every pinned dependency
# publishes musllinux wheels for both supported architectures.
COPY requirements.txt ./
RUN pip install --no-cache-dir --only-binary :all: -r requirements.txt

# The application, including the pre-built frontend in app/static.
COPY app ./app

# The Home Assistant base image's s6-overlay runs this as the container's main
# process. Options are read from /data/options.json by app.config, so no shell
# wrapper is needed.
CMD ["python", "-m", "app.main"]

# Build metadata, filled in by the Supervisor / the build action.
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.revision="${BUILD_REF}" \
    org.opencontainers.image.version="${BUILD_VERSION}" \
    org.opencontainers.image.licenses="MIT"
