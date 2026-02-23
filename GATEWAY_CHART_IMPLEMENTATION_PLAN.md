# Gateway Chart Tool Implementation Plan

## Context

Based on the documentation and previous architecture:
- **Previous**: Gateway with Lambda tools (sample_tool, stock_tool) → Removed for simplicity
- **Current**: Agent uses Alpha Vantage MCP directly + Code Interpreter
- **Goal**: Re-enable Gateway with a single chart Lambda that wraps Chart.js MCP

## Why This Approach?

1. **Solves MCP Serialization Issue**: Lambda handles JSON properly, no string/object confusion
2. **Clean Architecture**: Follows FAST's proven Gateway + Lambda pattern
3. **Separation of Concerns**: Chart generation logic separate from agent
4. **Reusable**: Chart Lambda can be used by other agents/services
5. **Maintainable**: Easy to update chart logic without touching agent code

## Architecture

```
Agent → Gateway (MCP) → Chart Lambda → Chart.js MCP Server → Chart Lambda → Gateway → Agent
                     ↓
              Alpha Vantage MCP (direct connection, no Gateway)
```

**Key Points**:
- Gateway is ONLY for chart generation tool
- Alpha Vantage MCP remains a direct connection (no Gateway)
- Agent has TWO tool sources: Gateway (charts) + Alpha Vantage MCP (financial data)

## Implementation Steps

### Step 1: Create Chart Lambda Function

**Location**: `gateway/tools/chart_tool/chart_tool_lambda.py`

**Purpose**: Accept chart parameters from Gateway, call Chart.js MCP server, return HTML

**Key Requirements**:
- Node.js 20+ runtime (for npx command)
- Python 3.13 with MCP client libraries
- Async MCP session management
- Proper error handling

**Code Structure**:
```python
import json
import logging
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger()
logger.setLevel(logging.INFO)

async def generate_chart_async(chart_config: dict) -> str:
    """Call Chart.js MCP server to generate chart HTML."""
    async with stdio_client(
        StdioServerParameters(
            command="npx",
            args=["@ax-crew/chartjs-mcp-server"]
        )
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            result = await session.call_tool(
                "generateChart",
                arguments={
                    "chartConfig": chart_config,
                    "outputFormat": "html"
                }
            )
            
            if result.content and len(result.content) > 0:
                return result.content[0].text
            else:
                raise ValueError("No content returned from Chart.js MCP")

def lambda_handler(event, context):
    """
    Gateway Lambda handler for chart generation.
    
    Event contains tool arguments directly.
    Context contains tool name in client_context.custom['bedrockAgentCoreToolName']
    """
    try:
        logger.info(f"Chart tool invoked with event: {json.dumps(event)}")
        
        # Extract tool name from context (Gateway pattern)
        delimiter = "___"
        original_tool_name = context.client_context.custom['bedrockAgentCoreToolName']
        tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]
        
        logger.info(f"Tool name: {tool_name}")
        
        if tool_name != "generate_chart":
            raise ValueError(f"Unknown tool: {tool_name}")
        
        # Extract parameters from event
        chart_type = event.get('chartType')
        data = event.get('data')
        options = event.get('options', {})
        title = event.get('title', 'Chart')
        
        # Validate required parameters
        if not chart_type or not data:
            raise ValueError("chartType and data are required")
        
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
                        "font": {"size": 18, "weight": "bold"},
                        "padding": 20
                    },
                    "legend": {
                        "display": True,
                        "position": "top"
                    },
                    "tooltip": {
                        "enabled": True,
                        "mode": "index",
                        "intersect": False
                    }
                },
                **options  # Merge any additional options
            }
        }
        
        logger.info(f"Calling Chart.js MCP with config: {json.dumps(chart_config)}")
        
        # Call Chart.js MCP server
        html_result = asyncio.run(generate_chart_async(chart_config))
        
        logger.info("Chart generated successfully")
        
        # Return in Gateway expected format
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

**Dependencies** (`gateway/tools/chart_tool/requirements.txt`):
```
mcp>=1.0.0
```

### Step 2: Create Tool Schema

**Location**: `gateway/tools/chart_tool/tool_spec.json`

```json
{
  "name": "generate_chart",
  "description": "Generate interactive Chart.js visualizations for financial data. Supports line, bar, pie, doughnut, scatter, bubble, radar, and polar charts.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "chartType": {
        "type": "string",
        "enum": ["line", "bar", "pie", "doughnut", "scatter", "bubble", "radar", "polar"],
        "description": "Type of chart to generate. Use 'line' for trends, 'bar' for comparisons, 'pie' for proportions."
      },
      "data": {
        "type": "object",
        "description": "Chart data object with labels and datasets arrays",
        "properties": {
          "labels": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Array of labels (dates, categories, etc.)"
          },
          "datasets": {
            "type": "array",
            "description": "Array of dataset objects with label, data, and styling properties"
          }
        },
        "required": ["labels", "datasets"]
      },
      "title": {
        "type": "string",
        "description": "Chart title to display at the top"
      },
      "options": {
        "type": "object",
        "description": "Optional Chart.js options for advanced customization (scales, colors, etc.)"
      }
    },
    "required": ["chartType", "data", "title"]
  }
}
```

### Step 3: Update CDK Infrastructure

**File**: `infra-cdk/lib/backend-stack.ts`

**Changes**:

1. **Re-enable Machine Authentication** (uncomment):
```typescript
// Create Machine-to-Machine authentication components
this.createMachineAuthentication(props.config)
```

2. **Re-enable Gateway Creation** (uncomment and modify):
```typescript
// Create AgentCore Gateway for chart generation tool
this.createAgentCoreGateway(props.config)
```

3. **Update Gateway Method** to include ONLY chart tool:
```typescript
private createAgentCoreGateway(config: AppConfig): void {
  // ... existing Gateway setup code ...
  
  // Create Chart Tool Lambda with Node.js support
  const chartToolLambda = new lambda.Function(this, "ChartToolLambda", {
    runtime: lambda.Runtime.PYTHON_3_13,
    handler: "chart_tool_lambda.lambda_handler",
    code: lambda.Code.fromAsset(
      path.join(__dirname, "../../gateway/tools/chart_tool")
    ),
    timeout: cdk.Duration.seconds(30),
    memorySize: 512,
    environment: {
      NODE_PATH: "/opt/nodejs/node_modules",
    },
    layers: [this.createNodeLayer()], // Node.js 20 layer
  })

  // Grant Gateway permission to invoke Lambda
  chartToolLambda.grantInvoke(gatewayRole)

  // Load chart tool schema
  const chartToolSpec = JSON.parse(
    fs.readFileSync(
      path.join(__dirname, "../../gateway/tools/chart_tool/tool_spec.json"),
      "utf-8"
    )
  )

  // Create Gateway target with chart tool
  const gatewayTarget = new bedrockagentcore.CfnGatewayTarget(
    this,
    "ChartToolTarget",
    {
      gatewayIdentifier: gateway.attrGatewayId,
      name: "chart_tool_target",
      resourceArn: chartToolLambda.functionArn,
      tools: [chartToolSpec],
    }
  )
  
  // ... rest of Gateway setup ...
}

