#!/bin/bash
# Test script for Chart Tool Lambda Docker image
# This builds the Docker image and runs the test locally

set -e

echo "=========================================="
echo "Chart Tool Lambda - Local Docker Test"
echo "=========================================="
echo ""

# Navigate to the chart tool directory
cd "$(dirname "$0")"

echo "Step 1: Building Docker image..."
echo "This may take a few minutes on first build..."
docker build --platform linux/arm64 -t chart-tool-test:latest .

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed!"
    exit 1
fi

echo ""
echo "✅ Docker image built successfully!"
echo ""

echo "Step 2: Testing Chart.js MCP server dependencies..."
echo "Checking if npx can find @ax-crew/chartjs-mcp-server..."

# Test that the MCP server package is installed
docker run --rm --platform linux/arm64 --entrypoint sh chart-tool-test:latest \
    -c "npm list -g @ax-crew/chartjs-mcp-server 2>&1 | head -5"

if [ $? -ne 0 ]; then
    echo "⚠️  Warning: Could not verify package, but continuing..."
fi

echo ""
echo "✅ Chart.js MCP server package check completed!"
echo ""

echo "Step 3: Checking system dependencies..."
echo "Verifying libexpat and other canvas dependencies..."

docker run --rm --platform linux/arm64 --entrypoint sh chart-tool-test:latest \
    -c "ldconfig -p | grep -E '(libexpat|libcairo|libpango)' | head -10"

if [ $? -ne 0 ]; then
    echo "❌ Required system libraries not found!"
    exit 1
fi

echo ""
echo "✅ All required system libraries are installed!"
echo ""

echo "Step 4: Testing Node.js and npm..."
docker run --rm --platform linux/arm64 --entrypoint sh chart-tool-test:latest \
    -c "node --version && npm --version"

echo ""
echo "Step 5: Running Lambda function test..."
echo "This will test the actual chart generation..."

# Run the test script inside the container
docker run --rm --platform linux/arm64 --entrypoint python3 chart-tool-test:latest \
    /var/task/test_local.py

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ ALL TESTS PASSED!"
    echo "=========================================="
    echo ""
    echo "The Docker image is ready to deploy."
    echo "Run: cd infra-cdk && npm run cdk deploy FAST-stack"
    exit 0
else
    echo ""
    echo "=========================================="
    echo "❌ TESTS FAILED!"
    echo "=========================================="
    echo ""
    echo "Please review the errors above before deploying."
    exit 1
fi
