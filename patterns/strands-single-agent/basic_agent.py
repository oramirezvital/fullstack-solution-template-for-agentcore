import json
import logging
import os
import traceback
from datetime import datetime

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


def create_tavily_mcp_client() -> MCPClient:
    """
    Create MCP client for Tavily web search API.
    
    Tavily provides AI-optimized web search perfect for financial research,
    news, and market intelligence. The client connects to Tavily's hosted
    MCP server using an API key for authentication.
    
    This function creates a direct connection to Tavily's Remote MCP server following
    the same pattern as Alpha Vantage. This ensures proper ToolProvider interface
    implementation and automatic lifecycle management.
    
    The API key is securely retrieved from AWS Secrets Manager at runtime, ensuring
    it is never hardcoded in the source code or exposed in git.
    
    Returns:
        MCPClient: Configured client for Tavily MCP server
        
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
    
    logger.info("Retrieving Tavily API key from Secrets Manager...")
    
    # Fetch API key from Secrets Manager with proper error handling
    try:
        api_key = get_secret(f"/{stack_name}/tavily_api_key")
    except ValueError as e:
        logger.error("Failed to retrieve Tavily API key: %s", e)
        raise ValueError(
            f"Tavily API key not found in Secrets Manager. "
            f"Please create the secret: /{stack_name}/tavily_api_key"
        ) from e
    except Exception as e:
        logger.error("Unexpected error retrieving Tavily API key: %s", e)
        raise RuntimeError(
            f"Failed to retrieve Tavily API key from Secrets Manager: {str(e)}"
        ) from e
    
    # Validate API key
    if not api_key or api_key == "PLACEHOLDER_UPDATE_AFTER_DEPLOYMENT":
        raise ValueError(
            "Tavily API key not configured. "
            "Please update the secret in AWS Secrets Manager: "
            f"/{stack_name}/tavily_api_key"
        )
    
    logger.info("Creating Tavily MCP client...")
    
    # Tavily MCP server URL with API key authentication
    # Note: Tavily uses 'tavilyApiKey' parameter (not 'apikey')
    tavily_url = f"https://mcp.tavily.com/mcp/?tavilyApiKey={api_key}"
    
    try:
        # Create MCP client for Tavily - direct connection, no wrapper
        # This follows the official FAST pattern and ensures proper ToolProvider interface
        tavily_client = MCPClient(
            lambda: streamablehttp_client(url=tavily_url),
            prefix="tavily",
        )
        logger.info("Tavily MCP client created successfully")
        return tavily_client
    except Exception as e:
        logger.error("Failed to create Tavily MCP client: %s", e)
        raise RuntimeError(
            f"Failed to initialize Tavily MCP client: {str(e)}"
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
        transaction_date: str = None,
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
            transaction_date: Date of transaction in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
                            Defaults to current date if not provided. Use this for historical transactions. (optional)
            
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
            transaction_date=transaction_date,
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
    def delete_investment(
        self,
        user_id: str,
        transaction_id: str
    ) -> str:
        """
        Delete an investment transaction from the portfolio.
        
        Use this tool when a user wants to remove an incorrect or unwanted transaction.
        This permanently deletes the transaction and cannot be undone.
        
        Args:
            user_id: User identifier
            transaction_id: Transaction ID to delete (from get_portfolio_performance)
            
        Returns:
            JSON string with deletion confirmation
        """
        result = self.tracker.delete_investment(
            user_id=user_id,
            transaction_id=transaction_id
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
    
    @tool
    def export_portfolio_to_excel(self, user_id: str) -> str:
        """
        Export portfolio details to an Excel file.
        
        Generates a comprehensive Excel workbook with multiple sheets:
        - Summary: Overall portfolio performance metrics
        - Transactions: Complete transaction history
        - Active Positions: Current holdings
        - Forecasts: Forecast accuracy analysis
        
        The Excel file is returned as base64-encoded data that the frontend
        can download automatically.
        
        Args:
            user_id: User identifier
            
        Returns:
            JSON string with base64-encoded Excel file and metadata
        """
        from utils.excel_export import create_portfolio_excel
        
        # Get full portfolio data with all transaction details
        summary = self.tracker.get_performance_summary(user_id=user_id)
        full_positions = self.tracker.get_active_positions(user_id=user_id)
        
        # Merge summary metrics with full position details
        portfolio_data = {
            "total_positions": summary.get('total_positions', 0),
            "total_invested": summary.get('total_invested', 0),
            "current_value": summary.get('current_value', 0),
            "total_gain_loss": summary.get('total_gain_loss', 0),
            "total_gain_loss_pct": summary.get('total_gain_loss_pct', 0),
            "positions": full_positions  # Use full transaction data
        }
        
        # Generate Excel file
        excel_base64 = create_portfolio_excel(
            portfolio_data=portfolio_data,
            user_email=user_id
        )
        
        # Return with metadata
        result = {
            "success": True,
            "filename": f"portfolio_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "data": excel_base64,
            "size_kb": len(excel_base64) * 3 / 4 / 1024,  # Approximate size
            "sheets": ["Summary", "Transactions", "Active Positions", "Forecasts"],
            "total_positions": portfolio_data.get('total_positions', 0)
        }
        
        return json.dumps(result, default=str)


def create_investment_advisor_agent(user_id: str, session_id: str) -> Agent:
    """
    Create an Investment Advisor agent with Alpha Vantage financial data, Tavily web search,
    Code Interpreter, and long-term memory for portfolio tracking.

    This function sets up a specialized investment advisor that can:
    1. Access 100+ Alpha Vantage financial tools (stocks, indicators, fundamentals)
    2. Search the web for news, research, and market intelligence (Tavily)
    3. Execute Python code for calculations and chart generation
    4. Remember user investments and preferences across sessions using long-term memory
    
    The agent uses AgentCore Memory with three strategies:
    - SemanticMemoryStrategy: Extracts investment facts (purchases, positions)
    - UserPreferenceMemoryStrategy: Learns risk tolerance and investment preferences
    - SummaryMemoryStrategy: Summarizes investment decisions and sessions
    
    Args:
        user_id: Unique identifier for the user (used for memory namespacing)
        session_id: Unique identifier for the conversation session
        
    Returns:
        Agent: Configured investment advisor agent with financial tools, web search, and memory
        
    Raises:
        ValueError: If required environment variables (MEMORY_ID, STACK_NAME) are missing
        Exception: If MCP client creation or memory configuration fails
    """
    system_prompt = f"""You are an Investment Advisor. User ID: {user_id}

