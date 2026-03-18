FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# force HTTPS repo + install curl
RUN printf "deb https://deb.debian.org/debian trixie main\n\
deb https://deb.debian.org/debian trixie-updates main\n\
deb https://deb.debian.org/debian-security trixie-security main\n" > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml README.md ./

RUN uv pip install --system torch --index-url https://download.pytorch.org/whl/cpu
RUN uv pip install --system .

COPY . .

EXPOSE 8080

CMD ["sh", "-c", "uvicorn src.api.rest.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
