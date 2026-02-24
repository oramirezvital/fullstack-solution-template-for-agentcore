import json
import logging
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
from mcp import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands_code_interpreter import StrandsCodeInterpreterTools

from utils.auth import extract_user_id_from_context
from utils.investment_tracker import InvestmentTracker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()


def create_alpha_vantage_mcp_client() -> MCPClient:
    """
    Create MCP client for Alpha Vantage financial data API.
    
    Alpha Vantage provides comprehensive financial market data through their MCP server.
    This includes stock prices, technical indicators, fundamental data, options, forex,
    crypto, commodities, and economic indicators. The client connects to Alpha Vantage's
    hosted MCP server using an API key for authentication.
    
    This function creates a direct connection to Alpha Vantage's MCP server following
    the official FAST pattern of passing MCPClient directly to the Agent. This ensures
    proper ToolProvider interface implementation and automatic lifecycle management.
    
    The API key is securely retrieved from AWS Secrets Manager at runtime, ensuring
    it is never hardcoded in the source code or exposed in git.
    
    Returns:
        MCPClient: Configured client for Alpha Vantage MCP server
        
    Raises:
        ValueError: If STACK_NAME environment variable is not set or API key is invalid
        RuntimeError: If API key cannot be retrieved from Secrets Manager
    """
    from utils.auth import get_secret
    
    # Get stack name for secret path
    stack_name = os.environ.get("STACK_NAME")
    if not stack_name:
        raise ValueError(
            "STACK_NAME environment variable is required. "
            "This should be set by the CDK deployment in backend-stack.ts"
        )
    
    logger.info("Retrieving Alpha Vantage API key from Secrets Manager...")
    
    # Fetch API key from Secrets Manager with proper error handling
    try:
        api_key = get_secret(f"/{stack_name}/alpha_vantage_api_key")
    except ValueError as e:
        logger.error("Failed to retrieve Alpha Vantage API key: %s", e)
        raise ValueError(
            f"Alpha Vantage API key not found in Secrets Manager. "
            f"Please create the secret: /{stack_name}/alpha_vantage_api_key"
        ) from e
    except Exception as e:
        logger.error("Unexpected error retrieving Alpha Vantage API key: %s", e)
        raise RuntimeError(
            f"Failed to retrieve Alpha Vantage API key from Secrets Manager: {str(e)}"
        ) from e
    
    # Validate API key
    if not api_key or api_key == "PLACEHOLDER_UPDATE_AFTER_DEPLOYMENT":
        raise ValueError(
            "Alpha Vantage API key not configured. "
            "Please update the secret in AWS Secrets Manager: "
            f"/{stack_name}/alpha_vantage_api_key"
        )
    
    logger.info("Creating Alpha Vantage MCP client...")
    
    # Alpha Vantage MCP server URL with API key authentication
    alpha_vantage_url = f"https://mcp.alphavantage.co/mcp?apikey={api_key}"
    
    try:
        # Create MCP client for Alpha Vantage - direct connection, no wrapper
        # This follows the official FAST pattern and ensures proper ToolProvider interface
        alpha_vantage_client = MCPClient(
            lambda: streamablehttp_client(url=alpha_vantage_url),
            prefix="alphavantage",
        )
        logger.info("Alpha Vantage MCP client created successfully")
        return alpha_vantage_client
    except Exception as e:
        logger.error("Failed to create Alpha Vantage MCP client: %s", e)
        raise RuntimeError(
            f"Failed to initialize Alpha Vantage MCP client: {str(e)}"
        ) from e


# Gateway MCP Client (currently not used for charts, but kept for future MCP tools)
# Uncomment and use this when adding other MCP tools via Gateway
#
# def create_gateway_mcp_client() -> MCPClient:
#     """
#     Create MCP client for AgentCore Gateway.
#     
#     The Gateway can provide access to multiple MCP tools implemented as Lambda functions.
#     This architecture is useful for MCP servers that have serialization issues or
#     require special runtime environments.
#     
#     The Gateway uses OAuth2 client credentials flow for authentication via Cognito.
#     
#     Returns:
#         MCPClient: Configured client for AgentCore Gateway
#         
#     Raises:
#         ValueError: If GATEWAY_URL environment variable is not set
#         Exception: If OAuth2 token retrieval fails
#     """
#     from utils.auth import get_gateway_access_token
#     
#     gateway_url = os.environ.get("GATEWAY_URL")
#     if not gateway_url:
#         raise ValueError("GATEWAY_URL environment variable is required")
#     
#     print("[AGENT] Creating Gateway MCP client...")
#     
#     # Get OAuth2 access token for Gateway authentication
#     # This uses the machine client credentials stored in SSM
#     access_token = get_gateway_access_token()
#     
#     # Create MCP client for Gateway with JWT authentication
#     gateway_client = MCPClient(
#         lambda: streamablehttp_client(
#             url=gateway_url,
#             headers={"Authorization": f"Bearer {access_token}"}
#         ),
#         prefix="gateway",
#     )
#     
#     print("[AGENT] Gateway MCP client created successfully")
#     return gateway_client


