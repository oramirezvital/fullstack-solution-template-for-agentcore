# Code Review and Optimization Plan

## Review Date: February 23, 2026
## Scope: Strands Agent and AgentCore Best Practices

---

## Executive Summary

After reviewing the codebase against Strands and AgentCore best practices, the implementation is **generally solid** with a few areas for optimization. The code follows official patterns correctly, but there are opportunities to improve error handling, resource management, and code organization.

---

## Current State Assessment

### ✅ What's Done Well

1. **MCP Integration**
   - Correctly uses `MCPClient` directly without wrappers (follows official FAST pattern)
   - Proper use of `streamablehttp_client` for HTTP-based MCP servers
   - Clean separation between Alpha Vantage MCP and Gateway MCP clients

2. **Memory Integration**
   - Proper use of `AgentCoreMemorySessionManager` with `AgentCoreMemoryConfig`
   - Well-configured retrieval strategies for investment tracking
   - Appropriate namespace design (`/investments/{actorId}`, `/preferences/{actorId}`)

3. **Security**
   - Secure user ID extraction from JWT token (prevents prompt injection)
   - API keys stored in Secrets Manager (not hardcoded)
   - Proper OAuth2 client credentials flow for Gateway authentication

4. **Streaming**
   - Correct use of `agent.stream_async()` for token-level streaming
   - Proper async/await patterns

5. **Documentation**
   - Comprehensive docstrings with type hints
   - Clear comments explaining design decisions
   - Good inline documentation

### ⚠️ Areas for Improvement

1. **Resource Management**
   - MCPClient lifecycle not explicitly managed
   - Code Interpreter cleanup not called
   - No context manager usage for resources

2. **Error Handling**
   - Generic exception catching in some places
   - Missing specific error types for better debugging
   - No retry logic for transient failures

3. **Configuration**
   - Environment variable access scattered throughout code
   - No centralized configuration validation
   - Missing default values for optional settings

4. **Code Organization**
   - Large system prompt embedded in code (should be external)
   - Agent creation function is very long (400+ lines)
   - Mixing concerns (MCP client creation + agent creation)

5. **Testing**
   - No unit tests for agent creation
   - No integration tests for MCP clients
   - No mocking for external dependencies

6. **Performance**
   - Agent created on every request (no caching)
   - MCP client created on every request
   - No connection pooling for HTTP clients

---

## Optimization Recommendations

### Priority 1: Critical (Implement Immediately)

#### 1.1 Add Proper Resource Management

**Issue**: MCPClient and Code Interpreter sessions are not properly cleaned up.

**Impact**: Resource leaks, potential memory issues, orphaned sessions.

**Solution**: Implement context managers and cleanup logic.

**Files to modify**:
- `patterns/strands-single-agent/basic_agent.py`

**Changes**:
```python
# Add cleanup in agent_stream function
try:
    agent = create_investment_advisor_agent(user_id, session_id)
    async for event in agent.stream_async(user_query):
        yield json.loads(json.dumps(dict(event), default=str))
finally:
    # Cleanup resources
    if hasattr(agent, 'session_manager'):
        # Session manager cleanup is automatic, but we can be explicit
        pass
    # Note: MCPClient cleanup is handled by Strands when passed to Agent
```

#### 1.2 Improve Error Handling

**Issue**: Generic exception catching makes debugging difficult.

**Impact**: Hard to diagnose issues in production, poor error messages to users.

**Solution**: Add specific exception types and better error messages.

**Files to modify**:
- `patterns/strands-single-agent/basic_agent.py`
- `patterns/utils/auth.py`

**Changes**:
```python
# In create_alpha_vantage_mcp_client
try:
    api_key = get_secret(f"/{stack_name}/alpha_vantage_api_key")
except ValueError as e:
    logger.error(f"Failed to retrieve API key: {e}")
    raise ValueError(
        f"Alpha Vantage API key not configured. "
        f"Please update the secret in AWS Secrets Manager: "
        f"/{stack_name}/alpha_vantage_api_key"
    ) from e
except Exception as e:
    logger.error(f"Unexpected error retrieving API key: {e}")
    raise RuntimeError(
        f"Failed to initialize Alpha Vantage client: {str(e)}"
    ) from e
```

#### 1.3 Add Configuration Validation

**Issue**: Environment variables accessed without validation.

