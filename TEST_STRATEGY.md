# Comprehensive Test Strategy for Voice Agent Platform

## Executive Summary

This document outlines a complete testing strategy that can be executed **WITHOUT** real credentials, phone numbers, or external services. All tests use mocks, fixtures, and local test databases.

## Testing Philosophy

- **Isolation**: Tests should never depend on external services
- **Repeatability**: Tests must produce consistent results
- **Speed**: Unit tests run in milliseconds, integration tests in seconds
- **Coverage Goal**: 80%+ for critical paths, 60%+ overall
- **Mocking Strategy**: Mock at boundaries (external APIs, databases for unit tests)

---

## 1. Backend Testing Strategy

### 1.1 Backend Directory Structure

```
backend/
├── tests/
│   ├── __init__.py                    # (already exists)
│   ├── conftest.py                    # Pytest fixtures & configuration
│   │
│   ├── unit/                          # Pure unit tests (no DB/Redis)
│   │   ├── __init__.py
│   │   ├── test_security.py          # JWT, password hashing
│   │   ├── test_cache.py             # Cache utilities (mocked Redis)
│   │   ├── test_limiter.py           # Rate limiting logic
│   │   └── test_models.py            # Model instantiation & validation
│   │
│   ├── integration/                   # API + database integration tests
│   │   ├── __init__.py
│   │   ├── conftest.py               # Integration-specific fixtures
│   │   ├── test_crm_api.py           # CRM endpoints
│   │   ├── test_health_api.py        # Health check endpoints
│   │   └── test_database.py          # Database operations
│   │
│   ├── services/                      # Service layer tests (future)
│   │   ├── __init__.py
│   │   ├── test_voice_pipeline.py    # Mock Pipecat/Deepgram/ElevenLabs
│   │   ├── test_telephony.py         # Mock Telnyx/Twilio
│   │   └── test_websocket.py         # WebSocket message handling
│   │
│   ├── fixtures/                      # Test data fixtures
│   │   ├── __init__.py
│   │   ├── contacts.py               # Sample contact data
│   │   ├── appointments.py           # Sample appointment data
│   │   ├── calls.py                  # Sample call interaction data
│   │   ├── audio.py                  # Mock audio data/buffers
│   │   └── webhooks.py               # Mock webhook payloads
│   │
│   └── mocks/                         # Mock implementations
│       ├── __init__.py
│       ├── mock_redis.py             # In-memory Redis mock
│       ├── mock_deepgram.py          # Mock STT responses
│       ├── mock_elevenlabs.py        # Mock TTS responses
│       ├── mock_openai.py            # Mock LLM responses
│       ├── mock_telnyx.py            # Mock telephony webhooks
│       └── mock_websocket.py         # Mock WebSocket client
```

### 1.2 Backend Test Files to Create

#### A. `tests/conftest.py` - Main Test Configuration

**Purpose**: Central fixtures for database, Redis mocking, and test client

**Key Fixtures**:
```python
- async_test_db_engine: Creates test database engine
- async_test_db_session: Provides clean DB session per test
- test_client: FastAPI TestClient with overrides
- mock_redis: In-memory Redis replacement (fakeredis)
- sample_user: Creates test user
- sample_contact: Creates test contact
```

**Mock Strategy**:
- Use **SQLite in-memory** for test database (fast, no cleanup)
- Use **fakeredis** library for Redis operations
- Override `get_db()` and `get_redis()` dependencies

#### B. `tests/unit/test_security.py` - Security Functions

**Tests**:
```python
test_create_access_token():
    - Creates valid JWT
    - Contains correct subject
    - Expiration time is set correctly
    - Token can be decoded

test_create_access_token_custom_expiry():
    - Respects custom expiration delta

test_verify_password_valid():
    - Returns True for correct password

test_verify_password_invalid():
    - Returns False for incorrect password

test_get_password_hash():
    - Returns bcrypt hash
    - Hash is different from plaintext
    - Same password produces different hashes (salt)
```

**Mocks**: None needed (pure functions)

**Coverage Goal**: 100%

#### C. `tests/unit/test_cache.py` - Cache Utilities

