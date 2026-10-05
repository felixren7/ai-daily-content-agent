# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system agent && useradd --system --gid agent --home-dir /app agent

WORKDIR /app
RUN pip install --no-cache-dir "setuptools>=75" wheel
COPY pyproject.toml ./
COPY app/__init__.py ./app/__init__.py
RUN touch README.md && pip install --no-cache-dir --no-build-isolation .

COPY README.md LICENSE ./
COPY app ./app
RUN pip install --no-cache-dir --no-deps --no-build-isolation . && \
    mkdir -p /app/data && \
    chown -R agent:agent /app

USER agent
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM runtime AS test
USER root
RUN pip install --no-cache-dir --no-build-isolation ".[dev]"
COPY tests ./tests
USER agent
CMD ["pytest"]