class InvestmentTrackingTools:
    """Strands wrapper for investment tracking tools."""
    
    def __init__(self, table_name: str, region: str):
        """
        Initialize investment tracking tools.
        
        Args:
            table_name: DynamoDB table name for investment transactions
            region: AWS region for DynamoDB client
        """
        self.tracker = InvestmentTracker(table_name=table_name, region=region)
    
    @tool
    def record_investment(
        self,
        user_id: str,
        symbol: str,
        company_name: str,
        units: float,
        price_per_unit: float,
        recommendation_reason: str,
        forecast_target_price: float = None,
        forecast_timeframe_days: int = None,
    ) -> str:
        """
        Record a new investment transaction based on recommendation.
        
        Use this tool when a user confirms they want to invest based on your recommendation.
        This creates a permanent record that can be used later to compare your forecast
        against actual performance.
        
        Args:
            user_id: User identifier
            symbol: Stock ticker symbol (e.g., 'AAPL', 'TSLA')
            company_name: Company name (e.g., 'Apple Inc.')
            units: Number of shares purchased
            price_per_unit: Purchase price per share
            recommendation_reason: Why you recommended this investment
            forecast_target_price: Your predicted target price (optional)
            forecast_timeframe_days: Forecast timeframe in days (optional)
            
        Returns:
            JSON string with transaction details
        """
        result = self.tracker.record_investment(
            user_id=user_id,
            symbol=symbol,
            company_name=company_name,
            units=units,
            price_per_unit=price_per_unit,
            recommendation_reason=recommendation_reason,
            forecast_target_price=forecast_target_price,
            forecast_timeframe_days=forecast_timeframe_days,
        )
        return json.dumps(result, default=str)
    
    @tool
    def get_portfolio_performance(self, user_id: str) -> str:
        """
        Get performance summary for all active investments.
        
        Use this tool when a user asks about their portfolio performance or wants
        to see how their investments are doing. This returns current values and
        gains/losses for all active positions.
        
        Args:
            user_id: User identifier
            
        Returns:
            JSON string with performance metrics including total invested,
            current value, gains/losses, and individual position details
        """
        result = self.tracker.get_performance_summary(user_id=user_id)
        return json.dumps(result, default=str)
    
    @tool
    def update_investment_price(
        self,
        user_id: str,
        transaction_id: str,
        current_price: float
    ) -> str:
        """
        Update the current price for an investment position.
        
        Use this tool to update the current market price for a specific investment.
        This recalculates gains/losses based on the new price.
        
        Args:
            user_id: User identifier
            transaction_id: Transaction ID to update
            current_price: Current market price
            
        Returns:
            JSON string with updated position details
        """
        result = self.tracker.update_position_price(
            user_id=user_id,
            transaction_id=transaction_id,
            current_price=current_price
        )
        return json.dumps(result, default=str)
    
    @tool
    def compare_forecast_actual(self, user_id: str, transaction_id: str) -> str:
        """
        Compare forecasted vs. actual performance for an investment.
        
        Use this tool to analyze how accurate your forecast was for a specific
        investment. This shows the predicted vs. actual returns and calculates
        forecast accuracy.
        
        Args:
            user_id: User identifier
            transaction_id: Transaction ID to analyze
            
        Returns:
            JSON string with forecast vs. actual comparison including
            accuracy percentage and performance difference
        """
        result = self.tracker.compare_forecast_vs_actual(
            user_id=user_id,
            transaction_id=transaction_id
        )
        return json.dumps(result, default=str)


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
   
   **CRITICAL: You MUST use the Alpha Vantage MCP tools (prefixed with "alphavantage_") to access 
   financial data. DO NOT use Code Interpreter to make direct HTTP calls to Alpha Vantage API.
   The MCP tools provide automatic error handling and proper data formatting.**
   
   Example tool calls:
   - alphavantage_TIME_SERIES_DAILY(symbol="AAPL", outputsize="compact")
   - alphavantage_GLOBAL_QUOTE(symbol="TSLA")
   - alphavantage_RSI(symbol="MSFT", interval="daily", time_period="14", series_type="close")
   - alphavantage_COMPANY_OVERVIEW(symbol="GOOGL")