**Tests**:
```python
test_cache_get_hit():
    - Returns cached value when key exists

test_cache_get_miss():
    - Returns None when key doesn't exist

test_cache_set():
    - Stores value successfully
    - Respects TTL

test_cache_delete():
    - Removes key from cache

test_cache_invalidate_pattern():
    - Deletes all keys matching pattern
    - Returns correct count

test_cached_decorator():
    - Caches function result
    - Returns cached value on second call
    - Doesn't call function on cache hit

test_generate_cache_key():
    - Generates unique keys for different args
    - Same args produce same key
    - Handles callable arguments correctly
```

**Mocks**: Use `fakeredis-py` library (already async-compatible)

**Coverage Goal**: 100%

#### D. `tests/unit/test_models.py` - Model Validation

**Tests**:
```python
test_contact_creation():
    - Creates contact with required fields
    - Optional fields work correctly
    - Defaults are applied

test_contact_validation():
    - Validates phone number format
    - Validates email format (if provided)

test_contact_relationships():
    - Can access appointments
    - Can access call_interactions

test_appointment_creation():
    - Creates appointment with datetime
    - Links to contact correctly

test_call_interaction_creation():
    - Creates call record
    - Stores duration correctly
```

**Mocks**: None (uses in-memory models)

**Coverage Goal**: 90%

#### E. `tests/integration/test_crm_api.py` - CRM Endpoints

**Tests**:
```python
test_list_contacts_empty():
    - Returns empty list when no contacts

test_list_contacts():
    - Returns paginated contacts
    - Respects skip/limit parameters
    - Orders by created_at desc

test_get_contact_success():
    - Returns correct contact by ID
    - Includes all fields

test_get_contact_not_found():
    - Returns 404 for non-existent ID

test_create_contact_success():
    - Creates contact with valid data
    - Returns 201 status
    - Includes auto-generated ID

test_create_contact_validation_error():
    - Returns 422 for invalid data
    - Required fields are enforced

test_get_crm_stats():
    - Returns correct counts
    - Caches results
    - Second call returns cached data

test_crm_stats_cache_invalidation():
    - Creating contact invalidates cache
    - Next stats call refreshes from DB

test_rate_limiting():
    - Enforces 100 requests/minute limit
    - Returns 429 when exceeded
```

**Mocks**:
- Test database (SQLite in-memory)
- fakeredis for cache testing
- Mock rate limiter for testing limits

**Coverage Goal**: 85%

#### F. `tests/integration/test_health_api.py` - Health Checks

**Tests**:
```python
test_health_check():
    - Returns 200 status
    - Contains correct response structure

test_health_check_database_down():
    - Returns 503 when DB unavailable
    - Includes error details (if implemented)
```

**Mocks**: Mock database connection failure for error cases

**Coverage Goal**: 100%

#### G. `tests/fixtures/contacts.py` - Contact Test Data

**Fixtures**:
```python
SAMPLE_CONTACTS = [
    {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "phone_number": "+15551234567",
        "company_name": "Acme Corp",
        "status": "new",
        "tags": "sales,vip",
        "notes": "Interested in product demo"
    },
    # ... more samples
]

def create_sample_contact(db: AsyncSession, **overrides):
    """Factory function to create contacts with custom fields"""
```

#### H. `tests/mocks/mock_redis.py` - Redis Mock Setup

**Implementation**:
```python
# Uses fakeredis library
import fakeredis.aioredis

async def get_mock_redis():
    """Returns fakeredis instance for testing"""
    return fakeredis.aioredis.FakeRedis()
```

#### I. Future: `tests/services/test_voice_pipeline.py` - Voice Pipeline

**Tests** (when voice services are implemented):
```python
test_stt_deepgram_mock():
    - Mocks Deepgram WebSocket connection
    - Returns pre-defined transcription
    - Handles audio chunks

test_llm_openai_mock():
    - Mocks OpenAI streaming response
    - Returns generated text tokens
    - Handles function calling

test_tts_elevenlabs_mock():
    - Mocks ElevenLabs API
    - Returns mock audio buffer
    - Handles voice settings

test_telephony_telnyx_webhook():
    - Mocks inbound call webhook
    - Parses webhook payload
    - Initiates voice pipeline

test_websocket_audio_stream():
    - Mocks WebSocket client
    - Sends/receives audio frames
    - Handles connection lifecycle
```

