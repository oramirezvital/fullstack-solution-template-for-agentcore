# Investment Advisor Agent - Test Plan

## Deployment Status
✅ Agent deployed successfully (Feb 23, 2026)
✅ Chart.js MCP client integrated (stdio transport)
✅ Frontend configured to render Chart.js HTML output

## Current Issue
Agent was not responding after previous deployment attempt. The issue was that the code wasn't deployed yet - it has now been deployed.

## Test Cases

### 1. Basic Functionality Test
**Query**: "Hello, can you help me with investment advice?"
**Expected**: Agent responds with greeting and confirms capabilities

### 2. Alpha Vantage Data Test
**Query**: "What is the current price of Amazon stock?"
**Expected**: Agent fetches AMZN price using Alpha Vantage GLOBAL_QUOTE tool

### 3. Chart.js Visualization Test
**Query**: "Chart the 1-week price trend for AMAZON"
**Expected**: 
- Agent fetches data using Alpha Vantage TIME_SERIES_DAILY
- Agent calls chartjs_generateChart with proper JSON object (NOT string)
- Frontend displays interactive HTML chart
- No "TypeError: Error in input stream" errors

### 4. Chart.js Configuration Format
**Critical**: The LLM must pass `chartConfig` as a JSON object, NOT as a JSON string
- ❌ WRONG: `chartConfig="{\"type\": \"line\", ...}"`
- ✅ RIGHT: `chartConfig={"type": "line", ...}`

## Known Issues

### Issue 1: LLM Passing JSON String Instead of Object
**Problem**: The LLM keeps passing `chartConfig` as a JSON string instead of an object, causing "TypeError: Error in input stream"

**Root Cause**: The Chart.js MCP server expects a JSON object but receives a string

**Attempted Solutions**:
1. ❌ Added wrapper to auto-parse JSON strings - broke agent (no response)
2. ✅ Removed wrapper, reverted to simple MCP client
3. 📝 Updated system prompt with explicit instructions to pass objects

**Current Status**: Deployed with clear instructions in system prompt. If issue persists, consider:
- Using Code Interpreter to generate charts instead of Chart.js MCP
- Creating a custom MCP wrapper that handles string-to-object conversion server-side
- Simplifying chart generation to avoid complex configurations

## Next Steps

1. Test basic agent functionality (confirm it responds)
2. Test Alpha Vantage data fetching
3. Test Chart.js visualization with simple query
4. If Chart.js still fails with string input, evaluate alternatives:
   - Code Interpreter with matplotlib/plotly
   - Custom MCP wrapper with JSON parsing
   - Simplified chart generation approach

## Frontend URLs
- Production: https://main.d3f65gfpy3izg4.amplifyapp.com
- Stack: FAST-stack
- Region: us-east-1

## Environment Variables
- ALPHA_VANTAGE_API_KEY: 6I7SGM9D7G40YB1I
- MEMORY_ID: Set in CDK stack
- AWS_DEFAULT_REGION: us-east-1