**Impact**: Runtime errors that could be caught at startup.

**Solution**: Create configuration class with validation.

**Files to create**:
- `patterns/strands-single-agent/config.py`

**Implementation**:
```python
"""Configuration management for Investment Advisor agent."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentConfig:
    """Configuration for Investment Advisor agent."""
    
    memory_id: str
    stack_name: str
    aws_region: str
    gateway_url: Optional[str] = None
    
    @classmethod
    def from_environment(cls) -> "AgentConfig":
        """
        Load configuration from environment variables.
        
        Returns:
            AgentConfig: Validated configuration
            
        Raises:
            ValueError: If required environment variables are missing
        """
        memory_id = os.environ.get("MEMORY_ID")
        if not memory_id:
            raise ValueError("MEMORY_ID environment variable is required")
        
        stack_name = os.environ.get("STACK_NAME")
        if not stack_name:
            raise ValueError("STACK_NAME environment variable is required")
        
        aws_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        gateway_url = os.environ.get("GATEWAY_URL")
        
        return cls(
            memory_id=memory_id,
            stack_name=stack_name,
            aws_region=aws_region,
            gateway_url=gateway_url,
        )
    
    def validate(self) -> None:
        """
        Validate configuration values.
        
        Raises:
            ValueError: If configuration is invalid
        """
        if not self.memory_id.strip():
            raise ValueError("MEMORY_ID cannot be empty")
        
        if not self.stack_name.strip():
            raise ValueError("STACK_NAME cannot be empty")
```

### Priority 2: Important (Implement Soon)

#### 2.1 Extract System Prompt to External File

**Issue**: 400+ line system prompt embedded in code.

**Impact**: Hard to maintain, version, and test prompt changes.

**Solution**: Move to external file with template support.

**Files to create**:
- `patterns/strands-single-agent/prompts/investment_advisor.txt`

**Files to modify**:
- `patterns/strands-single-agent/basic_agent.py`

**Implementation**:
```python
def load_system_prompt() -> str:
    """
    Load system prompt from external file.
    
    Returns:
        str: System prompt text
    """
    prompt_path = os.path.join(
        os.path.dirname(__file__),
        "prompts",
        "investment_advisor.txt"
    )
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()
```

#### 2.2 Refactor Agent Creation Function

**Issue**: `create_investment_advisor_agent` is too long (150+ lines).

**Impact**: Hard to test, maintain, and understand.

**Solution**: Break into smaller, focused functions.

**Files to modify**:
- `patterns/strands-single-agent/basic_agent.py`

**Implementation**:
```python
def create_memory_config(
    memory_id: str,
    session_id: str,
    user_id: str
) -> AgentCoreMemoryConfig:
    """
    Create AgentCore Memory configuration for investment tracking.
    
    Args:
        memory_id: AgentCore Memory resource ID
        session_id: Conversation session ID
        user_id: User identifier
        
    Returns:
        AgentCoreMemoryConfig: Configured memory settings
    """
    return AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=session_id,
        actor_id=user_id,
        retrieval_config={
            "/investments/{actorId}": RetrievalConfig(
                top_k=50,
                relevance_score=0.3,
            ),
            "/preferences/{actorId}": RetrievalConfig(
                top_k=10,
                relevance_score=0.5,
            ),
        },
    )


def create_tools(region: str) -> list:
    """
    Create and configure agent tools.
    
    Args:
        region: AWS region for Code Interpreter
        
    Returns:
        list: Configured tools for the agent
    """
    alpha_vantage_client = create_alpha_vantage_mcp_client()
    code_tools = StrandsCodeInterpreterTools(region)
    
    return [
        alpha_vantage_client,
        code_tools.execute_python_securely,
    ]


def create_investment_advisor_agent(
    user_id: str,
    session_id: str,
    config: AgentConfig
) -> Agent:
    """
    Create Investment Advisor agent (simplified).
    
    Args:
        user_id: User identifier
        session_id: Session identifier
        config: Agent configuration
        
    Returns:
        Agent: Configured agent instance
    """
    system_prompt = load_system_prompt()
    bedrock_model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        temperature=0.1
    )
    
    memory_config = create_memory_config(config.memory_id, session_id, user_id)
    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=memory_config,
        region_name=config.aws_region,
    )
    
    tools = create_tools(config.aws_region)
    
    return Agent(
        name="InvestmentAdvisor",
        system_prompt=system_prompt,
        tools=tools,
        model=bedrock_model,
        session_manager=session_manager,
        trace_attributes={
            "user.id": user_id,
            "session.id": session_id,
        },
    )
```

