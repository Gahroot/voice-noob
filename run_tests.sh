#!/bin/bash

# Voice Agent Platform - Test Runner Script
# This script runs all tests without requiring real credentials

set -e  # Exit on error

BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BOLD}Voice Agent Platform - Test Suite${NC}"
echo "Running all tests without real credentials..."
echo ""

# Track overall success
BACKEND_SUCCESS=true
FRONTEND_SUCCESS=true

# Backend Tests
echo -e "${BOLD}=== Backend Tests ===${NC}"
cd backend

echo "Running linting..."
if uv run ruff check app tests; then
    echo -e "${GREEN}✓ Linting passed${NC}"
else
    echo -e "${RED}✗ Linting failed${NC}"
    BACKEND_SUCCESS=false
fi

echo ""
echo "Running type checking..."
if uv run mypy app; then
    echo -e "${GREEN}✓ Type checking passed${NC}"
else
    echo -e "${RED}✗ Type checking failed${NC}"
    BACKEND_SUCCESS=false
fi

echo ""
echo "Running unit tests..."
if uv run pytest tests/unit/ -v; then
    echo -e "${GREEN}✓ Unit tests passed${NC}"
else
    echo -e "${RED}✗ Unit tests failed${NC}"
    BACKEND_SUCCESS=false
fi

echo ""
echo "Running integration tests..."
if uv run pytest tests/integration/ -v; then
    echo -e "${GREEN}✓ Integration tests passed${NC}"
else
    echo -e "${RED}✗ Integration tests failed${NC}"
    BACKEND_SUCCESS=false
fi

echo ""
echo "Generating coverage report..."
if uv run pytest --cov=app --cov-report=term-missing --cov-report=html; then
    echo -e "${GREEN}✓ Coverage report generated (see backend/htmlcov/index.html)${NC}"
else
    echo -e "${YELLOW}⚠ Coverage report failed (tests may have failed)${NC}"
fi

cd ..

# Frontend Tests
echo ""
echo -e "${BOLD}=== Frontend Tests ===${NC}"
cd frontend

# Check if test dependencies are installed
if ! npm list vitest > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Frontend test dependencies not installed${NC}"
    echo "Run: cd frontend && npm install --save-dev vitest @vitejs/plugin-react @testing-library/react @testing-library/jest-dom @testing-library/user-event msw @vitest/coverage-v8 jsdom"
    FRONTEND_SUCCESS=false
else
    echo "Running linting..."
    if npm run lint; then
        echo -e "${GREEN}✓ Linting passed${NC}"
    else
        echo -e "${RED}✗ Linting failed${NC}"
        FRONTEND_SUCCESS=false
    fi

    echo ""
    echo "Running type checking..."
    if npm run type-check; then
        echo -e "${GREEN}✓ Type checking passed${NC}"
    else
        echo -e "${RED}✗ Type checking failed${NC}"
        FRONTEND_SUCCESS=false
    fi

    echo ""
    echo "Running tests..."
    if npm run test:run; then
        echo -e "${GREEN}✓ Frontend tests passed${NC}"
    else
        echo -e "${RED}✗ Frontend tests failed${NC}"
        FRONTEND_SUCCESS=false
    fi

    echo ""
    echo "Generating coverage report..."
    if npm run test:coverage -- --run; then
        echo -e "${GREEN}✓ Coverage report generated (see frontend/coverage/index.html)${NC}"
    else
        echo -e "${YELLOW}⚠ Coverage report failed (tests may have failed)${NC}"
    fi
fi

cd ..

# Summary
echo ""
echo -e "${BOLD}=== Test Summary ===${NC}"

if [ "$BACKEND_SUCCESS" = true ]; then
    echo -e "${GREEN}✓ Backend: All checks passed${NC}"
else
    echo -e "${RED}✗ Backend: Some checks failed${NC}"
fi

if [ "$FRONTEND_SUCCESS" = true ]; then
    echo -e "${GREEN}✓ Frontend: All checks passed${NC}"
else
    echo -e "${RED}✗ Frontend: Some checks failed${NC}"
fi

echo ""

if [ "$BACKEND_SUCCESS" = true ] && [ "$FRONTEND_SUCCESS" = true ]; then
    echo -e "${GREEN}${BOLD}🎉 All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}${BOLD}❌ Some tests failed. Please fix the issues above.${NC}"
    exit 1
fi
