# Chart.js MCP Server Integration Plan

## Overview
Integrate the Chart.js MCP server (@ax-crew/chartjs-mcp-server) to generate professional, interactive charts using data from Alpha Vantage API. This will replace the current approach of having the LLM generate HTML/Chart.js code manually.

## Current State
- Agent uses Alpha Vantage MCP for financial data
- Agent attempts to generate Chart.js HTML code directly (unreliable)
- Frontend renders HTML code blocks with `dangerouslySetInnerHTML`
- Charts sometimes fail to render or show as text

## Proposed Solution
Use the Chart.js MCP server as a dedicated tool for chart generation:
1. Agent fetches data from Alpha Vantage MCP
2. Agent calls Chart.js MCP `generateChart` tool with proper configuration
3. Chart.js MCP returns interactive HTML or PNG
4. Frontend renders the chart output

## Benefits
- **Reliability**: Dedicated MCP server ensures consistent chart generation
- **Speed**: No LLM token generation for HTML/JS code
- **Quality**: Professional Chart.js v4 charts with proper configuration
- **Flexibility**: Supports 8 chart types (bar, line, pie, doughnut, scatter, bubble, radar, polar)
- **Output Options**: Can generate PNG images or interactive HTML divs

## Implementation Steps

### 1. Update Agent Code (`patterns/strands-single-agent/basic_agent.py`)

#### A. Add Chart.js MCP Client Creation
```python
def create_chartjs_mcp_client() -> MCPClient:
    """
    Create MCP client for Chart.js chart generation.
    
    The Chart.js MCP server generates beautiful, professional charts using Chart.js v4.
    It supports multiple chart types and can output both PNG images and interactive HTML.
    
    Note: This uses npx to run the Chart.js MCP server, which requires Node.js 18+
    to be available in the Lambda execution environment.
    
    Returns:
        MCPClient: Configured client for Chart.js MCP server
    """
    print("[AGENT] Creating Chart.js MCP client...")
    
    # Chart.js MCP server runs via npx (requires Node.js in environment)
    # Alternative: Use stdio transport if npx doesn't work in Lambda
    chartjs_client = MCPClient(
        lambda: streamablehttp_client(url="npx @ax-crew/chartjs-mcp-server"),
        prefix="chartjs",
    )
    
    print("[AGENT] Chart.js MCP client created successfully")
    return chartjs_client
```

**ISSUE TO INVESTIGATE**: Lambda Python runtime may not have Node.js available. 
**Alternative approaches**:
- Use stdio transport instead of HTTP
- Install Node.js in Lambda layer
- Run Chart.js MCP as separate service
- Use Python-based chart generation library instead

#### B. Update Agent Creation Function
Add Chart.js MCP client to the agent's tools:
```python
# Create Chart.js MCP client for visualizations
chartjs_client = create_chartjs_mcp_client()

agent = Agent(
    name="InvestmentAdvisor",
    system_prompt=system_prompt,
    tools=[
        alpha_vantage_client,  # Alpha Vantage financial tools
        chartjs_client,  # Chart.js visualization tools
        code_tools.execute_python_securely,  # Code Interpreter for calculations
    ],
    model=bedrock_model,
    session_manager=session_manager,
)
```

#### C. Update System Prompt
Replace HTML generation instructions with Chart.js MCP tool usage:

```markdown
2. CHART GENERATION:
   - Use Chart.js MCP server (chartjs_generateChart tool) for all visualizations
   - Fetch data from Alpha Vantage first
   - Format data into Chart.js configuration object
   - Call chartjs_generateChart with outputFormat='html' for interactive charts
   - The tool returns self-contained HTML that renders automatically

CHART GENERATION WORKFLOW:

When user asks for a chart:
1. Fetch data from Alpha Vantage (e.g., TIME_SERIES_DAILY for price history)
2. Process data into arrays (dates, prices, volumes, etc.)
3. Create Chart.js configuration object:
   {
     "type": "line",
     "data": {
       "labels": ["Sep 29", "Oct 02", ...],
       "datasets": [{
         "label": "AMZN Price",
         "data": [222.17, 222.41, ...],
         "borderColor": "#58a6ff",
         "backgroundColor": "rgba(88, 166, 255, 0.2)",
         "fill": true
       }]
     },
     "options": {
       "responsive": true,
       "plugins": {
         "title": { "display": true, "text": "Amazon 6-Month Price Trend" }
       }
     }
   }
4. Call chartjs_generateChart tool with:
   - chartConfig: (the configuration above)
   - outputFormat: "html"
5. The tool returns interactive HTML that displays automatically

CHART TYPES AVAILABLE:
- line: Price trends, time series
- bar: Comparisons, categorical data
- pie/doughnut: Portfolio allocation, market share
- scatter/bubble: Correlation analysis
- radar: Multi-factor comparison
- polar: Radial data visualization

IMPORTANT:
- Always use outputFormat='html' for interactive charts
- Include proper labels, titles, and legends
- Use appropriate colors for financial data (green for gains, red for losses)
- Add tooltips for better user experience
```

