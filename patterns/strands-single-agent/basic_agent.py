"""
Investment Advisor - Multi-Agent Entrypoint.

This module is the AgentCore Runtime entrypoint. It handles request lifecycle,
memory configuration, API key retrieval, and delegates all agent logic to the
multi-agent orchestrator defined in agents/orchestrator_agent.py.

Architecture (Hybrid ReWOO + Agents-as-Tools):

    Orchestrator Agent
    ├── market_data_specialist  → MarketDataAgent  (Alpha Vantage MCP)  [direct]
    ├── research_specialist     → ResearchAgent    (Tavily MCP)          [direct]
    ├── portfolio_specialist    → PortfolioAgent   (DynamoDB tracking)   [direct]
    └── run_investment_analysis → ReWOO Pipeline                         [analysis]
                                   ├── Planner    (decides which agents needed)
                                   ├── Executor   (parallel: market_data + research)
                                   │              (sequential: valuation after above)
                                   └── Synthesizer (Munger mental models → verdict)

Performance optimizations:
    - API keys cached at module level (retrieved once per cold start)
    - Sub-agents in the pipeline are lazily instantiated (only when needed)
    - Market data + research run concurrently via asyncio.gather
    - No temperature=1 (avoids extended thinking latency on valuation agent)
"""

import json
import logging
import os
import traceback

from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
    RetrievalConfig,
)
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext

from utils.auth import extract_user_id_from_context

# Configure structured logging for CloudWatch
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

# ---------------------------------------------------------------------------
# Module-level API key cache
# API keys are retrieved once on cold start and reused across requests.
# This avoids a Secrets Manager round-trip on every user request.
# ---------------------------------------------------------------------------
_cached_alpha_vantage_key: str | None = None
_cached_tavily_key: str | None = None


def _get_cached_api_key(secret_path: str, cache_attr: str) -> str:
    """
    Retrieve an API key from AWS Secrets Manager, caching the result in the module.

    On the first call the key is fetched from Secrets Manager and stored in a
    module-level variable. Subsequent calls return the cached value immediately,
    avoiding repeated network round-trips within the same Lambda/container instance.

    Args:
        secret_path: Full Secrets Manager path (e.g., '/FAST-stack/tavily_api_key')
        cache_attr: Name of the module-level cache variable (e.g., '_cached_tavily_key')

    Returns:
        str: The API key value

    Raises:
        ValueError: If the secret does not exist or contains a placeholder value
        RuntimeError: If Secrets Manager cannot be reached
    """
    global _cached_alpha_vantage_key, _cached_tavily_key

    # Return cached value if available
    cached = globals()[cache_attr]
    if cached is not None:
        return cached

    from utils.auth import get_secret

    try:
        api_key = get_secret(secret_path)
    except ValueError as e:
        logger.error("Secret not found at path '%s': %s", secret_path, e)
        raise ValueError(
            f"API key not found in Secrets Manager at path: {secret_path}. "
            "Please create the secret before deploying."
        ) from e
    except Exception as e:
        logger.error("Unexpected error retrieving secret '%s': %s", secret_path, e)
        raise RuntimeError(
            f"Failed to retrieve secret from Secrets Manager: {str(e)}"
        ) from e

    if not api_key or api_key == "PLACEHOLDER_UPDATE_AFTER_DEPLOYMENT":
        raise ValueError(
            f"API key at '{secret_path}' is not configured. "
            "Please update the secret in AWS Secrets Manager."
        )

    # Store in the correct module-level cache variable
    globals()[cache_attr] = api_key
    logger.info("API key cached for path: %s", secret_path)
    return api_key