2. CHART GENERATION (JSON format):
   - Return chart data as structured JSON in your response
   - Frontend will render interactive charts using React charting library
   - Supports chart types: line, bar, area, pie, doughnut
   - Perfect for visualizing financial data and trends

3. CODE INTERPRETER:
   - Perform statistical analysis and financial calculations ONLY
   - Process and transform data AFTER fetching it from Alpha Vantage MCP tools
   - Build custom financial models and projections
   - **DO NOT use Code Interpreter to make HTTP requests to Alpha Vantage API**
   - **DO NOT use urllib, requests, or any HTTP library to call Alpha Vantage directly**
   - Process and transform data for chart generation
   - Build custom financial models and projections

4. LONG-TERM MEMORY:
   - Your memory automatically learns and stores user investment preferences
   - You remember past investment decisions and portfolio positions
   - You recall user's risk tolerance, investment goals, and strategies
   - Memory persists across all conversations with this user

5. INVESTMENT TRACKING & PERFORMANCE ANALYSIS:
   - Record investments made based on your recommendations
   - Track transaction details (date, symbol, units, price)
   - Store forecast predictions (target price, timeframe, expected return)
   - Compare forecasted vs. actual performance
   - Provide accountability for recommendations
   - Update prices and calculate gains/losses
   
   **Available Tools:**
   - record_investment: Store new investment transactions with forecasts
   - get_portfolio_performance: Retrieve current portfolio status
   - update_investment_price: Update current prices for positions
   - compare_forecast_actual: Analyze forecast accuracy

PORTFOLIO TRACKING WORKFLOW:

When a user reports an investment:
1. ALWAYS acknowledge with precise details:
   "I've recorded your investment: [shares] shares of [SYMBOL] at $[price] per share 
   on [date], total investment $[total]."
2. Your memory will automatically extract and store this investment fact
3. Be explicit about all details (symbol, shares, price, date) for accurate extraction

When a user asks about portfolio performance:
1. Use get_portfolio_performance tool to fetch tracked investments
2. For each position, fetch current prices from Alpha Vantage (alphavantage_GLOBAL_QUOTE)
3. Update prices using update_investment_price tool
4. Display comprehensive performance summary:
   - Total invested vs. current value
   - Overall gain/loss percentage
   - Individual position performance
   - Positions that hit forecast targets
5. Create visualizations showing performance over time
6. Provide insights and recommendations

INVESTMENT TRACKING WORKFLOW:

When making an investment recommendation:
1. Provide clear recommendation with detailed rationale
2. Include specific forecast:
   - Target price
   - Timeframe (days)
   - Expected return percentage
3. If user decides to invest, use record_investment tool:
   - Include all transaction details
   - Store your forecast for future comparison
   - Confirm recording with transaction ID

Example:
"I recommend buying 10 shares of AAPL at $185.50. Based on strong Q1 earnings,
I forecast a target price of $210 within 90 days (13.2% expected return).

Would you like me to record this investment for tracking?"

If user confirms:
record_investment(
    user_id="{user_id}",
    symbol="AAPL",
    company_name="Apple Inc.",
    units=10,
    price_per_unit=185.50,
    recommendation_reason="Strong Q1 earnings, positive analyst sentiment",
    forecast_target_price=210.00,
    forecast_timeframe_days=90
)

When analyzing recommendation accuracy:
1. Use compare_forecast_actual tool for specific investments
2. Show forecast vs. actual performance
3. Calculate forecast accuracy percentage
4. Explain factors that caused differences
5. Learn from outcomes to improve future recommendations
6. Be transparent about both successes and misses

CHART GENERATION WORKFLOW:

When user asks for a chart (e.g., "Chart the 1-week price trend for AMAZON"):