### 2. Infrastructure Considerations

#### Option A: Node.js in Lambda (Preferred if feasible)
- Add Node.js 18+ to Lambda layer
- Ensure npx is available
- Chart.js MCP runs in same Lambda environment

#### Option B: Separate Service (More complex)
- Deploy Chart.js MCP as separate ECS/Fargate service
- Agent connects via HTTP
- Requires additional infrastructure

#### Option C: Python Alternative (Fallback)
- Use matplotlib/plotly for chart generation
- Keep current Code Interpreter approach
- Less ideal but works without Node.js

**RECOMMENDATION**: Start with Option A, fall back to Option C if Node.js not available

### 3. Frontend Updates (Already Done)
- ✅ Frontend already renders HTML code blocks with `dangerouslySetInnerHTML`
- ✅ No additional frontend changes needed
- Chart.js MCP returns self-contained HTML divs that work immediately

### 4. Testing Plan

#### Local Testing
1. Test Chart.js MCP client creation
2. Test generateChart tool with sample data
3. Verify HTML output renders correctly
4. Test different chart types (line, bar, pie)

#### Integration Testing
1. Deploy to AWS
2. Test with real Alpha Vantage data
3. Verify charts display in frontend
4. Test error handling (rate limits, invalid data)

### 5. Rollback Plan
If Chart.js MCP integration fails:
1. Keep current HTML generation approach
2. Improve system prompt with better examples
3. Add validation for generated HTML
4. Consider Python-based chart generation

## Technical Challenges

### Challenge 1: Node.js in Lambda
**Problem**: Python Lambda runtime doesn't include Node.js
**Solutions**:
- Add Node.js to Lambda layer
- Use custom Docker image with both Python and Node.js
- Run Chart.js MCP as separate service
- Use Python chart library instead

### Challenge 2: MCP Transport
**Problem**: Chart.js MCP may not support HTTP transport
**Solutions**:
- Check if stdio transport is supported
- Use subprocess to run npx command
- Implement custom transport layer

### Challenge 3: Chart.js MCP Availability
**Problem**: NPM package may not be accessible from Lambda
**Solutions**:
- Pre-install in Lambda layer
- Bundle with deployment package
- Use CDN-hosted version

## Success Criteria
- ✅ Agent can generate charts using Chart.js MCP
- ✅ Charts display correctly in frontend
- ✅ Faster response time than HTML generation
- ✅ Reliable chart rendering (no text fallback)
- ✅ Support for multiple chart types
- ✅ Interactive features (hover tooltips, animations)

## Timeline
1. **Investigation** (30 min): Check Node.js availability in Lambda
2. **Implementation** (1-2 hours): Add Chart.js MCP client
3. **Testing** (30 min): Local and integration tests
4. **Deployment** (15 min): Deploy and verify
5. **Rollback if needed** (15 min): Revert to previous approach

## Next Steps
1. ✅ Create this plan document
2. ✅ Get user approval
3. ✅ Investigate Node.js availability in Lambda - Added Node.js 20 to Dockerfile
4. ✅ Implement Chart.js MCP client - Using stdio transport
5. ✅ Update system prompt - Added Chart.js workflow instructions
6. ✅ Test and deploy - Successfully deployed
7. ⏳ Test with real queries - Ready for user testing
8. ⏳ Document results

## Implementation Complete!

Successfully integrated Chart.js MCP server:
- ✅ Added Node.js 20.20.0 to Docker image
- ✅ Installed @ax-crew/chartjs-mcp-server globally
- ✅ Created Chart.js MCP client with stdio transport
- ✅ Updated agent to include chartjs_generateChart tool
- ✅ Updated system prompt with Chart.js workflow
- ✅ Deployed to AWS successfully

The agent now has access to:
1. Alpha Vantage MCP (100+ financial data tools)
2. Chart.js MCP (professional chart generation)
3. Code Interpreter (calculations and data processing)
4. Long-term memory (portfolio tracking)

Ready to test with: "Chart the 6-month price trend for AMAZON"

## Questions for User
1. Do you want to proceed with Chart.js MCP integration?
2. Are you okay with adding Node.js to the Lambda environment if needed?
3. Should we have a fallback to Python-based charts if Node.js isn't available?
