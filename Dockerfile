# syntax=docker/dockerfile:1
# Research image for the CSI 500 pipeline: pinned Pi runtime on top of the
# hash-locked CPython 3.11 project environment. It carries no credentials, no
# ledger, and no schedule; it is for offline software regression and Mock runs
# unless an operator injects a reviewed .env at run time (see docs/macos-runbook.md).
ARG NODE_IMAGE=node:22-bookworm-slim
ARG PYTHON_IMAGE=python:3.11-slim

FROM ${NODE_IMAGE} AS pi-runtime
WORKDIR /app/pi_runtime
COPY pi_runtime/package.json pi_runtime/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org

FROM ${PYTHON_IMAGE}
ENV PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PI_OFFLINE=1 \
    PI_TELEMETRY=0
WORKDIR /app

# Project venv at the path the runtime contract requires (<root>/.venv/bin/python),
# installed from the Linux arm64 hash lock before any source is copied.
COPY requirements-linux-aarch64.txt /tmp/requirements-lock.txt
RUN python -m venv .venv \
    && .venv/bin/python -m pip install --require-hashes --only-binary=:all: \
        -r /tmp/requirements-lock.txt \
    && .venv/bin/python -m pip check \
    && rm /tmp/requirements-lock.txt

# Node binary from the pinned runtime stage; the Pi CLI is executed with it.
COPY --from=pi-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=pi-runtime /usr/local/bin/node /usr/local/bin/node
# Full source tree (minus the .dockerignore set: no .git, .venv, .env, caches,
# runs, or ledgers) so the contract tests that read scripts and docs run too.
COPY --from=pi-runtime /app/pi_runtime/node_modules ./pi_runtime/node_modules
COPY . .
RUN useradd --uid 1000 --create-home quant 2>/dev/null || true

# Default command is offline and credential-free: it only inspects the runtime.
ENTRYPOINT ["/app/.venv/bin/python", "tools/quant_ops.py"]
CMD ["python-runtime", "--require-ready"]
USER 1000:1000
