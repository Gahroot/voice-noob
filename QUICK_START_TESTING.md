# Quick Start Guide: Testing Without Real Credentials

This guide will get you up and running with tests in 5 minutes.

## Prerequisites

1. Backend already has pytest and testing tools installed
2. Frontend needs test framework (instructions below)

---

## Backend Testing - Ready to Use!

### 1. Install Dependencies (if not already done)

```bash
cd backend
uv sync --dev
```

### 2. Run Your First Tests

```bash
# Run security tests (should pass immediately)
uv run pytest tests/unit/test_security.py -v

# Run CRM API tests (should pass immediately)
uv run pytest tests/integration/test_crm_api.py -v

# Run all tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=app --cov-report=html
```

### 3. What's Already Set Up

✅ In-memory SQLite database (no PostgreSQL needed)
✅ Fake Redis (no Redis server needed)
✅ Test fixtures for contacts, users, appointments
✅ Factory functions to create test data
✅ HTTP test client with dependency overrides

### 4. Example: Create Your First Test

**File**: `backend/tests/unit/test_my_feature.py`

```python
"""Test my feature."""

import pytest


def test_simple_function() -> None:
    """Test a simple pure function."""
    # Arrange
    input_value = 5

    # Act
    result = input_value * 2

    # Assert
    assert result == 10


@pytest.mark.asyncio
async def test_with_database(test_session, create_test_contact) -> None:
    """Test with database access."""
    # Arrange: Create test data
    contact = await create_test_contact(
        first_name="Alice",
        phone_number="+15551111111"
    )

    # Act: Query the database
    from app.models.contact import Contact
    from sqlalchemy import select

    result = await test_session.execute(
        select(Contact).where(Contact.id == contact.id)
    )
    found_contact = result.scalar_one_or_none()

    # Assert
    assert found_contact is not None
    assert found_contact.first_name == "Alice"
```

---

## Frontend Testing - Setup Required

### 1. Install Test Dependencies

```bash
cd frontend

# Install Vitest and testing tools
npm install --save-dev \
  vitest \
  @vitejs/plugin-react \
  @testing-library/react \
  @testing-library/jest-dom \
  @testing-library/user-event \
  msw \
  @vitest/coverage-v8 \
  jsdom
```

### 2. Update package.json Scripts

Add these to your `package.json`:

```json
{
  "scripts": {
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage",
    "test:run": "vitest run"
  }
}
```

### 3. Run Your First Tests

```bash
# Run tests in watch mode
npm test

# Run tests once (CI mode)
npm run test:run

# Run with coverage
npm run test:coverage

# Run specific test file
npm test -- pricing-tiers.test.ts
```

### 4. What's Already Set Up

✅ Vitest configuration with jsdom environment
✅ MSW (Mock Service Worker) for API mocking
✅ Mock data for contacts and CRM stats
✅ Test utilities with React Query provider
✅ Example tests for pricing calculations

### 5. Example: Create Your First Frontend Test

**File**: `frontend/src/__tests__/components/my-component.test.tsx`

```typescript
import { describe, test, expect } from 'vitest'
import { render, screen } from '@/tests/utils/test-utils'
import MyComponent from '@/components/my-component'

describe('MyComponent', () => {
  test('renders correctly', () => {
    render(<MyComponent title="Test" />)

    expect(screen.getByText('Test')).toBeInTheDocument()
  })

  test('handles click events', async () => {
    const { user } = render(<MyComponent />)

    const button = screen.getByRole('button')
    await user.click(button)

    expect(screen.getByText('Clicked!')).toBeInTheDocument()
  })
})
```

---

## Common Testing Patterns

### Backend: Test an API Endpoint

```python
@pytest.mark.asyncio
async def test_create_contact_api(test_client):
    """Test POST /crm/contacts endpoint."""
    contact_data = {
        "first_name": "John",
        "phone_number": "+15551234567",
    }

    response = await test_client.post("/crm/contacts", json=contact_data)

    assert response.status_code == 201
    assert response.json()["first_name"] == "John"
```

### Backend: Test with Mock Redis

