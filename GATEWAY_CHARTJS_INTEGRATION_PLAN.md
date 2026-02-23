# Gateway Chart.js Lambda Integration Plan

## Overview
Create a Lambda function in the AgentCore Gateway that wraps the Chart.js MCP server. This provides a clean interface for the agent to generate charts without MCP serialization issues.

## Architecture

```
Agent → Gateway → Chart Lambda → Chart.js MCP Server → Chart Lambda → Gateway → Agent
```

## Benefits

1. **Clean Interface**: Agent calls a simple Lambda tool with JSON parameters
2. **MCP Abstraction**: Lambda handles all MCP communication complexity
3. **Error Handling**: Lambda can catch and handle MCP errors gracefully
4. **Flexibility**: Can add preprocessing, validation, or post-processing
5. **Reusability**: Same Lambda can be used by multiple agents/gateways

## Implementation Steps

### 1. Create Chart Lambda Function

**Location**: `gateway/tools/chart_tool/chart_tool_lambda.py`

**Responsibilities**:
- Accept chart configuration as JSON object
- Call Chart.js MCP server using stdio transport
- Handle MCP session lifecycle
- Return HTML chart or error message

**Key Features**:
- Node.js runtime support (for npx command)
- MCP client integration
- Proper error handling and logging
- JSON validation

### 2. Define Tool Schema

**Tool Name**: `generate_chart`

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "chartType": {
      "type": "string",
      "enum": ["line", "bar", "pie", "doughnut", "scatter", "bubble", "radar", "polar"],
      "description": "Type of chart to generate"
    },
    "data": {
      "type": "object",
      "description": "Chart data with labels and datasets",
      "properties": {
        "labels": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Array of labels for the chart"
        },
        "datasets": {
          "type": "array",
          "description": "Array of dataset objects"
        }
      },
      "required": ["labels", "datasets"]
    },
    "options": {
      "type": "object",
      "description": "Chart.js options for customization (optional)"
    },
    "title": {
      "type": "string",
      "description": "Chart title"
    }
  },
  "required": ["chartType", "data", "title"]
}
```

### 3. Lambda Implementation Details

**Runtime**: Python 3.13 with Node.js layer

**Dependencies**:
- `mcp` Python package for MCP client
- Node.js 20+ for Chart.js MCP server
- `@ax-crew/chartjs-mcp-server` npm package

**Code Structure**:
```python
import json
import logging
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger()
logger.setLevel(logging.INFO)

async def call_chartjs_mcp(chart_config: dict) -> str:
    """
    Call Chart.js MCP server to generate chart HTML.
    
    Args:
        chart_config: Chart.js configuration object
        
    Returns:
        HTML string with embedded chart
    """
    async with stdio_client(
        StdioServerParameters(
            command="npx",
            args=["@ax-crew/chartjs-mcp-server"]
        )
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Call generateChart tool
            result = await session.call_tool(
                "generateChart",
                arguments={
                    "chartConfig": chart_config,
                    "outputFormat": "html"
                }
            )
            
            # Extract HTML from result
            if result.content and len(result.content) > 0:
                return result.content[0].text
            else:
                raise ValueError("No content returned from Chart.js MCP")

def lambda_handler(event, context):
    """
    Lambda handler for chart generation tool.
    
    Args:
        event: Tool arguments from Gateway
        context: Lambda context with tool name
        
    Returns:
        Chart HTML or error message
    """
    try:
        logger.info(f"Chart tool invoked with event: {json.dumps(event)}")
        
        # Extract parameters
        chart_type = event.get('chartType')
        data = event.get('data')
        options = event.get('options', {})
        title = event.get('title', 'Chart')
        
        # Build Chart.js configuration
        chart_config = {
            "type": chart_type,
            "data": data,
            "options": {
                "responsive": True,
                "maintainAspectRatio": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": title,
                        "font": {"size": 18, "weight": "bold"}
                    },
                    "legend": {"display": True, "position": "top"}
                },
                **options
            }
        }
        
        # Call Chart.js MCP server
        html_result = asyncio.run(call_chartjs_mcp(chart_config))
        
        logger.info("Chart generated successfully")
        
        return {
            "content": [{
                "type": "text",
                "text": html_result
            }]
        }
        
    except Exception as e:
        logger.error(f"Error generating chart: {str(e)}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"Error generating chart: {str(e)}"
            }]
        }
