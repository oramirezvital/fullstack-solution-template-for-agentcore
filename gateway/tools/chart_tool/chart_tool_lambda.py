"""
Chart Tool Lambda Function

This Lambda function serves as a Gateway target that wraps the Chart.js MCP server.
It accepts chart configuration parameters from the AgentCore Gateway and generates
interactive Chart.js visualizations by communicating with the Chart.js MCP server
via stdio transport.

The Lambda handles:
- Parsing Gateway event format
- Building Chart.js configuration objects
- Calling Chart.js MCP server asynchronously
- Returning HTML charts in Gateway response format
- Error handling and logging

Author: Investment Advisor Agent Team
"""

import asyncio
import json
import logging
from typing import Any, Dict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


async def generate_chart_async(chart_config: Dict[str, Any]) -> str:
    """
    Call Chart.js MCP server to generate chart HTML.

    This function establishes an async MCP session with the Chart.js server
    running via npx, sends the chart configuration, and retrieves the
    generated HTML output.

    Args:
        chart_config: Chart.js configuration object with type, data, and options

    Returns:
        str: HTML string containing the interactive Chart.js visualization

    Raises:
        ValueError: If Chart.js MCP returns no content
        Exception: If MCP communication fails
    """
    logger.info("Establishing MCP session with Chart.js server")

    # Create stdio client for Chart.js MCP server
    # The server runs via npx and communicates through stdin/stdout
    async with stdio_client(
        StdioServerParameters(command="npx", args=["@ax-crew/chartjs-mcp-server"])
    ) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize MCP session
            await session.initialize()
            logger.info("MCP session initialized successfully")

            # Call generateChart tool with configuration
            result = await session.call_tool(
                name="generateChart",
                arguments={"chartConfig": chart_config, "outputFormat": "html"},
            )

            # Extract HTML from result
            if result.content and len(result.content) > 0:
                html_output = result.content[0].text
                logger.info(
                    f"Chart generated successfully, HTML length: {len(html_output)}"
                )
                return html_output
            else:
                raise ValueError("No content returned from Chart.js MCP server")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for chart generation tool invoked by AgentCore Gateway.

    This function follows the Gateway Lambda target pattern:
    - Tool name is passed via context.client_context.custom['bedrockAgentCoreToolName']
    - Tool arguments are passed directly in the event body
    - Response must be in Gateway format with 'content' array

    Args:
        event: Dictionary containing tool arguments (chartType, data, title, options)
        context: Lambda context object with client_context containing tool name

    Returns:
        Dict containing 'content' array with chart HTML or error message

    Example event:
        {
            "chartType": "line",
            "data": {
                "labels": ["Jan", "Feb", "Mar"],
                "datasets": [{
                    "label": "Sales",
                    "data": [100, 200, 150]
                }]
            },
            "title": "Monthly Sales",
            "options": {}
        }
    """
    try:
        logger.info(f"Chart tool invoked with event: {json.dumps(event)}")

        # Extract tool name from context (Gateway pattern)
        # Format: {target_name}___{tool_name}
        delimiter = "___"
        original_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]

        # Strip target prefix to get actual tool name
        if delimiter in original_tool_name:
            tool_name = original_tool_name[
                original_tool_name.index(delimiter) + len(delimiter) :
            ]
        else:
            tool_name = original_tool_name

        logger.info(f"Extracted tool name: {tool_name}")

        # Validate tool name
        if tool_name != "generate_chart":
            raise ValueError(f"Unknown tool: {tool_name}")

        # Extract and validate required parameters
        chart_type = event.get("chartType")
        data = event.get("data")
        title = event.get("title", "Chart")
        options = event.get("options", {})

        if not chart_type:
            raise ValueError("chartType is required")
        if not data:
            raise ValueError("data is required")
        if not isinstance(data, dict):
            raise ValueError("data must be an object")
        if "labels" not in data:
            raise ValueError("data.labels is required")
        if "datasets" not in data:
            raise ValueError("data.datasets is required")

        logger.info(f"Generating {chart_type} chart with title: {title}")

        # Build Chart.js configuration object
        # This is the format expected by Chart.js MCP server
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
                        "padding": 20,
                    },
                    "legend": {"display": True, "position": "top"},
                    "tooltip": {"enabled": True, "mode": "index", "intersect": False},
                },
                # Merge any additional options provided by the agent
                **options,
            },
        }

        logger.info(f"Chart configuration built: {json.dumps(chart_config, indent=2)}")

        # Call Chart.js MCP server asynchronously
        html_result = asyncio.run(generate_chart_async(chart_config))

        logger.info("Chart generation completed successfully")

        # Return in Gateway expected format
        # Gateway expects: {"content": [{"type": "text", "text": "..."}]}
        return {"content": [{"type": "text", "text": html_result}]}

    except Exception as e:
        # Log full error details for debugging
        logger.error(f"Error generating chart: {str(e)}", exc_info=True)

        # Return error message in Gateway format
        # This allows the agent to see what went wrong
        return {
            "content": [{"type": "text", "text": f"Error generating chart: {str(e)}"}]
        }
