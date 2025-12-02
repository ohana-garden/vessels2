# Vessels All-in-One Container

Single container with everything included:
- **Vessels** - Agent framework
- **FalkorDB** - Graph database (Graphiti backend)
- **TigerBeetle** - Financial ledger

## Quick Start (Windows 11 Docker Desktop)

1. **Copy environment file and add API keys:**
   ```powershell
   cd docker/standalone
   copy .env.example .env
   # Edit .env with your API keys
   ```

2. **Build and run:**
   ```powershell
   docker compose up -d
   ```

3. **Open browser:**
   ```
   http://localhost:8080
   ```

## Manual Build

```bash
# From repo root
docker build -f docker/standalone/Dockerfile -t vessels:latest .

# Run
docker run -d \
  -p 8080:80 \
  -v vessels-data:/data/falkordb \
  -v vessels-tb:/data/tigerbeetle \
  -v vessels-work:/vessels/work_dir \
  -e OPENAI_API_KEY=sk-... \
  --name vessels \
  vessels:latest
```

## Ports

| Port | Service | Internal |
|------|---------|----------|
| 8080 | Vessels Web UI | 80 |
| - | FalkorDB | 6379 (internal) |
| - | TigerBeetle | 3000 (internal) |

## Volumes

| Volume | Purpose |
|--------|---------|
| vessels-data | FalkorDB graph data |
| vessels-tb | TigerBeetle ledger data |
| vessels-work | Vessels working directory |

## Logs

```bash
# All logs
docker compose logs -f

# Specific service
docker exec vessels cat /var/log/supervisor/vessels.log
docker exec vessels cat /var/log/supervisor/falkordb.log
docker exec vessels cat /var/log/supervisor/tigerbeetle.log
```

## Stop

```bash
docker compose down

# Remove data too
docker compose down -v
```