def create_session_manager(
    memory_id: str,
    session_id: str,
    user_id: str,
    region: str,
) -> AgentCoreMemorySessionManager:
    """
    Create an AgentCore Memory session manager for long-term investment memory.

    Configures two memory namespaces:
    - /investments/{actorId}: Stores investment facts and transaction history
    - /preferences/{actorId}: Stores user risk tolerance and investment preferences

    Args:
        memory_id: AgentCore Memory resource ID (from CDK deployment)
        session_id: Unique session identifier for this conversation
        user_id: Authenticated user identifier for memory namespacing
        region: AWS region for the memory service

    Returns:
        AgentCoreMemorySessionManager: Configured session manager

    Raises:
        ValueError: If any required parameter is missing
    """
    if not memory_id:
        raise ValueError("memory_id is required and cannot be empty")
    if not session_id:
        raise ValueError("session_id is required and cannot be empty")
    if not user_id:
        raise ValueError("user_id is required and cannot be empty")
    if not region:
        raise ValueError("region is required and cannot be empty")

    agentcore_memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=session_id,
        actor_id=user_id,
        retrieval_config={
            # Retrieve investment facts - high top_k to capture full portfolio history
            "/investments/{{actorId}}": RetrievalConfig(
                top_k=50,
                relevance_score=0.3,  # Low threshold to capture all investment records
            ),
            # Retrieve user preferences - risk tolerance, preferred sectors, etc.
            "/preferences/{{actorId}}": RetrievalConfig(
                top_k=10,
                relevance_score=0.5,  # Medium threshold for relevant preferences only
            ),
        },
    )

    return AgentCoreMemorySessionManager(
        agentcore_memory_config=agentcore_memory_config,
        region_name=region,
    )


def create_investment_advisor_agent(user_id: str, session_id: str):
    """
    Create the multi-agent Investment Advisor orchestrator for a given user session.

    Retrieves all required environment variables, fetches API keys (with caching),
    configures long-term memory, and instantiates the orchestrator.

    Args:
        user_id: Authenticated user identifier (extracted from JWT token)
        session_id: Unique session identifier for this conversation

    Returns:
        Agent: Configured orchestrator agent ready to handle user queries

    Raises:
        ValueError: If required environment variables are missing or API keys
                    are not configured in Secrets Manager
        RuntimeError: If agent initialization fails
    """
    # Validate all required environment variables upfront - fail loudly if missing
    stack_name = os.environ.get("STACK_NAME")
    if not stack_name:
        raise ValueError(
            "STACK_NAME environment variable is required. "
            "This should be set by the CDK deployment in backend-stack.ts"
        )

    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        raise ValueError("MEMORY_ID environment variable is required")

    table_name = os.environ.get("INVESTMENT_TABLE_NAME")
    if not table_name:
        raise ValueError(
            "INVESTMENT_TABLE_NAME environment variable is required. "
            "This should be set by the CDK deployment in backend-stack.ts"
        )

    region = os.environ.get("AWS_DEFAULT_REGION")
    if not region:
        raise ValueError("AWS_DEFAULT_REGION environment variable is required")

    # Retrieve API keys with module-level caching (Secrets Manager called once per cold start)
    alpha_vantage_api_key = _get_cached_api_key(
        secret_path=f"/{stack_name}/alpha_vantage_api_key",
        cache_attr="_cached_alpha_vantage_key",
    )
    tavily_api_key = _get_cached_api_key(
        secret_path=f"/{stack_name}/tavily_api_key",
        cache_attr="_cached_tavily_key",
    )

    session_manager = create_session_manager(
        memory_id=memory_id,
        session_id=session_id,
        user_id=user_id,
        region=region,
    )

    from agents.orchestrator_agent import create_orchestrator_agent

    return create_orchestrator_agent(
        user_id=user_id,
        session_manager=session_manager,
        alpha_vantage_api_key=alpha_vantage_api_key,
        tavily_api_key=tavily_api_key,
        table_name=table_name,
        region=region,
    )


@app.entrypoint
async def agent_stream(payload: dict, context: RequestContext):
    """
    AgentCore Runtime entrypoint - handles all incoming requests with streaming.

    Extracts the user query and session ID from the payload, securely retrieves
    the user ID from the validated JWT token, creates the multi-agent orchestrator,
    and streams the response back token by token.

    Args:
        payload: Request payload containing 'prompt' and 'runtimeSessionId'
        context: RequestContext with validated JWT token for secure user identification

    Yields:
        dict: Streaming events (text chunks, tool calls, lifecycle events)
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
        # Extract user ID from the validated JWT token - never trust the payload body
        user_id = extract_user_id_from_context(context)

        logger.info(
            "Starting multi-agent stream for user: %s, session: %s",
            user_id,
            session_id,
        )
        logger.info("Query: %s", user_query)

        agent = create_investment_advisor_agent(
            user_id=user_id,
            session_id=session_id,
        )

        # Stream all agent events back to the client (text, tool calls, lifecycle)
        async for event in agent.stream_async(user_query):
            yield json.loads(json.dumps(dict(event), default=str))

    except Exception as e:
        logger.error("Error in agent_stream: %s", e)
        traceback.print_exc()
        yield {"status": "error", "error": str(e)}


if __name__ == "__main__":
    app.run()
