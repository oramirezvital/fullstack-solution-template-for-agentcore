import json
import os
import traceback

import boto3
from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
    RetrievalConfig,
)
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands_code_interpreter import StrandsCodeInterpreterTools

from utils.auth import extract_user_id_from_context

app = BedrockAgentCoreApp()


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


def create_investment_advisor_agent(user_id: str, session_id: str) -> Agent:
    """
    Create an Investment Advisor agent with Alpha Vantage financial data, Code Interpreter,
    and long-term memory for portfolio tracking.

    This function sets up a specialized investment advisor that can:
    1. Access 100+ Alpha Vantage financial tools (stocks, indicators, fundamentals)
    2. Execute Python code for calculations and chart generation
    3. Remember user investments and preferences across sessions using long-term memory
    
    The agent uses AgentCore Memory with three strategies:
    - SemanticMemoryStrategy: Extracts investment facts (purchases, positions)
    - UserPreferenceMemoryStrategy: Learns risk tolerance and investment preferences
    - SummaryMemoryStrategy: Summarizes investment decisions and sessions
    
    Args:
        user_id: Unique identifier for the user (used for memory namespacing)
        session_id: Unique identifier for the conversation session
        
    Returns:
        Agent: Configured investment advisor agent with financial tools and memory
        
    Raises:
        ValueError: If required environment variables (MEMORY_ID, ALPHA_VANTAGE_API_KEY) are missing
        Exception: If MCP client creation or memory configuration fails
    """
    system_prompt = """You are an experienced Investment Advisor with access to comprehensive 
financial market data, analysis tools, and long-term memory of user portfolios.

YOUR CAPABILITIES:

1. ALPHA VANTAGE FINANCIAL DATA (100+ tools):
   - Real-time and historical stock prices (GLOBAL_QUOTE, TIME_SERIES_DAILY, etc.)
   - Technical indicators (RSI, MACD, Bollinger Bands, Moving Averages, etc.)
   - Fundamental data (COMPANY_OVERVIEW, EARNINGS, INCOME_STATEMENT, BALANCE_SHEET)
   - Market news and sentiment analysis
   - Options data, Forex, Crypto, Commodities, Economic indicators

2. CODE INTERPRETER:
   - Generate professional charts and visualizations (matplotlib, plotly)
   - Perform statistical analysis and financial calculations
   - Create comparative analyses and correlations
   - Build custom financial models and projections

3. LONG-TERM MEMORY:
   - Your memory automatically learns and stores user investment preferences
   - You remember past investment decisions and portfolio positions
   - You recall user's risk tolerance, investment goals, and strategies
   - Memory persists across all conversations with this user

PORTFOLIO TRACKING WORKFLOW:

When a user reports an investment:
1. ALWAYS acknowledge with precise details:
   "I've recorded your investment: [shares] shares of [SYMBOL] at $[price] per share 
   on [date], total investment $[total]."
2. Your memory will automatically extract and store this investment fact
3. Be explicit about all details (symbol, shares, price, date) for accurate extraction

When a user asks about portfolio performance:
1. Recall their investments from your memory
2. Fetch current prices from Alpha Vantage (use GLOBAL_QUOTE for latest price)
3. Calculate for each position:
   - Current value = shares × current_price
   - Gain/Loss = current_value - (shares × purchase_price)
   - Gain/Loss % = (gain_loss / invested_amount) × 100
4. Create a visualization showing performance over time
5. Provide detailed analysis with insights

CHART GENERATION EXAMPLES:

CRITICAL: Always return charts as base64-encoded images, NOT as saved files!

For price trends:
```python
import matplotlib.pyplot as plt
import pandas as pd
import base64
from io import BytesIO

# Create line chart with volume
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
ax1.plot(dates, prices, linewidth=2, color='#2E86AB')
ax1.set_ylabel('Price ($)', fontsize=12)
ax1.grid(True, alpha=0.3)
ax2.bar(dates, volumes, color='#A23B72', alpha=0.7)
ax2.set_ylabel('Volume', fontsize=12)
plt.tight_layout()

# IMPORTANT: Return as base64 image
buffer = BytesIO()
plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
buffer.seek(0)
image_base64 = base64.b64encode(buffer.read()).decode()
plt.close()
print(f"![Chart](data:image/png;base64,{image_base64})")
```

For portfolio performance:
```python
import matplotlib.pyplot as plt
import base64
from io import BytesIO

# Create portfolio performance chart
fig, ax = plt.subplots(figsize=(12, 6))
for symbol, data in portfolio.items():
    ax.plot(data['dates'], data['returns'], label=symbol, linewidth=2)
ax.axhline(y=0, color='black', linestyle='--', alpha=0.3)
ax.set_xlabel('Date')
ax.set_ylabel('Return (%)')
ax.set_title('Portfolio Performance', fontsize=16, fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3)

# IMPORTANT: Return as base64 image
buffer = BytesIO()
plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
buffer.seek(0)
image_base64 = base64.b64encode(buffer.read()).decode()
plt.close()
print(f"![Chart](data:image/png;base64,{image_base64})")
```

CHART GENERATION RULES:
1. ALWAYS use BytesIO buffer and base64 encoding
2. NEVER save to files (plt.savefig('file.png'))
3. Print the base64 image in markdown format: ![Chart](data:image/png;base64,...)
4. Close the plot with plt.close() after encoding
5. Use dpi=150 for good quality without huge file sizes

YOUR INVESTMENT ADVISORY APPROACH:

1. DATA-DRIVEN ANALYSIS:
   - Always fetch current market data before providing recommendations
   - Use both technical and fundamental analysis
   - Consider historical trends and patterns

2. RISK ASSESSMENT:
   - Discuss risk factors for each investment
   - Consider market conditions and volatility
   - Align recommendations with user's risk tolerance (from memory)

3. CLEAR COMMUNICATION:
   - Explain technical indicators in accessible terms
   - Provide context on industry trends and comparisons
   - Use visualizations to support your analysis

4. EDUCATIONAL APPROACH:
   - Help users understand investment concepts
   - Explain the reasoning behind your analysis
   - Suggest areas for further research

5. PROFESSIONAL DISCLAIMERS:
   - Always remind users that you provide information for educational purposes
   - Investment decisions should consider individual circumstances
   - Recommend consulting with qualified financial advisors for personalized advice

IMPORTANT REMINDERS:
- Be explicit when recording investments so memory extraction is accurate
- Always fetch current prices before calculating performance
- Create charts to visualize trends and performance
- Remember user preferences and reference them in your advice
- Provide balanced insights considering both opportunities and risks

DISCLAIMER: I provide investment information and analysis for educational purposes only. 
This is not personalized financial advice. Investment decisions should be made in 
consultation with qualified financial advisors, considering your individual circumstances, 
risk tolerance, and financial goals. Past performance does not guarantee future results."""

    bedrock_model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0", temperature=0.1
    )

    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        raise ValueError("MEMORY_ID environment variable is required")

    # Configure AgentCore Memory with long-term strategies for investment tracking
    # Retrieves from investment and preference namespaces to recall portfolio and user preferences
    agentcore_memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=session_id,
        actor_id=user_id,
        retrieval_config={
            # Retrieve investment facts with high top_k to get all investments
            "/investments/{actorId}": RetrievalConfig(
                top_k=50,  # Retrieve up to 50 investment records
                relevance_score=0.3,  # Lower threshold to capture all investments
            ),
            # Retrieve user investment preferences
            "/preferences/{actorId}": RetrievalConfig(
                top_k=10,  # Top 10 preferences
                relevance_score=0.5,  # Medium threshold for relevant preferences
            ),
        },
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
        print("[AGENT] Starting Investment Advisor agent creation...")

        # Create Alpha Vantage MCP client for financial data
        print("[AGENT] Creating Alpha Vantage MCP client...")
        alpha_vantage_client = create_alpha_vantage_mcp_client()
        print("[AGENT] Alpha Vantage MCP client created successfully")

        print("[AGENT] Creating Investment Advisor agent with Alpha Vantage tools and Code Interpreter...")
        agent = Agent(
            name="InvestmentAdvisor",
            system_prompt=system_prompt,
            tools=[
                alpha_vantage_client,  # Alpha Vantage financial tools
                code_tools.execute_python_securely,  # Code Interpreter for charts and calculations
            ],
            model=bedrock_model,
            session_manager=session_manager,
            trace_attributes={
                "user.id": user_id,
                "session.id": session_id,
            },
        )
        print("[AGENT] Investment Advisor agent created successfully with memory and financial tools")
        return agent

    except Exception as e:
        print(f"[AGENT ERROR] Error creating Investment Advisor agent: {e}")
        print(f"[AGENT ERROR] Exception type: {type(e).__name__}")
        print("[AGENT ERROR] Traceback:")
        traceback.print_exc()
        raise


