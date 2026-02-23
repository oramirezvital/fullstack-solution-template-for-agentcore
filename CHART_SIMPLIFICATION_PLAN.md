# Chart Generation Simplification Plan

## Problem
The current Chart.js MCP approach is too complex:
1. Lambda wraps Chart.js MCP server (requires Node.js + Python + native dependencies)
2. Returns HTML that agent wraps in code blocks
3. Frontend struggles to detect and render the HTML
4. Heavy Docker image with many dependencies
5. Difficult to debug and maintain

## Better Approach: JSON Data + Frontend Rendering

Instead of generating HTML on the backend, return structured JSON data and render charts in the frontend using a React charting library.

### Architecture

```
User: "Chart the 1-week price trend for AMAZON"
    ↓
Agent fetches data from Alpha Vantage
    ↓
Agent calls simple chart tool (Lambda or direct)
    ↓
Tool returns JSON:
{
  "type": "chart",
  "chartType": "line",
  "title": "Amazon Stock Price",
  "data": {
    "labels": ["Feb 11", "Feb 12", ...],
    "datasets": [{
      "label": "AMZN Price",
      "data": [204.08, 199.6, ...]
    }]
  }
}
    ↓
Frontend detects JSON chart data
    ↓
React Chart component renders interactive chart
```

### Benefits
1. **Simpler Lambda**: Just Python, no Node.js or native dependencies
2. **Smaller Docker image**: ~200MB vs ~800MB
3. **Better control**: Frontend has full control over chart styling
4. **Easier debugging**: JSON is easy to inspect
5. **More flexible**: Can easily add new chart types
6. **Consistent rendering**: Same chart library across all charts
7. **No HTML parsing**: Frontend directly consumes structured data

### Implementation Options

#### Option 1: Remove Gateway, Use Direct Tool (RECOMMENDED)
- Agent has a simple `generate_chart` tool (not via Gateway)
- Tool just validates and formats the chart data JSON
- Returns structured JSON in agent response
- Frontend detects JSON and renders with React charting library

**Pros:**
- Simplest approach
- No Gateway overhead
- No Lambda needed for chart generation
- Agent directly returns chart data

**Cons:**
- None significant

#### Option 2: Keep Gateway, Simplify Lambda
- Keep Gateway architecture
- Simplify Lambda to just return JSON (no Chart.js MCP)
- Frontend renders charts

**Pros:**
- Maintains Gateway pattern
- Still simpler than current approach

**Cons:**
- Still has Gateway overhead
- Lambda still needed (though simpler)

### Recommended Frontend Library

**Recharts** (https://recharts.org/)
- Built for React
- Declarative API
- Responsive by default
- Good TypeScript support
- Active maintenance
- ~100KB bundle size

Alternative: **Chart.js with react-chartjs-2**
- More features
- Larger community
- Slightly larger bundle

### Implementation Steps

1. **Remove Chart.js MCP Infrastructure**
   - Remove `gateway/tools/chart_tool/` directory
   - Remove Gateway chart tool from CDK stack
   - Remove Chart.js MCP from agent

2. **Add Simple Chart Data Formatter**
   - Create `patterns/utils/chart_formatter.py`
   - Validates chart data structure
   - Returns JSON in standardized format

3. **Update Agent System Prompt**
   - Remove Chart.js MCP instructions
   - Add instructions to return chart data as JSON
   - Provide JSON schema for chart data

4. **Install Recharts in Frontend**
   ```bash
   cd frontend
   npm install recharts
   ```

5. **Create Chart Component**
   - `frontend/src/components/chat/ChartRenderer.tsx`
   - Detects JSON chart data in messages
   - Renders using Recharts

6. **Update MarkdownRenderer**
   - Detect JSON chart data blocks
   - Pass to ChartRenderer component

### Chart Data JSON Schema

```json
{
  "type": "chart",
  "chartType": "line" | "bar" | "pie" | "area",
  "title": "Chart Title",
  "data": {
    "labels": ["Label 1", "Label 2", ...],
    "datasets": [{
      "label": "Dataset Name",
      "data": [value1, value2, ...],
      "color": "#3fb950"
    }]
  },
  "options": {
    "yAxisLabel": "Price (USD)",
    "xAxisLabel": "Date"
  }
}
```

### Example Agent Response

```
Based on the data from Alpha Vantage, here's the 1-week price trend for Amazon:

```json
{
  "type": "chart",
  "chartType": "line",
  "title": "Amazon (AMZN) - 1 Week Price Trend",
  "data": {
    "labels": ["Feb 11", "Feb 12", "Feb 13", "Feb 17", "Feb 18", "Feb 19", "Feb 20"],
    "datasets": [{
      "label": "AMZN Price (USD)",
      "data": [204.08, 199.6, 198.79, 201.15, 204.79, 204.86, 210.11],
      "color": "#3fb950"
    }]
  },
  "options": {
    "yAxisLabel": "Price (USD)",
    "xAxisLabel": "Date"
  }
}
```

The stock showed an overall upward trend, starting at $204.08 and closing at $210.11, 
representing a 2.95% increase over the week.
```

### Testing Plan

1. **Unit Tests**
   - Test chart data formatter
   - Test JSON schema validation

2. **Frontend Tests**
   - Test ChartRenderer with various data
   - Test chart type detection

3. **Integration Tests**
   - Test agent returns valid chart JSON
   - Test frontend renders charts correctly

### Rollback Plan

If issues occur:
1. Keep current Gateway infrastructure
2. Revert agent prompt changes
3. Frontend falls back to code block rendering

### Timeline

- Remove Gateway chart tool: 10 minutes
- Create chart formatter utility: 15 minutes
- Update agent prompt: 10 minutes
- Install Recharts: 2 minutes
- Create ChartRenderer component: 30 minutes
- Update MarkdownRenderer: 15 minutes
- Test and deploy: 20 minutes

**Total: ~2 hours**

## Decision Required

Should we proceed with Option 1 (Remove Gateway, use direct JSON) or Option 2 (Keep Gateway, simplify Lambda)?

**Recommendation: Option 1** - Simplest, most maintainable, no infrastructure overhead.
