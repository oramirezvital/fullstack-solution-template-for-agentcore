# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Dockerfile for Chart Tool Lambda
# This Lambda wraps the Chart.js MCP server to provide chart generation
# capabilities through the AgentCore Gateway

FROM public.ecr.aws/lambda/python:3.13

# Install Node.js 20.x and canvas dependencies for Chart.js MCP server
# Node.js is required to run the Chart.js MCP server via npx
# Canvas package requires: cairo, pango, libjpeg, giflib, librsvg, expat
# AWS Lambda Python images already have curl-minimal, so we just need tar and gzip
RUN microdnf install -y \
    tar \
    gzip \
    cairo \
    pango \
    libjpeg-turbo \
    giflib \
    librsvg2 \
    expat && \
    curl -fsSL https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-arm64.tar.gz -o node.tar.gz && \
    tar -xzf node.tar.gz -C /usr/local --strip-components=1 && \
    rm node.tar.gz && \
    microdnf clean all

# Verify Node.js and npm installation
RUN node --version && npm --version

# Install Chart.js MCP server globally
# This makes the @ax-crew/chartjs-mcp-server package available via npx
RUN npm install -g @ax-crew/chartjs-mcp-server

# Copy requirements and install Python dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy Lambda function code
COPY chart_tool_lambda.py ${LAMBDA_TASK_ROOT}/

# Copy test script for local testing (optional, not used in production)
COPY test_local.py ${LAMBDA_TASK_ROOT}/

# Set HOME to /tmp so npm can create cache directories
# Lambda's /tmp directory is writable, unlike the default home directory
ENV HOME=/tmp

# Set the Lambda handler
CMD ["chart_tool_lambda.lambda_handler"]