**Mocks**:
```python
# mock_deepgram.py
class MockDeepgramClient:
    async def transcribe_streaming(self, audio_data):
        return {"transcript": "Hello, this is a test"}

# mock_elevenlabs.py
class MockElevenLabsClient:
    async def generate_audio(self, text):
        return b"fake_audio_bytes"  # Or load test.wav

# mock_openai.py
class MockOpenAIClient:
    async def chat_completion(self, messages):
        yield {"delta": {"content": "I can help you with that."}}
```

### 1.3 Backend Testing Tools & Dependencies

**Already Installed**:
- pytest (8.3.4)
- pytest-asyncio (0.24.0)
- pytest-cov (6.0.0)
- pytest-mock (3.14.0)
- faker (33.1.0)

**Need to Add**:
```toml
[project.optional-dependencies]
dev = [
    # ... existing ...
    "fakeredis[aioredis]>=2.26.1",  # In-memory Redis for testing
    "httpx>=0.28.0",                 # Already in main deps, for TestClient
    "pytest-env>=1.1.5",             # Environment variable management
    "freezegun>=1.5.1",              # Mock datetime for tests
]
```

### 1.4 Backend Test Execution

```bash
# Run all tests
cd backend
uv run pytest

# Run specific test file
uv run pytest tests/unit/test_security.py

# Run with coverage
uv run pytest --cov=app --cov-report=html

# Run only unit tests (fast)
uv run pytest tests/unit/

# Run only integration tests
uv run pytest tests/integration/

# Run with verbose output
uv run pytest -v

# Run in parallel (install pytest-xdist)
uv run pytest -n auto
```

---

## 2. Frontend Testing Strategy

### 2.1 Frontend Directory Structure

```
frontend/
├── src/
│   └── __tests__/                     # Test files mirror src structure
│       ├── components/
│       │   ├── ui/
│       │   │   ├── button.test.tsx
│       │   │   ├── card.test.tsx
│       │   │   └── form.test.tsx
│       │   ├── app-sidebar.test.tsx
│       │   └── tier-selector.test.tsx
│       │
│       ├── lib/
│       │   ├── utils.test.ts
│       │   ├── pricing-tiers.test.ts
│       │   ├── api.test.ts
│       │   └── integrations.test.ts
│       │
│       ├── hooks/
│       │   └── use-mobile.test.tsx
│       │
│       └── app/
│           └── dashboard/
│               └── crm/
│                   └── page.test.tsx
│
├── tests/
│   ├── setup.ts                       # Vitest setup file
│   ├── mocks/
│   │   ├── handlers.ts                # MSW API mock handlers
│   │   ├── server.ts                  # MSW server setup
│   │   └── data.ts                    # Mock data fixtures
│   └── utils/
│       └── test-utils.tsx             # Custom render with providers
│
├── vitest.config.ts                   # Vitest configuration
└── package.json                       # Updated scripts & dependencies
```

### 2.2 Frontend Test Files to Create

#### A. `vitest.config.ts` - Test Configuration

**Purpose**: Configure Vitest, path aliases, and global setup

```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      exclude: ['**/*.config.{ts,js}', '**/node_modules/**'],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
```

#### B. `tests/setup.ts` - Test Setup

**Purpose**: Global test setup, MSW server initialization

```typescript
import '@testing-library/jest-dom'
import { server } from './mocks/server'

// Start MSW server before all tests
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))

// Reset handlers after each test
afterEach(() => server.resetHandlers())

// Clean up after all tests
afterAll(() => server.close())

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
}
global.localStorage = localStorageMock as any
```

#### C. `tests/mocks/handlers.ts` - MSW API Handlers

**Purpose**: Mock API responses for all backend endpoints

