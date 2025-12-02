# Vessels All-in-One Container
# Includes: Vessels + FalkorDB + TigerBeetle
# Compatible with Windows 11 Docker Desktop

FROM python:3.11-slim-bookworm

LABEL maintainer="Vessels"
LABEL description="All-in-one Vessels container with FalkorDB and TigerBeetle"

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tools
    build-essential \
    cmake \
    git \
    curl \
    wget \
    unzip \
    # Redis/FalkorDB dependencies
    libssl-dev \
    # Supervisor for multi-process
    supervisor \
    # Document processing deps
    tesseract-ocr \
    poppler-utils \
    libmagic1 \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Install FalkorDB (Redis with graph module)
RUN curl -fsSL https://packages.redis.io/gpg | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb bookworm main" > /etc/apt/sources.list.d/redis.list \
    && apt-get update \
    && apt-get install -y redis-server \
    && rm -rf /var/lib/apt/lists/*

# Download and install FalkorDB module
RUN mkdir -p /opt/falkordb \
    && cd /opt/falkordb \
    && curl -L https://github.com/FalkorDB/FalkorDB/releases/download/v4.4.1/FalkorDB-v4.4.1-linux-x64.tar.gz -o falkordb.tar.gz \
    && tar -xzf falkordb.tar.gz \
    && rm falkordb.tar.gz \
    && mv falkordb.so /opt/falkordb/ 2>/dev/null || mv */falkordb.so /opt/falkordb/ 2>/dev/null || true

# Install TigerBeetle
RUN mkdir -p /opt/tigerbeetle \
    && cd /opt/tigerbeetle \
    && curl -L https://github.com/tigerbeetle/tigerbeetle/releases/download/0.16.11/tigerbeetle-x86_64-linux.zip -o tigerbeetle.zip \
    && unzip tigerbeetle.zip \
    && rm tigerbeetle.zip \
    && chmod +x tigerbeetle \
    && ln -s /opt/tigerbeetle/tigerbeetle /usr/local/bin/tigerbeetle

# Create directories
RUN mkdir -p /vessels /data/falkordb /data/tigerbeetle /var/log/supervisor

# Copy requirements first for better caching
COPY requirements.txt /vessels/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /vessels/requirements.txt

# Copy application code
COPY . /vessels
WORKDIR /vessels

# Copy supervisor and startup configs
COPY docker/standalone/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/standalone/startup.sh /startup.sh
RUN chmod +x /startup.sh

# Environment variables
ENV FALKORDB_HOST=localhost
ENV FALKORDB_PORT=6379
ENV FALKORDB_DATABASE=vessels
ENV TIGERBEETLE_HOST=localhost
ENV TIGERBEETLE_PORT=3000
ENV TIGERBEETLE_CLUSTER_ID=0
# Web UI binds to 0.0.0.0:80
ENV WEB_UI_PORT=80
ENV WEB_UI_HOST=0.0.0.0

# Expose ports
# 80 - Vessels web UI
# 6379 - FalkorDB (internal)
# 3000 - TigerBeetle (internal)
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:80/health || exit 1

# Volumes for persistence
VOLUME ["/data/falkordb", "/data/tigerbeetle", "/vessels/work_dir"]

# Start all services via supervisor
CMD ["/startup.sh"]
