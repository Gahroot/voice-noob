---
name: update-app
description: Update dependencies, fix deprecations and security issues
---

# Dependency Update & Deprecation Fix

This command updates all dependencies in both frontend (npm) and backend (uv), fixes deprecations, and ensures zero warnings.

## Step 1: Check for Updates

### Backend (Python with uv):
```bash
cd backend
uv lock --upgrade
uv tree --outdated
```

### Frontend (JavaScript with npm):
```bash
cd frontend
npm outdated
```

## Step 2: Update Dependencies

### Backend:
```bash
cd backend
uv sync --upgrade --all-extras
```

### Frontend:
```bash
cd frontend
npm update
npm audit fix
```

## Step 3: Check for Deprecations & Warnings

Run installation and **READ ALL OUTPUT CAREFULLY**:

### Backend:
```bash
cd backend
rm -rf .venv
uv sync --all-extras
```

Look for:
- Deprecation warnings
- Security vulnerabilities
- Package conflicts
- Python version warnings

### Frontend:
```bash
cd frontend
rm -rf node_modules package-lock.json .next
npm install
```

Look for:
- Deprecation warnings (npm WARN deprecated)
- Security vulnerabilities (npm audit)
- Peer dependency warnings
- Next.js/React version conflicts

## Step 4: Fix All Issues

**ZERO-TOLERANCE POLICY**: Fix ALL warnings and deprecations before proceeding.

For each warning:
1. Research the recommended replacement
2. Update dependencies or code
3. Re-run installation
4. Verify warning is gone

Common fixes:
- Update deprecated packages to latest versions
- Replace deprecated APIs with new ones
- Fix peer dependency mismatches
- Update breaking changes per migration guides

## Step 5: Run Quality Checks

### Backend:
```bash
cd backend
uv run ruff check app
uv run mypy app
uv run pytest
```

Fix all errors before proceeding.

### Frontend:
```bash
cd frontend
npm run lint
npm run type-check
npm run build
```

Fix all errors before proceeding.

## Step 6: Verify Clean Install & Zero Warnings

### Backend:
```bash
cd backend
rm -rf .venv
uv sync --all-extras 2>&1 | tee install-log.txt
```

Verify:
- ✅ No deprecation warnings
- ✅ No security vulnerabilities
- ✅ All packages resolve
- ✅ Clean output

### Frontend:
```bash
cd frontend
rm -rf node_modules package-lock.json .next
npm install 2>&1 | tee install-log.txt
```

Verify:
- ✅ 0 vulnerabilities
- ✅ No deprecation warnings
- ✅ No peer dependency warnings
- ✅ Clean install

## Step 7: Test Servers

Start both servers and verify they run without warnings:

### Backend:
```bash
cd backend
uv run uvicorn app.main:app --reload
```

Check for runtime warnings.

### Frontend:
```bash
cd frontend
npm run dev
```

Check for:
- No Fast Refresh errors
- No compilation warnings
- No runtime warnings

## Step 8: Commit Changes

Once everything is clean:

```bash
git add backend/pyproject.toml backend/uv.lock frontend/package.json frontend/package-lock.json
git commit -m "chore: update dependencies and fix deprecations

- Updated all backend dependencies (uv)
- Updated all frontend dependencies (npm)
- Fixed all deprecation warnings
- Resolved security vulnerabilities
- Verified zero warnings on fresh install
"
git push
```

## Success Criteria

- ✅ All dependencies updated
- ✅ Zero deprecation warnings (backend + frontend)
- ✅ Zero security vulnerabilities
- ✅ All quality checks passing (lint, typecheck, tests)
- ✅ Clean install with no warnings
- ✅ Servers start without warnings
- ✅ Changes committed and pushed

**IMPORTANT**: Do not mark complete until ALL criteria are met!