```typescript
import { http, HttpResponse } from 'msw'

export const handlers = [
  // Health check
  http.get('/api/health', () => {
    return HttpResponse.json({ status: 'ok' })
  }),

  // List contacts
  http.get('/api/crm/contacts', () => {
    return HttpResponse.json([
      {
        id: 1,
        user_id: 1,
        first_name: 'John',
        last_name: 'Doe',
        email: 'john@example.com',
        phone_number: '+15551234567',
        company_name: 'Acme Corp',
        status: 'new',
        tags: 'sales,vip',
        notes: 'Test contact'
      }
    ])
  }),

  // Get single contact
  http.get('/api/crm/contacts/:id', ({ params }) => {
    return HttpResponse.json({
      id: Number(params.id),
      first_name: 'John',
      last_name: 'Doe',
      // ... other fields
    })
  }),

  // Create contact
  http.post('/api/crm/contacts', async ({ request }) => {
    const body = await request.json()
    return HttpResponse.json(
      { id: 1, ...body },
      { status: 201 }
    )
  }),

  // CRM stats
  http.get('/api/crm/stats', () => {
    return HttpResponse.json({
      total_contacts: 42,
      total_appointments: 15,
      total_calls: 103
    })
  }),

  // Error scenarios
  http.get('/api/crm/contacts/999', () => {
    return HttpResponse.json(
      { detail: 'Contact not found' },
      { status: 404 }
    )
  }),
]
```

#### D. `tests/mocks/server.ts` - MSW Server Setup

```typescript
import { setupServer } from 'msw/node'
import { handlers } from './handlers'

export const server = setupServer(...handlers)
```

#### E. `tests/utils/test-utils.tsx` - Custom Render

**Purpose**: Render components with necessary providers (QueryClient, etc.)

```typescript
import { render, RenderOptions } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactElement, ReactNode } from 'react'

const createTestQueryClient = () => new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      gcTime: 0,
    },
  },
})

interface AllTheProvidersProps {
  children: ReactNode
}

const AllTheProviders = ({ children }: AllTheProvidersProps) => {
  const testQueryClient = createTestQueryClient()

  return (
    <QueryClientProvider client={testQueryClient}>
      {children}
    </QueryClientProvider>
  )
}

const customRender = (
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) => render(ui, { wrapper: AllTheProviders, ...options })

export * from '@testing-library/react'
export { customRender as render }
```

#### F. `src/__tests__/lib/pricing-tiers.test.ts` - Pricing Logic

**Tests**:
```typescript
describe('calculateMonthlyCost', () => {
  test('calculates budget tier cost correctly', () => {
    const tier = PRICING_TIERS.find(t => t.id === 'budget')!
    const result = calculateMonthlyCost(tier, 100, 5, 50)

    expect(result.totalMinutes).toBe(500)
    expect(result.aiCost).toBeCloseTo(3.95)
    expect(result.telephonyCost).toBeCloseTo(4.375)
    expect(result.totalCost).toBeCloseTo(8.325)
    expect(result.costPerCall).toBeCloseTo(0.08325)
  })

  test('handles 100% inbound calls', () => {
    const tier = PRICING_TIERS[0]
    const result = calculateMonthlyCost(tier, 100, 5, 100)

    // Only inbound telephony costs
    expect(result.telephonyCost).toBeCloseTo(500 * 0.0075)
  })

  test('handles 100% outbound calls', () => {
    const tier = PRICING_TIERS[0]
    const result = calculateMonthlyCost(tier, 100, 5, 0)

    // Only outbound telephony costs
    expect(result.telephonyCost).toBeCloseTo(500 * 0.01)
  })
})

describe('compareTiers', () => {
  test('returns all tiers with savings calculations', () => {
    const comparison = compareTiers(100, 5)

    expect(comparison).toHaveLength(3)
    expect(comparison[0].tier.id).toBe('budget')

    // Budget should save money vs premium
    expect(comparison[0].savingsVsPremium).toBeGreaterThan(0)

    // Premium should have 0 savings vs itself
    const premiumComparison = comparison.find(c => c.tier.id === 'premium')
    expect(premiumComparison?.savingsVsPremium).toBe(0)
  })
})
```

