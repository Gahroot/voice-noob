#!/bin/bash
set -e

echo "🔍 Running comprehensive frontend checks..."
echo ""

echo "📝 Running ESLint..."
npm run lint
echo "✓ ESLint passed"
echo ""

echo "🔬 Running TypeScript type checking..."
npm run type-check
echo "✓ Type checking passed"
echo ""

echo "✨ Checking code formatting..."
npm run format:check
echo "✓ Code formatting check passed"
echo ""

echo "🏗️  Testing production build..."
npm run build
echo "✓ Build successful"
echo ""

echo "✅ All frontend checks passed successfully!"