@app.entrypoint
async def agent_stream(payload, context: RequestContext):
    """
    Main entrypoint for the Investment Advisor agent using streaming.

    This is the function that AgentCore Runtime calls when the agent receives a request.
    It extracts the user's query from the payload, securely obtains the user ID from
    the validated JWT token in the request context, creates an Investment Advisor agent
    with Alpha Vantage financial tools, Code Interpreter, and long-term memory, then
    streams the response back. This function handles the complete request lifecycle
    with token-level streaming. The user ID is extracted from the JWT token (via
    RequestContext) for secure memory namespacing.
    
    Args:
        payload: Request payload containing prompt and runtimeSessionId
        context: RequestContext with validated JWT token for user authentication
        
    Yields:
        dict: Streaming events from the agent (text chunks, tool calls, etc.)
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
            f"[STREAM] Starting Investment Advisor streaming for user: {user_id}, session: {session_id}"
        )
        print(f"[STREAM] Query: {user_query}")

        agent = create_investment_advisor_agent(user_id, session_id)

        # Use the agent's stream_async method for true token-level streaming
        async for event in agent.stream_async(user_query):
            yield json.loads(json.dumps(dict(event), default=str))

    except Exception as e:
        print(f"[STREAM ERROR] Error in agent_stream: {e}")
        traceback.print_exc()
        yield {"status": "error", "error": str(e)}


if __name__ == "__main__":
    app.run()