private createNodeLayer(): lambda.LayerVersion {
  // Create Node.js 20 layer for Chart.js MCP
  return new lambda.LayerVersion(this, "NodeLayer", {
    code: lambda.Code.fromAsset(
      path.join(__dirname, "../../layers/nodejs"),
      {
        bundling: {
          image: lambda.Runtime.NODEJS_20_X.bundlingImage,
          command: [
            "bash",
            "-c",
            [
              "mkdir -p /asset-output/nodejs",
              "cd /asset-output/nodejs",
              "npm install @ax-crew/chartjs-mcp-server",
            ].join(" && "),
          ],
        },
      }
    ),
    compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
    description: "Node.js 20 with Chart.js MCP server",
  })
}
```

### Step 4: Update Agent Code

**File**: `patterns/strands-single-agent/basic_agent.py`

**Changes**:

1. **Add Gateway MCP Client** (alongside Alpha Vantage):
```python
from utils.auth import get_gateway_access_token

def create_gateway_mcp_client() -> MCPClient:
    """Create MCP client for AgentCore Gateway (chart generation tool)."""
    gateway_url = os.environ.get("GATEWAY_URL")
    if not gateway_url:
        raise ValueError("GATEWAY_URL environment variable is required")
    
    # Get OAuth2 token for Gateway authentication
    access_token = get_gateway_access_token()
    
    gateway_client = MCPClient(
        lambda: streamablehttp_client(
            url=gateway_url,
            headers={"Authorization": f"Bearer {access_token}"}
        ),
        prefix="gateway",
    )
    
    return gateway_client
```

2. **Add Gateway Client to Agent Tools**:
```python
# Create Gateway MCP client for chart generation
gateway_client = create_gateway_mcp_client()

# Create Alpha Vantage MCP client for financial data
alpha_vantage_client = create_alpha_vantage_mcp_client()