```

### 4. CDK Infrastructure Updates

**File**: `infra-cdk/lib/backend-stack.ts`

**Changes**:
1. Re-enable Gateway infrastructure
2. Create Chart Lambda function with Node.js layer
3. Add tool schema to Gateway target
4. Configure Lambda permissions

**Code Snippet**:
```typescript
// Create Chart Lambda with Node.js support
const chartLambda = new lambda.Function(this, 'ChartToolLambda', {
  runtime: lambda.Runtime.PYTHON_3_13,
  handler: 'chart_tool_lambda.lambda_handler',
  code: lambda.Code.fromAsset(path.join(__dirname, '../../gateway/tools/chart_tool')),
  timeout: Duration.seconds(30),
  memorySize: 512,
  environment: {
    NODE_PATH: '/opt/nodejs/node_modules'
  },
  layers: [nodeLayer] // Node.js 20 layer
});

// Define chart tool schema
const chartToolSchema = {
  name: "generate_chart",
  description: "Generate interactive Chart.js visualizations for financial data",
  inputSchema: {
    type: "object",
    properties: {
      chartType: {
        type: "string",
        enum: ["line", "bar", "pie", "doughnut", "scatter", "bubble", "radar", "polar"],
        description: "Type of chart to generate"
      },
      data: {
        type: "object",
        description: "Chart data with labels and datasets"
      },
      title: {
        type: "string",
        description: "Chart title"
      }
    },
    required: ["chartType", "data", "title"]
  }
};
```

### 5. Agent System Prompt Updates

Update the agent to use the Gateway chart tool instead of direct MCP:

```python
CHART GENERATION WORKFLOW:

When user asks for a chart:

1. FETCH DATA from Alpha Vantage
2. PREPARE DATA in simple format:
   - labels: array of strings (dates, categories, etc.)
   - datasets: array with data points and styling

3. CALL generate_chart TOOL:
   - chartType: "line" (for trends), "bar" (for comparisons), etc.
   - data: {labels: [...], datasets: [{label: "...", data: [...], ...}]}
   - title: "Descriptive chart title"
   - options: (optional) additional Chart.js options

4. The tool returns HTML that displays automatically in the chat

EXAMPLE:
Use generate_chart tool with:
- chartType: "line"
- data: {
    labels: ["Feb 11", "Feb 12", "Feb 13"],
    datasets: [{
      label: "AMZN Price",
      data: [204.08, 199.6, 198.79],
      borderColor: "#3fb950",
      backgroundColor: "rgba(63, 185, 80, 0.1)"
    }]
  }
- title: "Amazon Stock - 1 Week Trend"
```

### 6. Frontend Updates

**No changes needed** - Frontend already handles:
- Tool output rendering in ToolCallDisplay
- Chart.js HTML detection and rendering
- Markdown with embedded HTML

## Testing Plan

### Unit Tests
1. Test Lambda with valid chart configurations
2. Test Lambda with invalid inputs
3. Test MCP communication errors
4. Test timeout scenarios

### Integration Tests
1. Deploy Gateway with chart tool
2. Test from agent: "Chart the 1-week price trend for AMAZON"
3. Verify HTML chart renders in frontend
4. Test different chart types (line, bar, pie)
5. Test error handling

### Performance Tests
1. Measure Lambda cold start time
2. Measure chart generation time
3. Test concurrent requests
4. Monitor memory usage

## Deployment Steps

1. Create chart Lambda function code
2. Update CDK stack with Gateway + chart tool
3. Deploy infrastructure: `npm run cdk deploy FAST-stack`
4. Update agent system prompt
5. Test chart generation
6. Commit and push changes

## Rollback Plan

If issues occur:
1. Keep current MCP-based agent as backup
2. Gateway can be disabled without affecting agent
3. Can switch back to Code Interpreter charts
4. Lambda can be updated independently

## Success Criteria

- ✅ Agent can call generate_chart tool successfully
- ✅ Lambda communicates with Chart.js MCP server
- ✅ HTML charts render in frontend
- ✅ Error messages are clear and actionable
- ✅ Performance is acceptable (<5s for chart generation)
- ✅ Multiple chart types work correctly

## Next Steps

1. Get approval for this approach
2. Create chart Lambda function
3. Update CDK infrastructure
4. Test locally if possible
5. Deploy and test in AWS
6. Update documentation
