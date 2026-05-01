FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /src
COPY packages/pulse/python /src/packages/pulse/python
COPY packages/pulse-railway /src/packages/pulse-railway

RUN uv pip install --system /src/packages/pulse/python /src/packages/pulse-railway

CMD ["pulse-railway", "janitor", "run"]
