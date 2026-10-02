# Reproducible environment for the INR/USD fair-value pipeline.
#   docker build --build-arg GIT_REVISION=$(git rev-parse --short HEAD) -t inrfv .
#   docker run --rm -v "$PWD/outputs:/app/outputs" inrfv                      # full run on the cached data
#   docker run --rm inrfv python -m pytest -q                                # test suite
#   docker run --rm --env-file .env -v "$PWD:/app" inrfv python -m inrfv.refresh   # refresh (needs network)
FROM python:3.12-slim

ARG GIT_REVISION=unknown
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    INRFV_GIT_REVISION=${GIT_REVISION}

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY pyproject.toml README.md CHANGELOG.md ./
COPY src ./src
RUN pip install --no-deps -e .

COPY config ./config
COPY data ./data
COPY tests ./tests
COPY scripts ./scripts

CMD ["python", "-m", "inrfv.run"]
