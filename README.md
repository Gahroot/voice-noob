# Voice Agent Platform

A modern voice agent web application enabling users to configure and deploy custom voice agents for inbound and outbound calls.

## Tech Stack

### Voice & AI
- **Pipecat** - Voice agent orchestration
- **Deepgram Nova-3** - Speech-to-text
- **ElevenLabs Flash v2.5** - Text-to-speech
- **OpenAI GPT-4** - Language model
- **OpenAI Realtime API** - End-to-end speech processing

### Backend
- **FastAPI** - Modern async web framework
- **PostgreSQL 17** - Primary database
- **Redis** - Caching, rate limiting, task queue
- **SQLAlchemy 2.0** - Async ORM
- **Alembic** - Database migrations
- **Pydantic** - Data validation

### Frontend
- **Next.js 15** - React framework (App Router)
- **TypeScript** - Type-safe JavaScript
- **Tailwind CSS** - Utility-first CSS
- **React 19** - UI library

### Telephony
- **Telnyx** - Primary telephony provider
- **Twilio** - Optional secondary provider

### Infrastructure
- **Docker** - Containerization
- **Docker Compose** - Local orchestration
- **Fly.io** - Production deployment
- **Redis** - Caching and queuing

### Development Tools
- **uv** - Fast Python package manager
- **ruff** - Python linter and formatter
- **mypy** - Static type checker
- **pre-commit** - Git hooks
- **pytest** - Testing framework

### Monitoring
- **Sentry** - Error tracking
- **OpenTelemetry** - Distributed tracing

## Project Structure

```
voice-noob/
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── api/         # API routes
│   │   ├── core/        # Core configuration
│   │   ├── db/          # Database models and migrations
│   │   ├── services/    # Business logic
│   │   └── main.py      # Application entry point
│   ├── tests/           # Backend tests
│   ├── pyproject.toml   # Python dependencies
│   └── Dockerfile       # Backend container
├── frontend/            # Next.js frontend
│   ├── src/
│   │   ├── app/         # App router pages
│   │   ├── components/  # React components
│   │   └── lib/         # Utilities
│   ├── package.json     # Node dependencies
│   └── Dockerfile       # Frontend container
├── docker-compose.yml   # Local development setup
└── README.md           # This file
```

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Python 3.12+
- Node.js 20+
- uv (Python package manager)

### Installation

1. Clone the repository
2. Copy environment files:
   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```
3. Start services:
   ```bash
   docker-compose up -d
   ```
4. Install backend dependencies:
   ```bash
   cd backend
   uv sync
   ```
5. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   ```

### Development

- Backend API: http://localhost:8000
- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs

## License

MIT