#### 2.3 Add Logging Configuration

**Issue**: Inconsistent logging (print statements mixed with logger).

**Impact**: Hard to debug in production, no log levels.

**Solution**: Standardize on Python logging module.

**Files to modify**:
- `patterns/strands-single-agent/basic_agent.py`

**Implementation**:
```python
import logging

# Configure logging at module level
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Replace all print() statements with logger calls
logger.info("[AGENT] Starting Investment Advisor agent creation...")
logger.error("[AGENT ERROR] Error creating Investment Advisor agent: %s", e)
```

### Priority 3: Nice to Have (Future Improvements)

#### 3.1 Add Caching for Agent/Client Creation

**Issue**: Agent and MCP clients created on every request.

**Impact**: Slower response times, unnecessary overhead.

**Solution**: Implement caching with TTL.

**Note**: This requires careful consideration of thread safety and session isolation.

#### 3.2 Add Retry Logic for Transient Failures

**Issue**: No retry for network errors or rate limits.

**Impact**: Failures on transient issues.

**Solution**: Use `tenacity` library for retries.

**Implementation**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def get_secret_with_retry(secret_name: str) -> str:
    """Get secret with automatic retry on transient failures."""
    return get_secret(secret_name)
```

#### 3.3 Add Unit Tests

**Issue**: No automated tests.

**Impact**: Risk of regressions, hard to refactor.

**Solution**: Add pytest-based tests.

**Files to create**:
- `patterns/strands-single-agent/tests/test_agent.py`
- `patterns/strands-single-agent/tests/test_config.py`
- `patterns/strands-single-agent/tests/test_mcp_clients.py`

#### 3.4 Add Metrics and Monitoring

**Issue**: No custom metrics for agent performance.

**Impact**: Hard to monitor agent health and performance.

**Solution**: Add CloudWatch custom metrics.

**Implementation**:
```python
import boto3

cloudwatch = boto3.client('cloudwatch')

def record_agent_metric(metric_name: str, value: float, unit: str = 'Count'):
    """Record custom CloudWatch metric."""
    cloudwatch.put_metric_data(
        Namespace='InvestmentAdvisor',
        MetricData=[{
            'MetricName': metric_name,
            'Value': value,
            'Unit': unit,
        }]
    )
```

---

## Implementation Priority

### Phase 1: Critical Fixes (Week 1)
1. Add proper resource management
2. Improve error handling
3. Add configuration validation

### Phase 2: Code Quality (Week 2)
1. Extract system prompt to file
2. Refactor agent creation function
3. Standardize logging

### Phase 3: Enhancements (Week 3+)
1. Add caching
2. Add retry logic
3. Add unit tests
4. Add metrics

---

## Testing Strategy

### Unit Tests
- Test configuration validation
- Test MCP client creation
- Test memory config creation
- Test error handling paths

### Integration Tests
- Test agent creation end-to-end
- Test MCP tool invocation
- Test memory retrieval
- Test streaming responses

### Load Tests
- Test concurrent requests
- Test memory usage under load
- Test MCP client connection pooling

---

## Success Metrics

1. **Reliability**: Zero resource leaks, proper cleanup
2. **Maintainability**: Smaller functions (<50 lines), clear separation of concerns
3. **Debuggability**: Specific error messages, structured logging
4. **Performance**: <100ms agent creation time (with caching)
5. **Quality**: >80% test coverage

---

## Risks and Mitigation

### Risk 1: Breaking Changes
**Mitigation**: Implement changes incrementally, test thoroughly

### Risk 2: Performance Regression
**Mitigation**: Benchmark before/after, monitor metrics

### Risk 3: Compatibility Issues
**Mitigation**: Follow official Strands/AgentCore patterns, test with latest versions

---

## Conclusion

The current implementation is solid and follows best practices. The recommended optimizations will improve:
- **Reliability**: Better resource management and error handling
- **Maintainability**: Cleaner code organization and external prompts
- **Debuggability**: Structured logging and specific errors
- **Performance**: Caching and retry logic

All changes maintain compatibility with Strands and AgentCore official patterns.