#### G. `src/__tests__/lib/utils.test.ts` - Utility Functions

**Tests**:
```typescript
describe('cn', () => {
  test('merges class names correctly', () => {
    expect(cn('px-2', 'py-1')).toBe('px-2 py-1')
  })

  test('handles conditional classes', () => {
    expect(cn('px-2', false && 'hidden', 'py-1')).toBe('px-2 py-1')
  })

  test('merges Tailwind classes with twMerge', () => {
    // twMerge should handle conflicting utilities
    expect(cn('px-2', 'px-4')).toBe('px-4')
  })
})
```

#### H. `src/__tests__/lib/api.test.ts` - API Client

**Tests**:
```typescript
import { api } from '@/lib/api'

describe('API client', () => {
  test('adds auth token to requests', async () => {
    localStorage.getItem = vi.fn(() => 'test-token')

    const request = api.interceptors.request.handlers[0]
    const config = { headers: {} as any }
    const result = request.fulfilled(config)

    expect(result.headers.Authorization).toBe('Bearer test-token')
  })

  test('handles 401 errors', async () => {
    // Test that localStorage is cleared and redirect occurs
    // This tests the interceptor logic
  })
})
```

#### I. `src/__tests__/components/tier-selector.test.tsx` - Component Tests

**Tests**:
```typescript
import { render, screen } from '@/tests/utils/test-utils'
import TierSelector from '@/components/tier-selector'

describe('TierSelector', () => {
  test('renders all pricing tiers', () => {
    render(<TierSelector />)

    expect(screen.getByText('Budget')).toBeInTheDocument()
    expect(screen.getByText('Balanced')).toBeInTheDocument()
    expect(screen.getByText('Premium')).toBeInTheDocument()
  })

  test('highlights recommended tier', () => {
    render(<TierSelector />)

    const balanced = screen.getByText('Balanced').closest('div')
    expect(balanced).toHaveClass('recommended') // or whatever class
  })

  test('calls onSelect when tier is clicked', async () => {
    const onSelect = vi.fn()
    render(<TierSelector onSelect={onSelect} />)

    const budgetTier = screen.getByText('Budget')
    await userEvent.click(budgetTier)

    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({
      id: 'budget'
    }))
  })
})
```

#### J. `src/__tests__/hooks/use-mobile.test.tsx` - Hook Tests

**Tests**:
```typescript
import { renderHook } from '@testing-library/react'
import { useMobile } from '@/hooks/use-mobile'

describe('useMobile', () => {
  test('returns true for mobile viewport', () => {
    window.matchMedia = vi.fn().mockImplementation(query => ({
      matches: query === '(max-width: 768px)',
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))

    const { result } = renderHook(() => useMobile())
    expect(result.current).toBe(true)
  })

  test('returns false for desktop viewport', () => {
    window.matchMedia = vi.fn().mockImplementation(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))

    const { result } = renderHook(() => useMobile())
    expect(result.current).toBe(false)
  })
})
```

### 2.3 Frontend Testing Tools & Dependencies

**Need to Add to `package.json`**:
```json
{
  "devDependencies": {
    // Testing Framework
    "vitest": "^2.1.0",
    "@vitejs/plugin-react": "^4.3.4",

    // Testing Library
    "@testing-library/react": "^16.1.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/user-event": "^14.5.2",

    // MSW (Mock Service Worker)
    "msw": "^2.6.8",

    // Coverage
    "@vitest/coverage-v8": "^2.1.0",

    // Utilities
    "jsdom": "^25.0.1"
  },
  "scripts": {
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage",
    "test:run": "vitest run"
  }
}
```

### 2.4 Frontend Test Execution

```bash
# Run tests in watch mode
npm test

# Run tests once (CI mode)
npm run test:run

# Run with UI
npm run test:ui

# Generate coverage report
npm run test:coverage

# Run specific test file
npm test -- pricing-tiers.test.ts
```

---

## 3. Mock Data Strategy

### 3.1 Contact Fixtures

**File**: `backend/tests/fixtures/contacts.py`

