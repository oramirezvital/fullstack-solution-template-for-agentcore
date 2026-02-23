# Chart Generation - Debug Status

## Current Issue

Charts are not rendering in the frontend. The agent is returning chart JSON, but it's not being detected and rendered.

## Root Causes Identified

### 1. Agent Behavior ✅ PARTIALLY FIXED
- **Issue**: Agent was using Code Interpreter to generate chart JSON, which appeared in tool output (gray box) instead of agent's message text
- **Fix Applied**: Updated agent prompt to explicitly instruct including JSON in response text
- **Status**: Agent now includes JSON in response, but not using proper code fence format
- **Current Output**: `json{...}` instead of ` ```json\n{...}\n``` `

### 2. Frontend Detection ✅ FIXED (pending deployment)
- **Issue**: Regex wasn't catching nested JSON objects
- **Fix Applied**: Implemented brace-counting algorithm to extract complete JSON
- **Status**: Code committed and pushed, waiting for Amplify deployment
- **File**: `frontend/src/components/chat/MarkdownRenderer.tsx`

### 3. Amplify Deployment ⏳ IN PROGRESS
- **Issue**: Updated frontend code not deployed yet
- **Evidence**: No `[MarkdownRenderer]` debug logs in console
- **File hash**: Still showing old version `index-DkSQnhLO.js`
- **Action**: Wait for Amplify to complete deployment (3-5 minutes)

## What's Working

✅ Agent fetches data from Alpha Vantage  
✅ Agent processes data with Code Interpreter  
✅ Agent includes chart JSON in response text  
✅ ChartRenderer component created with Recharts  
✅ TypeScript compilation passes  
✅ Backend deployed successfully  

## What's Not Working

❌ Agent not using proper markdown code fence (writes `json{` instead of ` ```json `)  
❌ Frontend detection not active (old version still deployed)  
❌ Charts not rendering  

## Next Steps

### Immediate (waiting for Amplify)
1. Wait for Amplify to deploy updated frontend
2. Hard refresh browser (Ctrl+Shift+R / Cmd+Shift+R)
3. Check console for `[MarkdownRenderer]` logs
4. Verify chart detection is working

### If Detection Works But No Chart
- Check ChartRenderer component for errors
- Verify Recharts is properly imported
- Check browser console for React errors

### If Detection Still Doesn't Work
- Agent prompt needs further refinement
- May need to add explicit example with actual backticks
- Consider alternative: detect `json{` pattern specifically

## Testing Checklist

After Amplify deployment completes:

- [ ] Hard refresh browser
- [ ] Check console shows `[MarkdownRenderer]` logs
- [ ] Verify log shows "Valid chart found"
- [ ] Verify log shows "Total charts found: 1"
- [ ] Check if chart renders
- [ ] If chart renders, test different chart types
- [ ] If no chart, check for React/Recharts errors

## Alternative Solutions if Current Approach Fails

### Option A: Detect `json{` Pattern
Instead of requiring proper code fence, detect the literal string `json{` that the agent is currently producing:

```typescript
// Look for "json{" pattern (agent's current output)
if (content.includes('json{')) {
  const startIndex = content.indexOf('json{') + 4; // Skip "json"
  // Extract JSON using brace counting from startIndex
}
```

### Option B: Use Few-Shot Examples
Add actual successful chart examples to agent's context so it learns the exact format.

### Option C: Post-Process Agent Response
Create a backend post-processor that:
1. Detects chart JSON in agent response
2. Wraps it in proper code fence
3. Returns modified response to frontend

## Files Modified

### Backend
- `patterns/strands-single-agent/basic_agent.py` - Agent system prompt
- `patterns/utils/chart_formatter.py` - Chart data validation (created)

### Frontend  
- `frontend/src/components/chat/MarkdownRenderer.tsx` - JSON detection logic
- `frontend/src/components/chat/ChartRenderer.tsx` - Chart rendering component
- `frontend/package.json` - Added recharts dependency

### Infrastructure
- `infra-cdk/lib/backend-stack.ts` - Commented out Gateway chart tool (preserved for future)

## Deployment Status

| Component | Status | Version |
|-----------|--------|---------|
| Backend Agent | ✅ Deployed | Latest with updated prompt |
| Frontend Code | ✅ Committed | Brace-counting detection |
| Amplify Deploy | ⏳ Pending | Waiting for build |
| Gateway | ✅ Preserved | Ready for future MCP tools |

## Console Debug Output Expected

Once Amplify deploys, you should see:

```
[MarkdownRenderer] Valid chart found: Tesla (TSLA) - 30 Day Price Trend
[MarkdownRenderer] Total charts found: 1
```

If you see these logs but no chart, the issue is in ChartRenderer.
If you don't see these logs, the detection logic isn't working.

## Current Agent Output Format

```
Perfect! Here's Tesla's 30-day price trend chart:json{
  "type": "chart",
  "chartType": "line",
  "title": "Tesla (TSLA) - 30 Day Price Trend",
  "data": {
    "labels": ["Jan 21", "Jan 22", ...],
    "datasets": [{
      "label": "TSLA Price (USD)",
      "data": [412.50, 408.20, ...],
      "color": "#3fb950"
    }]
  },
  "options": {
    "yAxisLabel": "Price (USD)",
    "xAxisLabel": "Date"
  }
}
```

**Note**: Agent writes `json{` instead of proper code fence. Our detection should handle this.

## Recommended Action

**WAIT** for Amplify deployment to complete, then:
1. Hard refresh browser
2. Check console logs
3. Report findings

If detection works but agent format is still wrong, we'll implement Option A (detect `json{` pattern specifically).
