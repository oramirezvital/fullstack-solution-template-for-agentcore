#!/usr/bin/env python3

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Test Stock Tool via AgentCore Gateway.

Usage:
    python test-scripts/test-stock-tool.py [SYMBOL]

Example:
    python test-scripts/test-stock-tool.py AAPL
    python test-scripts/test-stock-tool.py GOOGL
"""

import json
import os
import sys
from pathlib import Path

import boto3
import requests

# Add scripts directory to path for reliable imports
scripts_dir = Path(__file__).parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from utils import get_ssm_params, get_stack_config, print_msg, print_section


def get_secret(secret_name: str) -> str:
    """
    Fetch secret from AWS Secrets Manager.

    Args:
        secret_name: The name or ARN of the secret to retrieve

    Returns:
        The secret value as a string

    Raises:
        ValueError: If the secret is not found or cannot be accessed
        RuntimeError: If there's an AWS service error
    """
    region = os.environ.get(
        "AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )
    secrets_client = boto3.client("secretsmanager", region_name=region)

    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        return response["SecretString"]
    except Exception as e:
        raise RuntimeError(f"Error retrieving secret {secret_name}: {str(e)}")


def fetch_access_token(client_id: str, client_secret: str, token_url: str) -> str:
    """
    Fetch access token using client credentials flow.

    Args:
        client_id: Cognito client ID
        client_secret: Cognito client secret
        token_url: OAuth2 token endpoint URL

    Returns:
        Access token string
    """
    response = requests.post(
        token_url,
        data=f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    if response.status_code != 200:
        print_msg(
            f"Token request failed: {response.status_code} - {response.text}", "error"
        )
        sys.exit(1)

    return response.json()["access_token"]


def list_tools(gateway_url: str, access_token: str) -> dict:
    """
    List available tools via gateway.

    Args:
        gateway_url: Gateway endpoint URL
        access_token: OAuth2 access token

    Returns:
        Dictionary containing available tools
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    payload = {"jsonrpc": "2.0", "id": "list-tools-request", "method": "tools/list"}

    response = requests.post(gateway_url, headers=headers, json=payload, timeout=30)

    if response.status_code != 200:
        print_msg(
            f"Gateway request failed: {response.status_code} - {response.text}", "error"
        )
        sys.exit(1)

    return response.json()


def call_tool(
    gateway_url: str, access_token: str, tool_name: str, arguments: dict
) -> dict:
    """
    Call a specific tool via gateway.

    Args:
        gateway_url: Gateway endpoint URL
        access_token: OAuth2 access token
        tool_name: Name of the tool to call (with target prefix)
        arguments: Dictionary of tool arguments

    Returns:
        Dictionary containing tool response
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    payload = {
        "jsonrpc": "2.0",
        "id": "call-tool-request",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    response = requests.post(gateway_url, headers=headers, json=payload, timeout=90)

    if response.status_code != 200:
        print_msg(
            f"Gateway request failed: {response.status_code} - {response.text}", "error"
        )
        sys.exit(1)

    return response.json()


def main():
    """Main entry point for stock tool testing."""
    print_section("Stock Tool Test via AgentCore Gateway")

    # Get stock symbol from command line or use default
    stock_symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(f"Testing with stock symbol: {stock_symbol}\n")

    # Get stack configuration
    stack_cfg = get_stack_config()
    print(f"Stack: {stack_cfg['stack_name']}\n")

    # Fetch SSM parameters
    print("Fetching configuration...")
    gateway_params = get_ssm_params(
        stack_cfg["stack_name"], "gateway_url", "machine_client_id", "cognito_provider"
    )

    # Get client secret from Secrets Manager
    client_secret = get_secret(f"/{stack_cfg['stack_name']}/machine_client_secret")

    print_msg("Configuration fetched")

    # Extract gateway configuration
    gateway_url = gateway_params["gateway_url"]
    client_id = gateway_params["machine_client_id"]
    cognito_domain = gateway_params["cognito_provider"]
    token_url = f"https://{cognito_domain}/oauth2/token"

    print(f"Gateway URL: {gateway_url}")
    print(f"Token URL: {token_url}")

    # Get access token
    print_section("Authentication")
    print("Fetching access token...")

    access_token = fetch_access_token(client_id, client_secret, token_url)
    print_msg("Access token obtained")

    # List available tools
    print_section("Available Tools")
    print("Calling tools/list...")

    tools = list_tools(gateway_url, access_token)
    print_msg("Gateway call successful")

    tool_list = tools.get("result", {}).get("tools", [])
    if not tool_list:
        print_msg("No tools found in gateway", "error")
        sys.exit(1)

    print("\nAvailable tools:")
    for tool in tool_list:
        print(f"  - {tool['name']}: {tool.get('description', 'No description')}")

    # Find the stock tool by base name (after the ___ target prefix)
    target_tool = "get_stock_info"
    tool_name = None
    for t in tool_list:
        if t["name"].endswith(f"___{target_tool}"):
            tool_name = t["name"]
            break

    if not tool_name:
        print_msg(
            f"Tool '{target_tool}' not found. Available: {[t['name'] for t in tool_list]}",
            "error",
        )
        sys.exit(1)

    # Call the stock tool
    print_section("Stock Tool Test")
    print(f"Calling tool: {tool_name}")
    print(f"Arguments: symbol={stock_symbol}\n")

    tool_result = call_tool(
        gateway_url,
        access_token,
        tool_name,
        {"symbol": stock_symbol},
    )

    # Validate response
    if "error" in tool_result:
        print_msg(f"Tool returned error: {tool_result['error']}", "error")
        sys.exit(1)

    if "result" not in tool_result or "content" not in tool_result["result"]:
        print_msg(f"Unexpected response format: {json.dumps(tool_result)}", "error")
        sys.exit(1)

    print_msg("Tool call successful")
    print("\n" + "=" * 60)
    print("STOCK INFORMATION")
    print("=" * 60 + "\n")

    # Extract and display the stock information
    content = tool_result["result"]["content"]
    if content and len(content) > 0:
        stock_info = content[0].get("text", "No data")
        print(stock_info)
    else:
        print("No stock information returned")

    print("\n" + "=" * 60)
    print("\nRaw Response:")
    print(json.dumps(tool_result, indent=2))


if __name__ == "__main__":
    main()
