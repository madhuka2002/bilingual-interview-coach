FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

FROM jenkins/inbound-agent:3345.v03dee9b_f88fc-1-jdk21

USER root

COPY --from=uv /uv /uvx /usr/local/bin/

ENV UV_CACHE_DIR=/opt/uv/cache \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PYTHON=3.12

RUN mkdir -p "${UV_CACHE_DIR}" "${UV_PYTHON_INSTALL_DIR}" \
    && uv python install 3.12 \
    && chown -R jenkins:jenkins /opt/uv

USER jenkins

RUN uv run --no-project python --version \
    && uv --version
