# Quality Checks & Type Safety Configuration

Complete setup for comprehensive linting, type checking, and code quality across the entire project.

## ✅ Backend (Python/FastAPI)

### Linting with Ruff
**Configuration**: `backend/pyproject.toml`

Comprehensive rule coverage including:
- **Code Quality**: pycodestyle (E, W), pyflakes (F), isort (I)
- **Best Practices**: flake8-bugbear (B), comprehensions (C4), pyupgrade (UP)
- **Security**: flake8-bandit (S) - hardcoded passwords, SQL injection, etc.
- **Async**: flake8-async (ASYNC) - proper async/await usage
- **Type Checking**: flake8-type-checking (TCH)
- **Complexity**: mccabe (C90), pylint (PL)
- **Error Handling**: tryceratops (TRY)
- **And 30+ other rule sets** for comprehensive coverage

**Run checks**:
```bash
cd backend
uv run ruff check app tests           # Lint
uv run ruff check app tests --fix     # Auto-fix
uv run ruff format app tests          # Format code
```

### Type Checking with mypy
**Configuration**: `backend/pyproject.toml`

Strictest TypeScript-like type checking:
- `strict = true` - Maximum type safety
- `disallow_untyped_defs` - All functions must have types
- `disallow_any_generics` - No bare generic types
- `warn_return_any` - Warn on `Any` returns
- `no_implicit_optional` - Explicit Optional types
- `warn_unreachable` - Dead code detection
- `strict_equality` - Type-safe comparisons

**Run checks**:
```bash
cd backend
uv run mypy app
```

### Testing
**Configuration**: `backend/pyproject.toml`

- pytest with async support
- Coverage reporting
- Strict markers

**Run tests**:
```bash
cd backend
uv run pytest
uv run pytest --cov=app --cov-report=html
```

### Pre-commit Hooks
**Configuration**: `backend/.pre-commit-config.yaml`

Automatically runs on git commit:
- Trailing whitespace removal
- End-of-file fixer
- YAML/TOML validation
- Ruff linting and formatting
- mypy type checking

**Install hooks**:
```bash
cd backend
uv run pre-commit install
uv run pre-commit run --all-files  # Test all files
```

### Run All Backend Checks
```bash
cd backend
bash scripts/check.sh
```

This runs:
1. Ruff linter (40+ rule sets)
2. Ruff formatter check
3. mypy type checking (strict mode)
4. pytest with coverage

## ✅ Frontend (TypeScript/Next.js)

### ESLint Configuration
**Configuration**: `frontend/.eslintrc.json`

Comprehensive TypeScript + React rules:
- **TypeScript**: Full @typescript-eslint ruleset
  - No explicit `any`
  - Proper async/await usage
  - No floating promises
  - Prefer nullish coalescing (`??`)
  - Require await for async functions
- **React**: Hook rules, no prop-types
- **Code Quality**: No console (except warn/error), no debugger

**Run checks**:
```bash
cd frontend
npm run lint
npm run lint:fix  # Auto-fix
```

### TypeScript Configuration
**Configuration**: `frontend/tsconfig.json`

Strictest possible TypeScript settings:
- `strict: true` - All strict checks enabled
- `noImplicitAny` - No implicit any types
- `strictNullChecks` - Proper null/undefined handling
- `strictFunctionTypes` - Type-safe functions
- `noUnusedLocals` - No unused variables
- `noUnusedParameters` - No unused parameters
- `noImplicitReturns` - All code paths return
- `noFallthroughCasesInSwitch` - No fallthrough in switch
- `noUncheckedIndexedAccess` - Array access safety
- `noImplicitOverride` - Explicit override keyword

**Run checks**:
```bash
cd frontend
npm run type-check
```

### Prettier Formatting
**Configuration**: `frontend/.prettierrc`

- Consistent code formatting
- Auto-sorts Tailwind classes
- 100 character line length
- Double quotes, semicolons

**Run checks**:
```bash
cd frontend
npm run format        # Format code
npm run format:check  # Check formatting
```

### Run All Frontend Checks
```bash
cd frontend
npm run check
```

Or:
```bash
cd frontend
bash scripts/check.sh
```

This runs:
1. ESLint (TypeScript + React rules)
2. TypeScript type checking (strict mode)
3. Prettier formatting check
4. Production build test

## ✅ Run All Checks (Backend + Frontend)

From project root:

```bash
make check
```

Or:

```bash
bash scripts/check-all.sh
```

This runs comprehensive checks on both backend and frontend.

## Available Make Commands

```bash
make help              # Show all commands
make check             # Run all quality checks
make check-backend     # Run backend checks only
make check-frontend    # Run frontend checks only
make lint              # Run linters
make format            # Format code
make test              # Run tests
```

## Development Workflow

### 1. Before Committing

```bash
# Backend
cd backend
uv run ruff check app --fix
uv run ruff format app
uv run mypy app

# Frontend
cd frontend
npm run lint:fix
npm run format
npm run type-check
```

### 2. Or Use Make

```bash
make format  # Auto-format everything
make check   # Run all checks
```

### 3. Automated via Pre-commit

Install pre-commit hooks (backend only for now):
```bash
cd backend
uv run pre-commit install
```

Now checks run automatically on `git commit`.

## Configuration Files

### Backend
- `backend/pyproject.toml` - Ruff, mypy, pytest configuration
- `backend/.pre-commit-config.yaml` - Git hooks
- `backend/scripts/check.sh` - Run all checks

### Frontend
- `frontend/.eslintrc.json` - ESLint rules
- `frontend/tsconfig.json` - TypeScript compiler options
- `frontend/.prettierrc` - Code formatting
- `frontend/package.json` - npm scripts
- `frontend/scripts/check.sh` - Run all checks

### Root
- `Makefile` - Convenient shortcuts
- `scripts/check-all.sh` - Run everything

## Type Safety Highlights

### Backend (Python)
- ✅ Strict mypy checking - no implicit Any
- ✅ All functions fully typed
- ✅ Pydantic models for runtime validation
- ✅ SQLAlchemy typed ORM queries
- ✅ FastAPI automatic request/response validation

### Frontend (TypeScript)
- ✅ Strict TypeScript compiler
- ✅ No implicit any allowed
- ✅ All array access checked
- ✅ No unused variables/parameters
- ✅ Exhaustive switch statements
- ✅ Proper null/undefined handling

## Security & Code Quality

### Backend
- ✅ Bandit security scanning (flake8-bandit)
- ✅ Hardcoded password detection
- ✅ SQL injection prevention
- ✅ Async best practices enforcement
- ✅ Complexity limits (mccabe)

### Frontend
- ✅ No unsafe any usage
- ✅ Promise handling enforced
- ✅ React hooks rules
- ✅ No console.log in production code
- ✅ TypeScript strict mode

## CI/CD Ready

All checks can be run in CI/CD:

```yaml
# Example GitHub Actions
- name: Backend Checks
  run: |
    cd backend
    uv sync --all-extras
    bash scripts/check.sh

- name: Frontend Checks
  run: |
    cd frontend
    npm ci
    npm run check
```

## Summary

**Backend**: Ruff (40+ rules) + mypy (strictest) + pytest + pre-commit
**Frontend**: ESLint (TypeScript strict) + tsc (strict) + Prettier + build test

**Result**: Enterprise-grade type safety and code quality! 🚀
