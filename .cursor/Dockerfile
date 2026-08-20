# Cursor Cloud Agent base image for the Pulse monorepo.
# Provides the system toolchain (Python 3.12, Node 22) plus uv + bun installed
# into /usr/local/bin so they are on PATH for every shell (login or not).
# Project dependencies are installed by the `install` command in
# .cursor/environment.json (`make sync`), NOT here — do not COPY the repo.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# System dependencies. git + sudo are required by the Cloud Agent runtime
# (it clones the repo and expects passwordless sudo). build-essential provides
# `make` and a C toolchain; python3.12 matches .python-version.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    sudo \
    unzip \
    xz-utils \
    build-essential \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22 (used by @react-router/serve in prod and some JS tooling).
RUN curl --retry 3 --retry-delay 5 -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Non-root `ubuntu` user with passwordless sudo, as expected by Cloud Agents.
RUN id -u ubuntu >/dev/null 2>&1 || useradd -m -s /bin/bash ubuntu \
    && usermod -aG sudo ubuntu \
    && echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu \
    && chmod 0440 /etc/sudoers.d/ubuntu

# uv (Python package/monorepo manager), pinned. Installed to /usr/local/bin so
# it is on the default PATH for all shells without profile edits.
RUN curl --retry 3 --retry-delay 5 -LsSf https://astral.sh/uv/0.12.3/install.sh \
    | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

# bun (JS package manager/runtime), pinned. BUN_INSTALL=/usr/local places the
# binary at /usr/local/bin/bun.
RUN curl --retry 3 --retry-delay 5 -fsSL https://bun.sh/install \
    | env BUN_INSTALL=/usr/local bash -s "bun-v1.3.14"

USER ubuntu
