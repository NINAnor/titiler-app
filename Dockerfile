FROM ghcr.io/astral-sh/uv:python3.13-bookworm AS base

RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    apt-get update && apt-get install --no-install-recommends -yq libgl1-mesa-glx -y

COPY ./pyproject.toml ./uv.lock .
RUN uv sync --frozen

FROM base
COPY src src
CMD ["uv", "run", "uvicorn", "src.app.app:app", "--host", "0.0.0.0", "--port", "80"]