```python
SAMPLE_CONTACTS = [
    {
        "first_name": "Alice",
        "last_name": "Johnson",
        "email": "alice@example.com",
        "phone_number": "+15551111111",
        "company_name": "Tech Startup Inc",
        "status": "qualified",
        "tags": "enterprise,hot-lead",
    },
    {
        "first_name": "Bob",
        "last_name": "Smith",
        "phone_number": "+15552222222",
        "status": "new",
    },
    # ... 10-20 more samples
]
```

### 3.2 Audio Mock Data

**File**: `backend/tests/fixtures/audio.py`

```python
# Simple mock audio buffers for testing
MOCK_AUDIO_PCM = b'\x00\x01' * 1000  # Fake PCM data
MOCK_AUDIO_WAV_HEADER = b'RIFF...'  # Minimal WAV header

# Or load actual test audio file (very small, <10KB)
import pathlib
TEST_AUDIO_PATH = pathlib.Path(__file__).parent / "test_audio.wav"
```

### 3.3 Webhook Payloads

**File**: `backend/tests/fixtures/webhooks.py`

```python
TELNYX_INBOUND_CALL_WEBHOOK = {
    "data": {
        "event_type": "call.initiated",
        "id": "abc-123-def",
        "payload": {
            "call_control_id": "ctrl-123",
            "from": "+15551234567",
            "to": "+15559876543",
            "direction": "incoming",
            "state": "ringing"
        }
    }
}

DEEPGRAM_TRANSCRIPT_RESPONSE = {
    "channel": {
        "alternatives": [
            {
                "transcript": "Hello, I would like to schedule an appointment",
                "confidence": 0.98
            }
        ]
    }
}
```

### 3.4 Frontend Mock Data

**File**: `frontend/tests/mocks/data.ts`

```typescript
export const mockContacts = [
  {
    id: 1,
    user_id: 1,
    first_name: "John",
    last_name: "Doe",
    email: "john@example.com",
    phone_number: "+15551234567",
    company_name: "Acme Corp",
    status: "new",
    tags: "sales,vip",
    notes: "Interested in premium tier"
  },
  // ... more mock data
]

export const mockCRMStats = {
  total_contacts: 42,
  total_appointments: 15,
  total_calls: 103
}
```

---

## 4. Test Execution Order & CI Pipeline

### 4.1 Local Development

```bash
# Backend: Quick check (unit tests only, ~2-5 seconds)
cd backend && uv run pytest tests/unit/

# Backend: Full suite (~10-30 seconds)
cd backend && uv run pytest

# Frontend: Quick check
cd frontend && npm run test:run

# Full quality check (linting + types + tests)
make check  # If you have a Makefile
# OR
cd backend && uv run ruff check app && uv run mypy app && uv run pytest
cd frontend && npm run check && npm run test:run
```

### 4.2 CI Pipeline (GitHub Actions Example)

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: cd backend && uv sync --dev

      - name: Run linting
        run: cd backend && uv run ruff check app tests

      - name: Run type checking
        run: cd backend && uv run mypy app

      - name: Run tests
        run: cd backend && uv run pytest --cov --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./backend/coverage.xml

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        run: cd frontend && npm ci

      - name: Run linting
        run: cd frontend && npm run lint

      - name: Run type checking
        run: cd frontend && npm run type-check

      - name: Run tests
        run: cd frontend && npm run test:coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./frontend/coverage/lcov.info
```

### 4.3 Pre-commit Hook

**File**: `.pre-commit-config.yaml`

```yaml
repos:
  - repo: local
    hooks:
      - id: backend-tests
        name: Backend Unit Tests
        entry: bash -c 'cd backend && uv run pytest tests/unit/ -q'
        language: system
        pass_filenames: false

      - id: frontend-tests
        name: Frontend Tests
        entry: bash -c 'cd frontend && npm run test:run'
        language: system
        pass_filenames: false