agent = Agent(
    name="InvestmentAdvisor",
    system_prompt=system_prompt,
    tools=[
        gateway_client,  # Chart generation tool
        alpha_vantage_client,  # Financial data tools
        code_tools.execute_python_securely,  # Code Interpreter
    ],
    model=bedrock_model,
    session_manager=session_manager,
)
```

3. **Update System Prompt** with Gateway chart tool instructions:
```python
system_prompt = """...

CHART GENERATION WORKFLOW:

When user asks for a chart (e.g., "Chart the 1-week price trend for AMAZON"):

1. FETCH DATA from Alpha Vantage:
   - Use TIME_SERIES_DAILY for historical price data
   - Extract dates and prices from the response

2. PREPARE DATA in simple format:
   labels = ["Feb 11", "Feb 12", "Feb 13", ...]
   datasets = [{
     "label": "AMZN Price (USD)",
     "data": [204.08, 199.6, 198.79, ...],
     "borderColor": "#3fb950",
     "backgroundColor": "rgba(63, 185, 80, 0.1)",
     "fill": true
   }]

3. CALL gateway_generate_chart TOOL:
   - chartType: "line" (for trends), "bar" (for comparisons), etc.
   - data: {labels: [...], datasets: [...]}
   - title: "Amazon (AMZN) - 1 Week Price Trend"
   - options: (optional) additional Chart.js customization

4. The tool returns HTML that displays automatically in the chat

EXAMPLE TOOL CALL:
Use gateway_generate_chart with:
{
  "chartType": "line",
  "data": {
    "labels": ["Feb 11", "Feb 12", "Feb 13"],
    "datasets": [{
      "label": "AMZN Price (USD)",
      "data": [204.08, 199.6, 198.79],
      "borderColor": "#3fb950",
      "backgroundColor": "rgba(63, 185, 80, 0.1)",
      "fill": true,
      "tension": 0.3
    }]
  },
  "title": "Amazon (AMZN) - 1 Week Price Trend"
}

CHART STYLING TIPS:
- Green (#3fb950) for positive/gains
- Red (#f85149) for negative/losses
- Blue (#58a6ff) for neutral data
- Add "fill": true for area charts
- Use "tension": 0.3-0.4 for smooth lines

...
"""
```

### Step 5: Update Agent Dockerfile

**File**: `patterns/strands-single-agent/Dockerfile`

**No changes needed** - Node.js is already installed in the agent container, but it's not needed there since the Lambda handles Chart.js MCP.

### Step 6: Frontend Updates

**No changes needed** - Frontend already handles:
- Gateway tool output in ToolCallDisplay
- Chart.js HTML rendering
- Tool result display

### Step 7: Testing Plan

1. **Local Lambda Testing** (if possible):
   - Test Lambda with sample chart configurations
   - Verify MCP communication works
   - Test error handling

2. **Integration Testing**:
   - Deploy Gateway + Lambda
   - Test from agent: "Chart the 1-week price trend for AMAZON"
   - Verify HTML chart renders in frontend
   - Test different chart types
   - Test error scenarios

3. **Performance Testing**:
   - Measure Lambda cold start time
   - Measure chart generation time
   - Test concurrent requests

## Deployment Steps

1. Create chart Lambda code and tool spec
2. Update CDK stack (re-enable Gateway, add chart tool)
3. Deploy: `cd infra-cdk && npm run cdk deploy FAST-stack`
4. Update agent code (add Gateway client)
5. Deploy agent (CDK will rebuild container)
6. Test chart generation
7. Commit and push changes

## Success Criteria

- ✅ Gateway deploys successfully with chart tool
- ✅ Lambda can call Chart.js MCP server
- ✅ Agent can call gateway_generate_chart tool
- ✅ HTML charts render in frontend
- ✅ Error messages are clear
- ✅ Performance is acceptable (<5s)
- ✅ Multiple chart types work

## Rollback Plan

If issues occur:
1. Comment out Gateway infrastructure in CDK
2. Remove Gateway client from agent
3. Redeploy
4. Agent falls back to Code Interpreter for charts

## Files to Create/Modify

### New Files:
1. `gateway/tools/chart_tool/chart_tool_lambda.py` - Lambda function
2. `gateway/tools/chart_tool/requirements.txt` - Dependencies
3. `gateway/tools/chart_tool/tool_spec.json` - Tool schema

### Modified Files:
1. `infra-cdk/lib/backend-stack.ts` - Re-enable Gateway, add chart tool
2. `patterns/strands-single-agent/basic_agent.py` - Add Gateway client
3. `patterns/strands-single-agent/requirements.txt` - Ensure MCP dependencies

### Documentation:
1. Update `docs/GATEWAY.md` with chart tool example
2. Update `README.md` with chart generation feature

## Next Steps

Ready to proceed? I'll:
1. Create the chart Lambda function
2. Create the tool spec
3. Update the CDK infrastructure
4. Update the agent code
5. Test and deploy

This approach follows FAST's proven Gateway pattern and solves the MCP serialization issue cleanly!
