# The API, as it runs on a server. Built and started by deploy/docker-compose.yml - see
# deploy/DEPLOY.ar.md for the whole procedure.

# The version the suite runs on, here and in CI. DuckDB ships wheels per Python version,
# so a different one here is a different database engine build from the one tested.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# A face that covers Arabic and Hebrew for PDF exports. reportlab's own fonts are
# Latin-1 only, and a slim image has no others, so without this every label in an
# exported PDF is a box - see app/services/pdf_fonts.py.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app

# Not root. uid 1000 is also who owns the host folders mounted at /data and /backups -
# the guide creates them that way.
RUN useradd --uid 1000 --create-home autoline \
    && mkdir -p /data /backups \
    && chown autoline:autoline /data /backups
USER autoline

ENV DATA_DIR=/data \
    BACKUP_DIR=/backups

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# One worker, and it has to stay one. Each dataset is a DuckDB file that accepts a single
# writer process, and the rate limiter and restore progress live in this process's
# memory - a second worker would be refused the database and would count requests on
# its own.
#
# --proxy-headers takes the visitor's address from the reverse proxy. Without it every
# request appears to come from the proxy, and the login guard and the rate limiter -
# both keyed on the address - would treat all visitors as one, locking everyone out
# together. Only the compose network is trusted to set it: the proxy overwrites the
# header with the real peer, and nothing outside that network can reach this port.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "172.28.0.0/24", \
     "--timeout-graceful-shutdown", "30"]
