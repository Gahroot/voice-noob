# Quick Start Guide

## Prerequisites

- Docker and Docker Compose installed
- Python 3.12+ installed
- Node.js 20+ installed
- uv package manager installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Initial Setup

### 1. Install Dependencies

```bash
# Install all dependencies (backend + frontend + docker services)
make install
```

Or manually:

```bash
# Backend
cd backend
uv sync --all-extras

# Frontend
cd frontend
npm install

# Docker services
docker compose up -d postgres redis
```

### 2. Configure Environment Variables

```bash
# Backend
cp backend/.env.example backend/.env
# Edit backend/.env and add your API keys

# Frontend (already created)
# Edit frontend/.env.local if needed
```

### 3. Run Database Migrations

```bash
cd backend
uv run alembic upgrade head
```

## Running the Application

### Option 1: Using Make (Recommended)

```bash
# Start Docker services
make dev
```

Then in separate terminals:

```bash
# Terminal 1: Backend
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
# Terminal 2: Frontend
cd frontend
npm run dev
```

### Option 2: Manual

```bash
# Terminal 1: Docker services
docker compose up -d postgres redis

# Terminal 2: Backend
cd backend
uv run uvicorn app.main:app --reload

# Terminal 3: Frontend
cd frontend
npm run dev
```

## Accessing the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Development Tools

### Backend

```bash
cd backend

# Run tests
uv run pytest

# Lint code
uv run ruff check .

# Format code
uv run ruff format .

# Type checking
uv run mypy app

# Install pre-commit hooks
uv run pre-commit install
```

### Frontend

```bash
cd frontend

# Run linter
npm run lint

# Type checking
npm run type-check

# Build for production
npm run build
```

## Database Management

### Create Migration

```bash
cd backend
uv run alembic revision --autogenerate -m "description"
```

### Run Migrations

```bash
cd backend
uv run alembic upgrade head
```

### Rollback Migration

```bash
cd backend
uv run alembic downgrade -1
```

## Docker Management

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f postgres
docker compose logs -f redis
```

### Restart Services

```bash
docker compose restart
```

### Stop Services

```bash
make stop
# or
docker compose down
```

### Clean Everything

```bash
make clean
# This removes containers, volumes, and installed dependencies
```

## Optional: Database/Redis GUI Tools

### Start Management Tools

```bash
docker compose --profile tools up -d
```

- **pgAdmin**: http://localhost:5050 (admin@voiceagent.local / admin)
- **Redis Commander**: http://localhost:8081

## API Keys Required

Before using voice features, add these API keys to `backend/.env`:

### Required

- `OPENAI_API_KEY` - OpenAI API key for LLM
- `DEEPGRAM_API_KEY` - Deepgram API key for speech-to-text
- `ELEVENLABS_API_KEY` - ElevenLabs API key for text-to-speech

### Telephony (Optional)

- `TELNYX_API_KEY` - Telnyx API key (primary)
- `TELNYX_PUBLIC_KEY` - Telnyx public key
- `TWILIO_ACCOUNT_SID` - Twilio account SID (optional)
- `TWILIO_AUTH_TOKEN` - Twilio auth token (optional)

### Monitoring (Optional)

- `SENTRY_DSN` - Sentry DSN for error tracking

## Troubleshooting

### Port Already in Use

If ports 3000, 5432, 6379, or 8000 are already in use:

```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>
```

### Database Connection Issues

```bash
# Check if PostgreSQL is running
docker compose ps

# View PostgreSQL logs
docker compose logs postgres

# Restart PostgreSQL
docker compose restart postgres
```

### Redis Connection Issues

```bash
# Check if Redis is running
docker compose ps

# Test Redis connection
docker exec -it voice-agent-redis redis-cli ping
```

### Frontend Build Issues

```bash
cd frontend
rm -rf node_modules .next
npm install
npm run dev
```

### Backend Issues

```bash
cd backend
rm -rf .venv
uv sync --all-extras
```

## Next Steps

1. Explore the API documentation at http://localhost:8000/docs
2. Check out the example code in `backend/app/`
3. Review the frontend components in `frontend/src/`
4. Read the main README.md for architecture details

## Need Help?

- Check the logs: `docker compose logs -f`
- Verify all services are running: `docker compose ps`
- Ensure all environment variables are set in `.env` files
- Check the health endpoints:
  - http://localhost:8000/health
  - http://localhost:8000/health/db
  - http://localhost:8000/health/redis