```

---

## 5. Coverage Goals & Metrics

### 5.1 Backend Coverage Targets

| Component | Target Coverage | Priority |
|-----------|----------------|----------|
| Core (security, cache) | 95%+ | Critical |
| Models | 85%+ | High |
| API endpoints | 85%+ | High |
| Services (future) | 80%+ | High |
| Database utils | 75%+ | Medium |
| Overall | 80%+ | - |

### 5.2 Frontend Coverage Targets

| Component | Target Coverage | Priority |
|-----------|----------------|----------|
| Business logic (pricing) | 95%+ | Critical |
| Utilities | 90%+ | High |
| Hooks | 85%+ | High |
| Components (UI) | 70%+ | Medium |
| Pages | 60%+ | Medium |
| Overall | 70%+ | - |

### 5.3 Measuring Coverage

```bash
# Backend
cd backend
uv run pytest --cov=app --cov-report=html
open htmlcov/index.html

# Frontend
cd frontend
npm run test:coverage
open coverage/index.html
```

---

## 6. Key Testing Principles

### 6.1 AAA Pattern (Arrange-Act-Assert)

```python
# Good example
def test_create_contact():
    # Arrange: Set up test data
    contact_data = {"first_name": "John", "phone_number": "+15551234567"}

    # Act: Execute the operation
    response = client.post("/crm/contacts", json=contact_data)

    # Assert: Verify the outcome
    assert response.status_code == 201
    assert response.json()["first_name"] == "John"
```

### 6.2 Test Isolation

- Each test should be independent
- Use fixtures for setup/teardown
- Don't rely on test execution order
- Clean up database between tests

### 6.3 Mock at Boundaries

```python
# Mock external services, not internal logic
✅ Mock Redis, Deepgram, ElevenLabs
❌ Don't mock your own business logic

# Mock at the interface level
✅ Mock HTTP client responses
❌ Don't mock individual functions in your service
```

### 6.4 Test Names Should Be Descriptive

```python
# Good
def test_create_contact_returns_201_with_valid_data()
def test_create_contact_returns_422_when_phone_missing()

# Bad
def test_contact_creation()
def test_validation()
```

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Week 1)
- ✅ Set up backend test infrastructure (conftest.py)
- ✅ Add fakeredis dependency
- ✅ Create first unit tests (security, cache)
- ✅ Set up frontend Vitest
- ✅ Add MSW for API mocking
- ✅ Create first frontend tests (utils, pricing)

### Phase 2: Core Coverage (Week 2)
- ✅ Backend: All unit tests for core modules
- ✅ Backend: CRM API integration tests
- ✅ Frontend: Component tests for key UI elements
- ✅ Frontend: Hook tests
- ✅ Achieve 60%+ coverage

### Phase 3: Service Layer (Week 3-4)
- ✅ Mock Deepgram, ElevenLabs, OpenAI
- ✅ Mock Telnyx webhooks
- ✅ Test voice pipeline (when implemented)
- ✅ Test WebSocket handling
- ✅ Achieve 75%+ coverage

### Phase 4: Polish & Automation (Week 5)
- ✅ CI/CD pipeline setup
- ✅ Pre-commit hooks
- ✅ Coverage reporting
- ✅ Documentation
- ✅ Achieve 80%+ coverage

---

## 8. Example Test Commands Reference

```bash
# Backend - Run everything
cd backend && uv run pytest

# Backend - Unit tests only (fast)
cd backend && uv run pytest tests/unit/ -v

# Backend - Integration tests only
cd backend && uv run pytest tests/integration/ -v

# Backend - Specific test file
cd backend && uv run pytest tests/unit/test_security.py -v

# Backend - Specific test function
cd backend && uv run pytest tests/unit/test_security.py::test_create_access_token -v

# Backend - With coverage report
cd backend && uv run pytest --cov=app --cov-report=term-missing

# Backend - Parallel execution (faster)
cd backend && uv run pytest -n auto

# Frontend - Watch mode
cd frontend && npm test

# Frontend - Run once (CI)
cd frontend && npm run test:run

# Frontend - With coverage
cd frontend && npm run test:coverage

# Frontend - Specific test file
cd frontend && npm test -- pricing-tiers.test.ts

