#!/usr/bin/env python3
"""
Test script for Alpha Vantage cache functionality.

This script tests the cache layer by simulating tool calls and verifying
that responses are cached and retrieved correctly.
"""

import json
import os
import sys
import time

# Add patterns directory to path
sys.path.insert(0, 'patterns')

from utils.alpha_vantage_cache import AlphaVantageCache


def test_cache_operations():
    """Test basic cache operations: set, get, TTL calculation."""
    
    print("=" * 60)
    print("Testing Alpha Vantage Cache")
    print("=" * 60)
    
    # Initialize cache
    cache = AlphaVantageCache(
        table_name="FAST-stack-alpha-vantage-cache",
        region_name="us-east-1"
    )
    
    # Test 1: Cache key generation
    print("\n[TEST 1] Cache Key Generation")
    print("-" * 60)
    
    test_args = {
        "symbol": "AAPL",
        "outputsize": "compact"
    }
    
    cache_key = cache.generate_cache_key("TIME_SERIES_DAILY", test_args)
    print(f"Tool: TIME_SERIES_DAILY")
    print(f"Arguments: {test_args}")
    print(f"Cache Key: {cache_key}")
    assert "TIME_SERIES_DAILY#AAPL#" in cache_key, "Cache key format incorrect"
    print("✓ Cache key generation works correctly")
    
    # Test 2: TTL calculation
    print("\n[TEST 2] TTL Calculation")
    print("-" * 60)
    
    test_tools = {
        "GLOBAL_QUOTE": cache.TTL_REAL_TIME,
        "TIME_SERIES_DAILY": cache.TTL_DAILY,
        "COMPANY_OVERVIEW": cache.TTL_FUNDAMENTALS,
        "RSI": cache.TTL_INDICATORS,
        "UNKNOWN_TOOL": cache.TTL_DEFAULT,
    }
    
    for tool_name, expected_ttl in test_tools.items():
        actual_ttl = cache.get_ttl_for_tool(tool_name)
        print(f"{tool_name:20} -> {actual_ttl:6} seconds ({actual_ttl/3600:.1f} hours)")
        assert actual_ttl == expected_ttl, f"TTL mismatch for {tool_name}"
    
    print("✓ TTL calculation works correctly")
    
    # Test 3: Cache set and get
    print("\n[TEST 3] Cache Set and Get")
    print("-" * 60)
    
    test_response = {
        "Meta Data": {
            "1. Information": "Daily Prices",
            "2. Symbol": "AAPL",
        },
        "Time Series (Daily)": {
            "2024-02-23": {
                "1. open": "182.31",
                "2. high": "184.62",
                "3. low": "181.94",
                "4. close": "182.52",
                "5. volume": "52164000"
            }
        }
    }
    
    # Set cache
    print(f"Setting cache for key: {cache_key}")
    cache.set_cached_response(
        cache_key=cache_key,
        tool_name="TIME_SERIES_DAILY",
        response_data=test_response
    )
    print("✓ Cache set successfully")
    
    # Get cache
    print(f"Getting cache for key: {cache_key}")
    cached_data = cache.get_cached_response(cache_key)
    
    if cached_data:
        print("✓ Cache retrieved successfully")
        assert cached_data["Meta Data"]["2. Symbol"] == "AAPL", "Cached data mismatch"
        print("✓ Cached data matches original")
    else:
        print("✗ Cache miss (unexpected)")
        return False
    
    # Test 4: Cache miss
    print("\n[TEST 4] Cache Miss")
    print("-" * 60)
    
    nonexistent_key = cache.generate_cache_key("TIME_SERIES_DAILY", {"symbol": "NONEXISTENT"})
    print(f"Trying to get non-existent key: {nonexistent_key}")
    result = cache.get_cached_response(nonexistent_key)
    
    if result is None:
        print("✓ Cache miss handled correctly")
    else:
        print("✗ Unexpected cache hit")
        return False
    
    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        success = test_cache_operations()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
