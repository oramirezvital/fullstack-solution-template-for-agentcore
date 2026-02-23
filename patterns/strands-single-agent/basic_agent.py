import json
import os
import traceback

import boto3
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands_code_interpreter import StrandsCodeInterpreterTools

from utils.auth import extract_user_id_from_context, get_gateway_access_token
from utils.ssm import get_ssm_parameter

app = BedrockAgentCoreApp()


def create_gateway_mcp_client(access_token: str) -> MCPClient:
    """
    Create MCP client for AgentCore Gateway with OAuth2 authentication.

    MCP (Model Context Protocol) is how agents communicate with tool providers.
    This creates a client that can talk to the AgentCore Gateway using the provided
    access token for authentication. The Gateway then provides access to Lambda-based tools.
    """
    stack_name = os.environ.get("STACK_NAME")
    if not stack_name:
        raise ValueError("STACK_NAME environment variable is required")

    # Validate stack name format to prevent injection
    if not stack_name.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid STACK_NAME format")

    print(f"[AGENT] Creating Gateway MCP client for stack: {stack_name}")

    # Fetch Gateway URL from SSM
    gateway_url = get_ssm_parameter(f"/{stack_name}/gateway_url")
    print(f"[AGENT] Gateway URL from SSM: {gateway_url}")

    # Create MCP client with Bearer token authentication
    gateway_client = MCPClient(
        lambda: streamablehttp_client(
            url=gateway_url, headers={"Authorization": f"Bearer {access_token}"}
        ),
        prefix="gateway",
    )

    print("[AGENT] Gateway MCP client created successfully")
    return gateway_client


def create_alpha_vantage_mcp_client() -> MCPClient:
    """
    Create MCP client for Alpha Vantage financial data API.
    
    Alpha Vantage provides comprehensive financial market data through their MCP server.
    This includes stock prices, technical indicators, fundamental data, options, forex,
    crypto, commodities, and economic indicators. The client connects to Alpha Vantage's
    hosted MCP server using an API key for authentication.
    
    Returns:
        MCPClient: Configured client for Alpha Vantage MCP server
        
    Raises:
        ValueError: If ALPHA_VANTAGE_API_KEY environment variable is not set
    """
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is required")
    
    print("[AGENT] Creating Alpha Vantage MCP client...")
    
    # Alpha Vantage MCP server URL with API key authentication
    alpha_vantage_url = f"https://mcp.alphavantage.co/mcp?apikey={api_key}"
    
    # Create MCP client for Alpha Vantage
    # No additional headers needed as API key is in the URL
    alpha_vantage_client = MCPClient(
        lambda: streamablehttp_client(url=alpha_vantage_url),
        prefix="alphavantage",
    )
    
    print("[AGENT] Alpha Vantage MCP client created successfully")
    return alpha_vantage_client