TOOLS AVAILABLE:
• Alpha Vantage MCP (alphavantage_*): Stock quotes, indicators, fundamentals, earnings
• Tavily MCP (tavily_*): Web search, news, analyst reports - ALWAYS cite sources with URLs
• Investment tracking: record_investment, get_portfolio_performance, update_investment_price, delete_investment, compare_forecast_actual, export_portfolio_to_excel
• Charts: Return JSON in markdown code blocks (```json) for visualization (line, bar, area, pie)
• Code Interpreter: Analysis ONLY - NO direct HTTP calls to Alpha Vantage

CRITICAL RULES:
• ALWAYS use user_id {user_id} for investment tools
• Use MCP tools (alphavantage_*, tavily_*) - NOT Code Interpreter for API calls
• Memory persists across sessions - recall user preferences and past investments
• Accept ALL dates as provided - do NOT assume future dates are typos (we are in February 2026)

RESPONSE STYLE:
• Be concise and direct (under 200 words unless asked for details)
• Lead with key insights, offer deeper analysis on request
• Use bullet points for clarity
• Include charts for trends/comparisons

WORKFLOWS:

Investment Recording:
1. Confirm: symbol, units, price, date, forecast (target price, timeframe, expected return)
2. Call record_investment with all details (include transaction_date for historical transactions)
3. Acknowledge: "Recorded [X] shares of [SYMBOL] at $[price] on [date], total $[total]"

Delete Transactions:
1. Get current portfolio with get_portfolio_performance to see transaction_ids
2. For each transaction to delete, call delete_investment(user_id, transaction_id)
3. Confirm: "Deleted [X] transactions"

Portfolio Performance:
1. Call get_portfolio_performance
2. Fetch current prices (alphavantage_GLOBAL_QUOTE)
3. Update with update_investment_price
4. Show: total invested vs current value, gain/loss %, individual positions
5. Create performance chart

Export Portfolio:
1. Call export_portfolio_to_excel(user_id="{user_id}")
2. Confirm: "Generated portfolio export with [X] positions across 4 sheets. Download starting."

Chart Generation:
1. Fetch data via Alpha Vantage MCP
2. Process with Code Interpreter if needed
3. Return JSON in YOUR response (not Code Interpreter output):
```json
{{
  "type": "chart",
  "chartType": "line",
  "title": "Stock Price Trend",
  "data": {{
    "labels": ["Date1", "Date2"],
    "datasets": [{{"label": "Price", "data": [100, 105], "color": "#3fb950"}}]
  }},
  "options": {{"yAxisLabel": "Price (USD)", "xAxisLabel": "Date"}}
}}
```
4. Provide brief context (current price, change %, insights)

DISCLAIMER: Educational purposes only. Not personalized financial advice. Consult qualified advisors for investment decisions."""

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
            "/investments/{{actorId}}": RetrievalConfig(
                top_k=50,  # Retrieve up to 50 investment records
                relevance_score=0.3,  # Lower threshold to capture all investments
            ),
            # Retrieve user investment preferences
            "/preferences/{{actorId}}": RetrievalConfig(
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

        # Create Tavily MCP client for web search
        logger.info("Creating Tavily MCP client...")
        tavily_client = create_tavily_mcp_client()
        logger.info("Tavily MCP client created successfully")

        # Create Investment Advisor agent with all tools
        logger.info("Creating Investment Advisor agent with Alpha Vantage, Tavily, Code Interpreter, and Investment Tracking...")
        agent = Agent(
            name="InvestmentAdvisor",
            system_prompt=system_prompt,
            tools=[
                alpha_vantage_client,  # Alpha Vantage financial tools
                tavily_client,  # Tavily web search tools
                code_tools.execute_python_securely,  # Code Interpreter for calculations
                tracking_tools.record_investment,  # Investment tracking tools
                tracking_tools.get_portfolio_performance,
                tracking_tools.update_investment_price,
                tracking_tools.delete_investment,  # Delete transactions
                tracking_tools.compare_forecast_actual,
                tracking_tools.export_portfolio_to_excel,  # Excel export
            ],
            model=bedrock_model,
            session_manager=session_manager,
            trace_attributes={
                "user.id": user_id,
                "session.id": session_id,
            },
        )
        logger.info("Investment Advisor agent created successfully with memory, financial tools, web search, and investment tracking")
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
