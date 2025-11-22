#!/bin/bash
set -e

echo "🔍 Running comprehensive backend checks..."
echo ""

echo "📝 Running Ruff linter..."
uv run ruff check app tests
echo "✓ Ruff linting passed"
echo ""

echo "✨ Checking code formatting..."
uv run ruff format --check app tests
echo "✓ Code formatting check passed"
echo ""

echo "🔬 Running mypy type checking..."
uv run mypy app
echo "✓ Type checking passed"
echo ""

echo "🧪 Running tests..."
uv run pytest
echo "✓ Tests passed"
echo ""

echo "✅ All backend checks passed successfully!"