# Frontend - UI mode (visual test runner)
cd frontend && npm run test:ui
```

---

## 9. Troubleshooting Common Issues

### Backend

**Issue**: Tests fail with database connection errors
```bash
# Solution: Ensure test uses in-memory SQLite
# Check conftest.py uses: sqlite+aiosqlite:///:memory:
```

**Issue**: Redis connection errors
```bash
# Solution: Ensure fakeredis is installed and mocked
pip install fakeredis[aioredis]
```

**Issue**: Import errors in tests
```bash
# Solution: Run pytest from backend directory
cd backend && uv run pytest
```

### Frontend

**Issue**: Module not found errors
```bash
# Solution: Check vitest.config.ts has correct path alias
resolve: {
  alias: {
    '@': path.resolve(__dirname, './src'),
  },
}
```

**Issue**: MSW handlers not working
```bash
# Solution: Ensure server.listen() is called in setup.ts
# Check handlers are imported correctly
```

**Issue**: Tests fail with "window is not defined"
```bash
# Solution: Ensure vitest.config.ts sets environment: 'jsdom'
```

---

## 10. Next Steps

1. **Start Small**: Begin with backend unit tests for security and cache
2. **Build Incrementally**: Add tests as you develop new features
3. **Maintain Coverage**: Don't let coverage drop below targets
4. **Review Tests**: Treat test code with same quality standards as production code
5. **Document Patterns**: Keep this strategy updated as patterns evolve

---

## Appendix A: Additional Libraries to Consider

### Backend
- `pytest-xdist`: Parallel test execution
- `pytest-env`: Environment variable management
- `freezegun`: Mock datetime for time-sensitive tests
- `pytest-benchmark`: Performance testing
- `respx`: HTTP mocking for httpx client

### Frontend
- `@testing-library/react-hooks`: Testing hooks (now built into RTL)
- `playwright`: E2E testing (future phase)
- `axe-core/@axe-core/react`: Accessibility testing
- `@storybook/test-runner`: Visual regression testing

---

## Appendix B: File Tree Summary

```
voice-noob/
├── backend/
│   ├── tests/
│   │   ├── conftest.py                    # Main fixtures
│   │   ├── unit/                          # Pure unit tests
│   │   │   ├── test_security.py
│   │   │   ├── test_cache.py
│   │   │   ├── test_limiter.py
│   │   │   └── test_models.py
│   │   ├── integration/                   # API + DB tests
│   │   │   ├── conftest.py
│   │   │   ├── test_crm_api.py
│   │   │   └── test_health_api.py
│   │   ├── services/                      # Service tests (future)
│   │   │   ├── test_voice_pipeline.py
│   │   │   └── test_telephony.py
│   │   ├── fixtures/                      # Test data
│   │   │   ├── contacts.py
│   │   │   ├── appointments.py
│   │   │   └── audio.py
│   │   └── mocks/                         # Mock implementations
│   │       ├── mock_redis.py
│   │       ├── mock_deepgram.py
│   │       └── mock_elevenlabs.py
│   └── pyproject.toml                     # Add fakeredis
│
├── frontend/
│   ├── src/
│   │   └── __tests__/                     # Tests mirror src/
│   │       ├── lib/
│   │       │   ├── utils.test.ts
│   │       │   ├── pricing-tiers.test.ts
│   │       │   └── api.test.ts
│   │       ├── components/
│   │       │   └── tier-selector.test.tsx
│   │       └── hooks/
│   │           └── use-mobile.test.tsx
│   ├── tests/
│   │   ├── setup.ts                       # Vitest setup
│   │   ├── mocks/
│   │   │   ├── handlers.ts                # MSW handlers
│   │   │   ├── server.ts                  # MSW server
│   │   │   └── data.ts                    # Mock data
│   │   └── utils/
│   │       └── test-utils.tsx             # Custom render
│   ├── vitest.config.ts                   # Vitest config
│   └── package.json                       # Add test deps
│
├── .github/
│   └── workflows/
│       └── test.yml                       # CI pipeline
│
└── TEST_STRATEGY.md                       # This document
```

---

**Document Version**: 1.0
**Last Updated**: 2025-11-23
**Maintained By**: Development Team
