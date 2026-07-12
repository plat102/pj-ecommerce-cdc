# Stage 1: export locked requirements from uv (uv itself is not in the runtime image)
# Alpine variant is used because the default distroless uv image lacks /bin/sh,
# which Docker's shell-form RUN needs.
FROM ghcr.io/astral-sh/uv:0.11.14-alpine AS uv-export
WORKDIR /export
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-hashes --no-dev --no-emit-project -o requirements.txt

# Stage 2: runtime image
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv-export /export/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY application/cdc-testing-ui/ .

EXPOSE 8501

ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
