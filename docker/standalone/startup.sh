#!/bin/bash
set -e

echo "=== Vessels All-in-One Container ==="
echo "Starting services..."

# Create data directories if they don't exist
mkdir -p /data/falkordb /data/tigerbeetle /vessels/work_dir

# Initialize TigerBeetle data file if it doesn't exist
if [ ! -f /data/tigerbeetle/0_0.tigerbeetle ]; then
    echo "Initializing TigerBeetle data file..."
    /usr/local/bin/tigerbeetle format \
        --cluster=0 \
        --replica=0 \
        --replica-count=1 \
        /data/tigerbeetle/0_0.tigerbeetle
    echo "TigerBeetle initialized."
fi

# Check if FalkorDB module exists
if [ ! -f /opt/falkordb/falkordb.so ]; then
    echo "WARNING: FalkorDB module not found at /opt/falkordb/falkordb.so"
    echo "Graph features may not work correctly."
fi

# Set environment variables for the application
export FALKORDB_HOST=${FALKORDB_HOST:-localhost}
export FALKORDB_PORT=${FALKORDB_PORT:-6379}
export FALKORDB_DATABASE=${FALKORDB_DATABASE:-vessels}
export TIGERBEETLE_HOST=${TIGERBEETLE_HOST:-localhost}
export TIGERBEETLE_PORT=${TIGERBEETLE_PORT:-3000}
export TIGERBEETLE_CLUSTER_ID=${TIGERBEETLE_CLUSTER_ID:-0}

echo "Configuration:"
echo "  FalkorDB: ${FALKORDB_HOST}:${FALKORDB_PORT}"
echo "  TigerBeetle: ${TIGERBEETLE_HOST}:${TIGERBEETLE_PORT}"
echo ""

# Start supervisor (manages all processes)
echo "Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
