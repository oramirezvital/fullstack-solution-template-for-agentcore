"""
Cached wrapper for Alpha Vantage MCP Client.

This module provides a caching layer around the Alpha Vantage MCP client
to reduce API calls and stay within rate limits. It intercepts tool calls,
checks the cache, and only makes API calls when necessary.

The wrapper is transparent to the agent - it looks and behaves exactly like
a regular MCP client but with automatic caching.
"""

import json
from typing import Any, Callable, Dict, Optional

from strands.tools.mcp import MCPClient

from utils.alpha_vantage_cache import AlphaVantageCache


class CachedAlphaVantageMCPClient:
    """
    Wrapper around Alpha Vantage MCP Client with automatic caching.
    
    This class intercepts tool calls to the Alpha Vantage MCP server,
    checks the DynamoDB cache first, and only makes API calls when
    the data is not cached or has expired.
    
    The wrapper is designed to be a drop-in replacement for MCPClient
    in the agent's tool list.
    
    Attributes:
        mcp_client: The underlying Alpha Vantage MCP client
        cache: AlphaVantageCache instance for DynamoDB operations
        prefix: Tool name prefix (e.g., "alphavantage")
    """
    
    def __init__(
        self,
        mcp_client: MCPClient,
        cache: Optional[AlphaVantageCache] = None,
        table_name: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        """
        Initialize the cached MCP client wrapper.
        
        Args:
            mcp_client: The Alpha Vantage MCP client to wrap
            cache: Optional AlphaVantageCache instance. If None, creates a new one.
            table_name: DynamoDB table name (only used if cache is None)
            region_name: AWS region (only used if cache is None)
            
        Example:
            >>> from strands.tools.mcp import MCPClient
            >>> from mcp.client.streamable_http import streamablehttp_client
            >>> 
            >>> # Create base MCP client
            >>> base_client = MCPClient(
            ...     lambda: streamablehttp_client(url="https://mcp.alphavantage.co/mcp?apikey=KEY"),
            ...     prefix="alphavantage"
            ... )
            >>> 
            >>> # Wrap with caching
            >>> cached_client = CachedAlphaVantageMCPClient(
            ...     mcp_client=base_client,
            ...     table_name="my-stack-alpha-vantage-cache"
            ... )
        """
        self.mcp_client = mcp_client
        self.cache = cache or AlphaVantageCache(
            table_name=table_name,
            region_name=region_name
        )
        
        # Store the prefix from the original client
        self.prefix = getattr(mcp_client, 'prefix', 'alphavantage')
        
        print(f"[CACHED CLIENT] Initialized cached Alpha Vantage MCP client with prefix: {self.prefix}")
    
    async def __call__(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a tool call with caching.
        
        This method is called by the Strands agent when it wants to use a tool.
        It checks the cache first, and only calls the actual MCP server if needed.
        
        Args:
            tool_name: Name of the Alpha Vantage tool (e.g., "TIME_SERIES_DAILY")
            arguments: Dictionary of tool arguments
            
        Returns:
            Tool execution result (from cache or API)
            
        Note:
            This method maintains the same signature as MCPClient.__call__()
            so it can be used as a drop-in replacement.
        """
        # Generate cache key
        cache_key = self.cache.generate_cache_key(
            tool_name=tool_name,
            arguments=arguments
        )
        
        # Check cache first
        cached_response = self.cache.get_cached_response(cache_key=cache_key)
        
        if cached_response is not None:
            # Cache hit - return cached data
            print(f"[CACHED CLIENT] Returning cached response for {tool_name}")
            return cached_response
        
        # Cache miss - call the actual MCP server
        print(f"[CACHED CLIENT] Cache miss, calling Alpha Vantage API for {tool_name}")
        
        try:
            # Call the underlying MCP client
            response = await self.mcp_client(tool_name, arguments)
            
            # Cache the successful response
            # Convert response to dict if it's not already
            if isinstance(response, str):
                try:
                    response_dict = json.loads(response)
                except json.JSONDecodeError:
                    # If response is not JSON, wrap it
                    response_dict = {"result": response}
            elif isinstance(response, dict):
                response_dict = response
            else:
                # For other types, convert to dict
                response_dict = {"result": str(response)}
            
            # Only cache successful responses (not errors)
            # Check for common error indicators in Alpha Vantage responses
            if not self._is_error_response(response_dict):
                self.cache.set_cached_response(
                    cache_key=cache_key,
                    tool_name=tool_name,
                    response_data=response_dict
                )
            else:
                print(f"[CACHED CLIENT] Not caching error response for {tool_name}")
            
            return response
            
        except Exception as e:
            print(f"[CACHED CLIENT ERROR] Error calling Alpha Vantage API: {e}")
            # Re-raise the exception - don't cache errors
            raise
    
    def _is_error_response(self, response: Dict[str, Any]) -> bool:
        """
        Check if a response contains an error.
        
        Alpha Vantage returns errors in various formats:
        - {"Error Message": "..."}
        - {"Note": "API rate limit exceeded"}
        - {"Information": "...rate limit..."}
        
        Args:
            response: API response dictionary
            
        Returns:
            True if response contains an error, False otherwise
        """
        # Check for explicit error fields
        if "Error Message" in response:
            return True
        
        # Check for rate limit messages
        if "Note" in response:
            note = response["Note"].lower()
            if "rate limit" in note or "api call" in note:
                return True
        
        if "Information" in response:
            info = response["Information"].lower()
            if "rate limit" in info or "api call" in info or "premium" in info:
                return True
        
        return False
    
    def __getattr__(self, name: str) -> Any:
        """
        Delegate attribute access to the underlying MCP client.
        
        This allows the cached client to behave exactly like the original
        MCP client for any attributes or methods we don't explicitly override.
        
        Args:
            name: Attribute name
            
        Returns:
            Attribute value from the underlying MCP client
        """
        return getattr(self.mcp_client, name)