def create_basic_agent(user_id: str, session_id: str) -> Agent:
    """
    Create a basic agent with Gateway MCP tools, Alpha Vantage MCP tools, and memory integration.

    This function sets up an agent that can access tools from two MCP servers:
    1. AgentCore Gateway - Custom Lambda-based tools (text analysis, etc.)
    2. Alpha Vantage MCP - 100+ financial data tools (stocks, indicators, fundamentals, etc.)
    
    The agent also has Code Interpreter capabilities and maintains conversation memory.
    It handles authentication for both MCP servers and configures the agent with access
    to all available tools. If either MCP connection fails, the error is raised.
    
    Args:
        user_id: Unique identifier for the user
        session_id: Unique identifier for the conversation session
        
    Returns:
        Agent: Configured Strands agent with all tools and memory
        
    Raises:
        ValueError: If required environment variables are missing
        Exception: If MCP client creation fails
    """
    system_prompt = """You are a helpful financial assistant with access to comprehensive tools:

1. Gateway Tools: Custom tools for text analysis and other utilities
2. Alpha Vantage Tools: 100+ financial data tools including:
   - Stock prices and quotes (TIME_SERIES_DAILY, GLOBAL_QUOTE, etc.)
   - Technical indicators (RSI, MACD, Bollinger Bands, SMA, EMA, etc.)
   - Fundamental data (COMPANY_OVERVIEW, EARNINGS, INCOME_STATEMENT, etc.)
   - Options data, Forex, Crypto, Commodities
   - Economic indicators and market news
3. Code Interpreter: Execute Python code for analysis and visualization

When asked about stocks or financial data, use the Alpha Vantage tools.
When asked about text analysis, use the Gateway tools.
Always explain what tools you're using and why."""

    bedrock_model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0", temperature=0.1
    )

    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        raise ValueError("MEMORY_ID environment variable is required")

    # Configure AgentCore Memory
    agentcore_memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id, session_id=session_id, actor_id=user_id
    )

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=agentcore_memory_config,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )

    # Initialize Code Interpreter tools with boto3 session
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    session = boto3.Session(region_name=region)
    code_tools = StrandsCodeInterpreterTools(region)

    try:
        print("[AGENT] Starting agent creation with multiple MCP servers...")

        # Get OAuth2 access token and create Gateway MCP client
        print("[AGENT] Step 1: Getting OAuth2 access token for Gateway...")
        access_token = get_gateway_access_token()
        print(f"[AGENT] Got access token: {access_token[:20]}...")

        # Create Gateway MCP client with authentication
        print("[AGENT] Step 2: Creating Gateway MCP client...")
        gateway_client = create_gateway_mcp_client(access_token)
        print("[AGENT] Gateway MCP client created successfully")

        # Create Alpha Vantage MCP client
        print("[AGENT] Step 3: Creating Alpha Vantage MCP client...")
        alpha_vantage_client = create_alpha_vantage_mcp_client()
        print("[AGENT] Alpha Vantage MCP client created successfully")

        print(
            "[AGENT] Step 4: Creating Agent with Gateway tools, Alpha Vantage tools, and Code Interpreter..."
        )
        agent = Agent(
            name="FinancialAgent",
            system_prompt=system_prompt,
            tools=[
                gateway_client,           # Custom Lambda tools via Gateway
                alpha_vantage_client,     # Alpha Vantage financial tools
                code_tools.execute_python_securely  # Code Interpreter
            ],
            model=bedrock_model,
            session_manager=session_manager,
            trace_attributes={
                "user.id": user_id,
                "session.id": session_id,
            },
        )
        print(
            "[AGENT] Agent created successfully with Gateway tools, Alpha Vantage tools, and Code Interpreter"
        )
        return agent

    except Exception as e:
        print(f"[AGENT ERROR] Error creating MCP clients: {e}")
        print(f"[AGENT ERROR] Exception type: {type(e).__name__}")
        print("[AGENT ERROR] Traceback:")
        traceback.print_exc()
        print(
            "[AGENT] MCP connection failed - raising exception"
        )
        raise


@app.entrypoint
async def agent_stream(payload, context: RequestContext):
    """
    Main entrypoint for the agent using streaming with Gateway integration.

    This is the function that AgentCore Runtime calls when the agent receives a request.
    It extracts the user's query from the payload, securely obtains the user ID from
    the validated JWT token in the request context, creates an agent with Gateway tools
    and memory, and streams the response back. This function handles the complete
    request lifecycle with token-level streaming. The user ID is extracted from the 
    JWT token (via RequestContext).
    """
    user_query = payload.get("prompt")
    session_id = payload.get("runtimeSessionId")

    if not all([user_query, session_id]):
        yield {
            "status": "error",
            "error": "Missing required fields: prompt or runtimeSessionId",
        }
        return

    try:
        # Extract user ID securely from the validated JWT token
        # instead of trusting the payload body (which could be manipulated)
        user_id = extract_user_id_from_context(context)

        print(
            f"[STREAM] Starting streaming invocation for user: {user_id}, session: {session_id}"
        )
        print(f"[STREAM] Query: {user_query}")

        agent = create_basic_agent(user_id, session_id)

        # Use the agent's stream_async method for true token-level streaming
        async for event in agent.stream_async(user_query):
            yield json.loads(json.dumps(dict(event), default=str))

    except Exception as e:
        print(f"[STREAM ERROR] Error in agent_stream: {e}")
        traceback.print_exc()
        yield {"status": "error", "error": str(e)}


if __name__ == "__main__":
    app.run()
