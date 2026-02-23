"""
Alpha Vantage API Response Cache using DynamoDB.

This module provides caching functionality for Alpha Vantage API responses
to reduce API calls and stay within rate limits (5 calls/minute, 25 calls/day).

The cache uses DynamoDB with TTL-based expiration. Cache keys are generated
from tool names, symbols, and parameter hashes to ensure uniqueness.

Cache TTL Strategy:
- Real-time quotes (GLOBAL_QUOTE): 60 seconds
- Daily time series (TIME_SERIES_DAILY, etc.): 86400 seconds (24 hours)
- Company fundamentals (COMPANY_OVERVIEW, EARNINGS, etc.): 604800 seconds (7 days)
- Technical indicators (RSI, MACD, SMA, etc.): 3600 seconds (1 hour)
- Default: 3600 seconds (1 hour)
"""

import hashlib
import json
import os
import time
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError


class AlphaVantageCache:
    """
    DynamoDB-based cache for Alpha Vantage API responses.
    
    This cache reduces API calls by storing responses with automatic TTL-based
    expiration. The cache is shared across all users since stock market data
    is public and identical for everyone.
    
    Attributes:
        table_name: Name of the DynamoDB table for caching
        dynamodb: Boto3 DynamoDB resource
        table: DynamoDB table object
    """
    
    # TTL values in seconds for different tool types
    TTL_REAL_TIME = 60  # 1 minute for real-time quotes
    TTL_DAILY = 86400  # 24 hours for daily time series
    TTL_FUNDAMENTALS = 604800  # 7 days for company fundamentals
    TTL_INDICATORS = 3600  # 1 hour for technical indicators
    TTL_DEFAULT = 3600  # 1 hour default
    
    # Tool name patterns for TTL determination
    REAL_TIME_TOOLS = {"GLOBAL_QUOTE", "CURRENCY_EXCHANGE_RATE"}
    DAILY_TOOLS = {
        "TIME_SERIES_DAILY",
        "TIME_SERIES_DAILY_ADJUSTED",
        "TIME_SERIES_WEEKLY",
        "TIME_SERIES_WEEKLY_ADJUSTED",
        "TIME_SERIES_MONTHLY",
        "TIME_SERIES_MONTHLY_ADJUSTED",
    }
    FUNDAMENTAL_TOOLS = {
        "COMPANY_OVERVIEW",
        "EARNINGS",
        "INCOME_STATEMENT",
        "BALANCE_SHEET",
        "CASH_FLOW",
        "EARNINGS_CALENDAR",
        "IPO_CALENDAR",
    }
    INDICATOR_TOOLS = {
        "SMA", "EMA", "WMA", "DEMA", "TEMA", "TRIMA", "KAMA", "MAMA", "T3",
        "MACD", "MACDEXT", "STOCH", "STOCHF", "RSI", "STOCHRSI", "WILLR",
        "ADX", "ADXR", "APO", "PPO", "MOM", "BOP", "CCI", "CMO", "ROC",
        "ROCR", "AROON", "AROONOSC", "MFI", "TRIX", "ULTOSC", "DX", "MINUS_DI",
        "PLUS_DI", "MINUS_DM", "PLUS_DM", "BBANDS", "MIDPOINT", "MIDPRICE",
        "SAR", "TRANGE", "ATR", "NATR", "AD", "ADOSC", "OBV", "HT_TRENDLINE",
        "HT_SINE", "HT_TRENDMODE", "HT_DCPERIOD", "HT_DCPHASE", "HT_PHASOR",
    }
    
    def __init__(self, table_name: Optional[str] = None, region_name: Optional[str] = None):
        """
        Initialize the Alpha Vantage cache.
        
        Args:
            table_name: Name of the DynamoDB table. If None, reads from CACHE_TABLE_NAME env var.
            region_name: AWS region name. If None, reads from AWS_DEFAULT_REGION env var.
            
        Raises:
            ValueError: If table_name is not provided and CACHE_TABLE_NAME env var is not set.
        """
        self.table_name = table_name or os.environ.get("CACHE_TABLE_NAME")
        if not self.table_name:
            raise ValueError(
                "Cache table name must be provided or set in CACHE_TABLE_NAME environment variable"
            )
        
        region = region_name or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        self.dynamodb = boto3.resource("dynamodb", region_name=region)
        self.table = self.dynamodb.Table(self.table_name)
        
        print(f"[CACHE] Initialized Alpha Vantage cache with table: {self.table_name}")
    
    def generate_cache_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Generate a unique cache key from tool name and arguments.
        
        The cache key format is: {tool_name}#{symbol}#{params_hash}
        
        Args:
            tool_name: Name of the Alpha Vantage tool (e.g., "TIME_SERIES_DAILY")
            arguments: Dictionary of tool arguments (e.g., {"symbol": "AAPL", "outputsize": "compact"})
            
        Returns:
            Unique cache key string
            
        Example:
            >>> cache.generate_cache_key("TIME_SERIES_DAILY", {"symbol": "AAPL", "outputsize": "compact"})
            "TIME_SERIES_DAILY#AAPL#a1b2c3d4"
        """
        # Extract symbol if present (most common parameter)
        symbol = arguments.get("symbol", arguments.get("from_currency", ""))
        
        # Create a stable hash of all arguments
        # Sort keys to ensure consistent hashing regardless of dict order
        args_str = json.dumps(arguments, sort_keys=True)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()[:8]
        
        # Format: tool_name#symbol#hash
        cache_key = f"{tool_name}#{symbol}#{args_hash}"
        return cache_key
    
    def get_ttl_for_tool(self, tool_name: str) -> int:
        """
        Determine the appropriate TTL (in seconds) for a given tool.
        
        Different types of financial data have different update frequencies:
        - Real-time quotes change every second
        - Daily time series data is finalized at market close
        - Company fundamentals change quarterly
        - Technical indicators need recalculation with new data
        
        Args:
            tool_name: Name of the Alpha Vantage tool
            
        Returns:
            TTL in seconds
            
        Example:
            >>> cache.get_ttl_for_tool("GLOBAL_QUOTE")
            60
            >>> cache.get_ttl_for_tool("TIME_SERIES_DAILY")
            86400
        """
        if tool_name in self.REAL_TIME_TOOLS:
            return self.TTL_REAL_TIME
        elif tool_name in self.DAILY_TOOLS:
            return self.TTL_DAILY
        elif tool_name in self.FUNDAMENTAL_TOOLS:
            return self.TTL_FUNDAMENTALS
        elif tool_name in self.INDICATOR_TOOLS:
            return self.TTL_INDICATORS
        else:
            return self.TTL_DEFAULT
    
    def get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a cached response from DynamoDB.
        
        Args:
            cache_key: Unique cache key generated by generate_cache_key()
            
        Returns:
            Cached response data as a dictionary, or None if not found or expired
            
        Note:
            DynamoDB automatically removes expired items based on the TTL attribute,
            but there may be a delay. This method does not perform additional
            expiration checks since DynamoDB handles it.
        """
        try:
            response = self.table.get_item(Key={"cache_key": cache_key})
            
            if "Item" in response:
                item = response["Item"]
                # Parse the JSON response data
                response_data = json.loads(item["response_data"])
                
                print(f"[CACHE HIT] Key: {cache_key}, Tool: {item.get('tool_name', 'unknown')}")
                return response_data
            else:
                print(f"[CACHE MISS] Key: {cache_key}")
                return None
                
        except ClientError as e:
            print(f"[CACHE ERROR] Failed to get cached response: {e}")
            # Return None on error to allow fallback to API call
            return None
    
    def set_cached_response(
        self,
        cache_key: str,
        tool_name: str,
        response_data: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Store a response in the DynamoDB cache.
        
        Args:
            cache_key: Unique cache key generated by generate_cache_key()
            tool_name: Name of the Alpha Vantage tool (for monitoring and TTL determination)
            response_data: API response data to cache (will be JSON-encoded)
            ttl_seconds: Optional custom TTL in seconds. If None, uses get_ttl_for_tool()
            
        Note:
            The expiration_time attribute is used by DynamoDB TTL to automatically
            delete expired items. There may be a delay of up to 48 hours for deletion,
            but expired items are not returned in queries.
        """
        try:
            # Determine TTL
            if ttl_seconds is None:
                ttl_seconds = self.get_ttl_for_tool(tool_name)
            
            # Calculate expiration time (current time + TTL)
            current_time = int(time.time())
            expiration_time = current_time + ttl_seconds
            
            # Store in DynamoDB
            self.table.put_item(
                Item={
                    "cache_key": cache_key,
                    "response_data": json.dumps(response_data),
                    "expiration_time": expiration_time,
                    "created_at": current_time,
                    "tool_name": tool_name,
                }
            )
            
            print(
                f"[CACHE SET] Key: {cache_key}, Tool: {tool_name}, "
                f"TTL: {ttl_seconds}s, Expires: {expiration_time}"
            )
            
        except ClientError as e:
            print(f"[CACHE ERROR] Failed to set cached response: {e}")
            # Don't raise exception - caching is optional, API call already succeeded