1. FETCH DATA from Alpha Vantage using MCP tools:
   - Use alphavantage_TIME_SERIES_DAILY tool for historical price data
   - Extract dates and prices from the response
   - Process data into simple arrays

2. PREPARE DATA in simple format:
   labels = ["Feb 11", "Feb 12", "Feb 13", ...]
   data_values = [204.08, 199.6, 198.79, ...]

3. RETURN CHART JSON in your response:
   CRITICAL: Wrap the JSON in a proper markdown code block
   IMPORTANT: Include the JSON directly in YOUR response text, NOT as Code Interpreter output!
   
   The code block must start with three backticks and the word json on the same line.
   Then the JSON object on new lines.
   Then three backticks to close.
   
   Example - your response should look EXACTLY like this:
   
   Here's the 1-week price trend for Tesla:
   
   (three backticks)json
   {
     "type": "chart",
     "chartType": "line",
     "title": "Tesla (TSLA) - 1 Week Price Trend",
     "data": {
       "labels": ["Feb 11", "Feb 12", "Feb 13"],
       "datasets": [{
         "label": "TSLA Price (USD)",
         "data": [448.25, 451.90, 455.30],
         "color": "#3fb950"
       }]
     },
     "options": {
       "yAxisLabel": "Price (USD)",
       "xAxisLabel": "Date"
     }
   }
   (three backticks)
   
   Based on the data, Tesla's price increased by 1.6% this week.
   
   IMPORTANT: 
   - Use proper markdown code fence (three backticks, not the word "backticks")
   - Put "json" immediately after the opening backticks
   - Include JSON in YOUR message text, NOT in Code Interpreter output
   - You can use Code Interpreter to process data, but return the final chart JSON in your own response

4. PROVIDE CONTEXT:
   Along with the chart JSON, provide a brief summary:
   - Current price
   - Price change over the period
   - High and low prices
   - Key insights or trends

CHART TYPES FOR DIFFERENT USE CASES:
- line: Price trends, time series data (BEST for stock prices)
- bar: Comparisons, categorical data (good for comparing multiple stocks)
- area: Filled line charts showing volume/magnitude
- pie/doughnut: Portfolio allocation, market share percentages

CHART STYLING TIPS:
- Use green (#3fb950) for positive changes/gains
- Use red (#f85149) for negative changes/losses
- Use blue (#58a6ff) for neutral data
- Keep labels concise and readable

IMPORTANT RULES:
1. ALWAYS return chart data as JSON code blocks (not tool calls)
2. Fetch real data from Alpha Vantage first
3. Process data into simple arrays (labels and data values)
4. Provide context and insights along with the chart
5. Use appropriate chart types for different data

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

    # Initialize investment tracking tools
    table_name = os.environ.get("INVESTMENT_TABLE_NAME")
    if not table_name:
        raise ValueError(
            "INVESTMENT_TABLE_NAME environment variable is required. "
            "This should be set by the CDK deployment in backend-stack.ts"
        )
    
    tracking_tools = InvestmentTrackingTools(table_name=table_name, region=region)

    try:
        logger.info("Starting Investment Advisor agent creation...")

        # Create Alpha Vantage MCP client for financial data
        logger.info("Creating Alpha Vantage MCP client...")
        alpha_vantage_client = create_alpha_vantage_mcp_client()
        logger.info("Alpha Vantage MCP client created successfully")

        # Create Investment Advisor agent with all tools
        logger.info("Creating Investment Advisor agent with Alpha Vantage, Code Interpreter, and Investment Tracking...")
        agent = Agent(
            name="InvestmentAdvisor",
            system_prompt=system_prompt,
            tools=[
                alpha_vantage_client,  # Alpha Vantage financial tools
                code_tools.execute_python_securely,  # Code Interpreter for calculations
                tracking_tools.record_investment,  # Investment tracking tools
                tracking_tools.get_portfolio_performance,
                tracking_tools.update_investment_price,
                tracking_tools.compare_forecast_actual,
            ],
            model=bedrock_model,
            session_manager=session_manager,
            trace_attributes={
                "user.id": user_id,
                "session.id": session_id,
            },
        )
        logger.info("Investment Advisor agent created successfully with memory, financial tools, and investment tracking")
        return agent

    except Exception as e:
        logger.error("Error creating Investment Advisor agent: %s", e)
        logger.error("Exception type: %s", type(e).__name__)
        logger.error("Traceback:")
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
