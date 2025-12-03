# Vessels All-in-One Container

Self-instantiating Docker setup for Windows 11. Just provide API keys and go.

**Includes:**
- **Vessels** - AI Agent Community Framework
- **FalkorDB** - Graph database with Graphiti for knowledge
- **TigerBeetle** - Financial ledger for Kala tracking

**Features:**
- Entity Ontology (personas for humans, agents, plants, machines, systems, biomes...)
- Moral Geometry (15-dimensional ethical space)
- Kala (non-currency contribution visibility)
- Hume AI Integration (voice personas via EVI)

## Quick Start (Windows 11)

### Option 1: Automatic Setup (Recommended)

**Using Command Prompt:**
```cmd
cd docker\standalone
setup.bat
```

**Using PowerShell:**
```powershell
cd docker\standalone
.\setup.ps1
```

The setup script will:
1. Check Docker is running
2. Prompt for your API keys
3. Create the .env configuration file
4. Build and start Vessels
5. Open your browser to http://localhost:8080

### Option 2: Manual Setup

1. **Copy environment file:**
   ```powershell
   cd docker/standalone
   copy .env.example .env
   ```

2. **Edit .env and add your API keys:**
   ```
   OPENAI_API_KEY=sk-...
   # or
   ANTHROPIC_API_KEY=sk-ant-...
   ```

3. **Build and run:**
   ```powershell
   docker compose up -d
   ```

4. **Open browser:**
   ```
   http://localhost:8080
   ```

## API Keys

You need at least ONE LLM API key:

| Provider | Get Key From | Used For |
|----------|--------------|----------|
| OpenAI | https://platform.openai.com/api-keys | Main LLM + Graphiti |
| Anthropic | https://console.anthropic.com/ | Main LLM + Graphiti |
| Hume AI | https://platform.hume.ai | Voice personas (optional) |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Vessels Container                     │
│                                                         │
│  ┌─────────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │   Vessels UI    │  │  FalkorDB   │  │ TigerBeetle │ │
│  │   (Port 80)     │  │ (Port 6379) │  │ (Port 3000) │ │
│  └────────┬────────┘  └──────┬──────┘  └──────┬──────┘ │
│           │                  │                 │        │
│           └──────────────────┴─────────────────┘        │
│                         │                               │
│  ┌─────────────────────────────────────────────────────┐│
│  │                Graph Store                          ││
│  │  - Entity Personas    - Moral Geometry              ││
│  │  - Elicitation Sessions - Kala Events               ││
│  │  - Voice Sessions     - Stories & Boundaries        ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
                          │
                    Port 8080 → Browser
```

## Ports

| Port | Service | Access |
|------|---------|--------|
| 8080 | Vessels Web UI | External (your browser) |
| 80 | Vessels (internal) | Internal |
| 6379 | FalkorDB | Internal only |
| 3000 | TigerBeetle | Internal only |

## Volumes

| Volume | Purpose | Location |
|--------|---------|----------|
| vessels-falkordb-data | Graph database | Persistent |
| vessels-tigerbeetle-data | Financial ledger | Persistent |
| vessels-work-dir | Working files | Persistent |

## Common Commands

```bash
# View logs (all services)
docker compose logs -f

# View specific service logs
docker exec vessels cat /var/log/supervisor/vessels.log
docker exec vessels cat /var/log/supervisor/falkordb.log
docker exec vessels cat /var/log/supervisor/tigerbeetle.log

# Restart Vessels
docker compose restart

# Stop Vessels
docker compose down

# Stop and remove all data (fresh start)
docker compose down -v

# Rebuild after code changes
docker compose up -d --build
```

## Running Tests

Once the container is running, you can run the test suite:

```bash
# Enter the container
docker exec -it vessels bash

# Run tests
cd /vessels
python -m pytest tests/test_vessels_core.py -v

# Run only entity ontology tests
python -m pytest tests/test_vessels_core.py::TestEntityOntology -v
```

## Troubleshooting

### Docker not starting
- Make sure Docker Desktop is running
- Check Docker has enough resources (Settings → Resources)
- Try: `docker system prune` to clean up old containers

### Container fails to start
```bash
# Check logs
docker compose logs

# Check if ports are in use
netstat -an | findstr 8080
```

### FalkorDB module error
The FalkorDB module is downloaded during build. If it fails:
```bash
# Rebuild from scratch
docker compose build --no-cache
```

### Reset everything
```bash
# Stop and remove all data
docker compose down -v

# Remove the image
docker rmi vessels:latest

# Rebuild
docker compose up -d --build
```

## Manual Build

If you want to build manually:

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

## What Gets Stored

All data persists in Docker volumes:

- **FalkorDB**: Entity personas, moral geometry vectors, Kala events, stories, elicitation sessions
- **TigerBeetle**: Financial ledger for Kala accounting (future)
- **Work Directory**: Uploaded files, generated content

Your API keys are stored in the local `.env` file and passed as environment variables.
