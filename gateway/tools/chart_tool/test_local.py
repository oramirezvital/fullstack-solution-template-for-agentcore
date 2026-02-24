#!/usr/bin/env python3
"""
Local test script for Chart Tool Lambda

This script tests the chart generation functionality locally by:
1. Simulating a Lambda event
2. Calling the lambda_handler function
3. Verifying the output

Run this after building the Docker image to verify it works before deploying.
"""

import json
import sys

from chart_tool_lambda import lambda_handler


class MockContext:
    """Mock Lambda context for local testing"""

    class ClientContext:
        def __init__(self):
            self.custom = {
                "bedrockAgentCoreToolName": "chart-tool-target___generate_chart"
            }

    def __init__(self):
        self.client_context = self.ClientContext()
        self.function_name = "test-chart-tool"
        self.memory_limit_in_mb = 512
        self.invoked_function_arn = (
            "arn:aws:lambda:us-east-1:123456789012:function:test-chart-tool"
        )
        self.aws_request_id = "test-request-id"


def test_chart_generation():
    """Test chart generation with sample data"""

    # Sample event matching the format from the logs
    event = {
        "chartType": "line",
        "data": {
            "labels": ["02/11", "02/12", "02/13", "02/17", "02/18", "02/19", "02/20"],
            "datasets": [
                {
                    "label": "AMZN Closing Price (USD)",
                    "data": [204.08, 199.6, 198.79, 201.15, 204.79, 204.86, 210.11],
                    "borderColor": "#3fb950",
                    "backgroundColor": "rgba(63, 185, 80, 0.1)",
                    "fill": True,
                    "tension": 0.3,
                    "pointRadius": 5,
                    "pointHoverRadius": 7,
                }
            ],
        },
        "title": "Amazon (AMZN) - 1 Week Price Trend (Feb 11-20, 2026)",
    }

    print("Testing chart generation with sample data...")
    print(f"Event: {json.dumps(event, indent=2)}")
    print("\nCalling lambda_handler...")

    try:
        # Call the Lambda handler
        context = MockContext()
        result = lambda_handler(event, context)

        # Check result
        if "content" in result and len(result["content"]) > 0:
            html = result["content"][0]["text"]

            # Verify HTML contains expected elements
            if "<canvas" in html and "chart.js" in html.lower():
                print("\n✅ SUCCESS! Chart generated successfully")
                print(f"HTML length: {len(html)} characters")
                print("\nFirst 500 characters of HTML:")
                print(html[:500])
                return True
            else:
                print("\n❌ FAILED! HTML doesn't contain expected Chart.js elements")
                print(f"Result: {result}")
                return False
        else:
            print("\n❌ FAILED! No content in result")
            print(f"Result: {result}")
            return False

    except Exception as e:
        print(f"\n❌ FAILED! Exception occurred: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_chart_generation()
    sys.exit(0 if success else 1)