```python
@pytest.mark.asyncio
async def test_caching(test_redis):
    """Test Redis caching."""
    # Set a value
    await test_redis.set("test_key", "test_value")

    # Get the value
    value = await test_redis.get("test_key")

    assert value == "test_value"
```

### Frontend: Test Component with API Call

```typescript
import { render, screen, waitFor } from '@/tests/utils/test-utils'

test('loads and displays contacts', async () => {
  render(<ContactList />)

  // Wait for API call to complete
  await waitFor(() => {
    expect(screen.getByText('John Doe')).toBeInTheDocument()
  })

  // MSW will automatically return mock data from tests/mocks/handlers.ts
})
```

### Frontend: Test User Interaction

```typescript
import { render, screen } from '@/tests/utils/test-utils'
import userEvent from '@testing-library/user-event'

test('submits form when button clicked', async () => {
  const user = userEvent.setup()
  render(<ContactForm />)

  await user.type(screen.getByLabelText('Name'), 'John Doe')
  await user.click(screen.getByRole('button', { name: 'Submit' }))

  await waitFor(() => {
    expect(screen.getByText('Success!')).toBeInTheDocument()
  })
})
```

---

## Debugging Tests

### Backend

```bash
# Run with verbose output
uv run pytest -vv

# Run with print statements visible
uv run pytest -s

# Run specific test and stop on first failure
uv run pytest tests/unit/test_security.py::test_verify_password_correct -x

# Run with debugger (pdb)
uv run pytest --pdb
```

### Frontend

```bash
# Run with UI (visual test runner)
npm run test:ui

# Run in watch mode (auto-reruns on file changes)
npm test

# Debug specific test
npm test -- pricing-tiers.test.ts -t "should calculate budget tier"
```

---

## Common Issues & Solutions

### Backend

**Issue**: `ImportError: cannot import name 'X'`
- **Solution**: Make sure you're running pytest from `backend/` directory
- **Fix**: `cd backend && uv run pytest`

**Issue**: `Database locked` error
- **Solution**: Tests are trying to use real database instead of in-memory
- **Fix**: Check that `conftest.py` is using `sqlite+aiosqlite:///:memory:`

**Issue**: Tests fail with Redis connection error
- **Solution**: fakeredis dependency missing
- **Fix**: `cd backend && uv sync --dev` (already includes fakeredis)

### Frontend

**Issue**: `Cannot find module '@/...'`
- **Solution**: Path alias not configured in vitest.config.ts
- **Fix**: Check that `resolve.alias['@']` points to `./src`

**Issue**: `window is not defined`
- **Solution**: Missing jsdom environment
- **Fix**: Ensure `vitest.config.ts` has `environment: 'jsdom'`

**Issue**: MSW handlers not intercepting requests
- **Solution**: Server not started in setup
- **Fix**: Check `tests/setup.ts` calls `server.listen()`

---

## Quick Test Checklist

Before committing code:

- [ ] Backend: `cd backend && uv run pytest`
- [ ] Backend: `cd backend && uv run ruff check app tests`
- [ ] Backend: `cd backend && uv run mypy app`
- [ ] Frontend: `cd frontend && npm run test:run`
- [ ] Frontend: `cd frontend && npm run lint`
- [ ] Frontend: `cd frontend && npm run type-check`

Or use the shortcut:

```bash
# Backend
cd backend && uv run ruff check app tests && uv run mypy app && uv run pytest

# Frontend
cd frontend && npm run check && npm run test:run
```

---

## Next Steps

1. **Read**: See `TEST_STRATEGY.md` for comprehensive testing strategy
2. **Practice**: Add tests for your features as you develop them
3. **Coverage**: Run `pytest --cov` (backend) or `npm run test:coverage` (frontend)
4. **CI**: Set up GitHub Actions to run tests on every push

---

## Resources

- **Backend Test Examples**: `backend/tests/unit/test_security.py`
- **Backend API Tests**: `backend/tests/integration/test_crm_api.py`
- **Frontend Tests**: `frontend/src/__tests__/lib/pricing-tiers.test.ts`
- **Test Fixtures**: `backend/tests/conftest.py`
- **Mock Data**: `frontend/tests/mocks/data.ts`

**Happy Testing!** 🎉
