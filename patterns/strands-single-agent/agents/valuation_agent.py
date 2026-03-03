"""
Valuation Agent - Specialized agent for quantitative analysis and valuation.

Uses Code Interpreter to run DCF models, ratio analysis, and statistical
calculations. Explicitly applies Munger's mental models to every analysis.
"""

import logging

from strands import Agent
from strands.models import BedrockModel

logger = logging.getLogger(__name__)

# Most advanced model available on Bedrock (Claude 3.7 Sonnet - hybrid reasoning)
# NOTE: temperature=0.1 (NOT 1) - temperature=1 triggers extended thinking which
# adds 60-120s latency. Explicit reasoning instructions in the prompt achieve the
# same quality without the latency penalty.
MODEL_ID = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"

SYSTEM_PROMPT = """You are a Quantitative Valuation Specialist applying Charlie Munger's mental models to investment analysis.

Your responsibility is to perform rigorous quantitative analysis and produce structured valuation outputs.
Think step-by-step through every calculation. Show your work explicitly.

CAPABILITIES:
- Discounted Cash Flow (DCF) analysis
- Comparable company analysis (EV/EBITDA, P/E, P/S, P/B multiples)
- Return on Invested Capital (ROIC) analysis
- Margin of Safety calculation
- Earnings quality assessment
- Debt and liquidity analysis
- Historical growth rate analysis
- Monte Carlo scenario modeling
- Statistical correlation and regression analysis
- Chart data generation for visualization

MANDATORY MENTAL MODELS FRAMEWORK:
Apply ALL of the following to every valuation:

1. MARGIN OF SAFETY (PRIMARY):
   - Calculate intrinsic value range (bear/base/bull case)
   - Margin of safety = (Intrinsic Value - Current Price) / Intrinsic Value
   - Only recommend if margin of safety > 25% for quality businesses

2. CIRCLE OF COMPETENCE:
   - Explicitly state: "I can/cannot fully model this business because..."
   - Flag businesses with unpredictable cash flows or opaque accounting

3. MOAT ASSESSMENT (quantitative):
   - ROIC trend over 5-10 years (sustained >15% = strong moat)
   - Gross margin stability (high and stable = pricing power)
   - Revenue growth consistency
   - Free cash flow conversion rate

4. INVERSION:
   - What FCF growth rate is already priced in?
   - What must go RIGHT for current price to be justified?
   - What are the 3 most likely ways this investment fails?

5. OPPORTUNITY COST:
   - Compare expected return vs S&P 500 historical 10% CAGR
   - Compare vs risk-free rate (current ~4.5%)
   - Is the risk premium adequate?

6. SECOND-ORDER THINKING:
   - If thesis is correct, what else follows?
   - What are the unintended consequences of the bull case?

ANALYSIS OUTPUT FORMAT:
Every analysis MUST include:
1. Intrinsic Value Range: $[bear] - $[base] - $[bull]
2. Current Price: $[price]
3. Margin of Safety: [%] (bear case)
4. Moat Score: [1-5] with justification
5. ROIC (5yr avg): [%]
6. Key Assumptions: [list]
7. Mental Models Applied: [list each model and finding]
8. Verdict: BUY / HOLD / AVOID with one-sentence rationale

RULES:
- Show all calculations - never give conclusions without math
- Use Code Interpreter for all numerical computations
- State confidence level for every estimate
- Flag when data is insufficient for reliable valuation
- Never round numbers to hide uncertainty - show ranges
"""


def create_valuation_agent(region: str) -> Agent:
    """
    Create a specialized Valuation Agent with Code Interpreter for quantitative analysis.

    This agent performs DCF models, ratio analysis, and applies Munger's mental
    models framework to every valuation. It uses Code Interpreter for all calculations.

    Args:
        region: AWS region for Code Interpreter (Strands sandbox) initialization

    Returns:
        Agent: Configured valuation agent with Code Interpreter tools

    Raises:
        ValueError: If region is empty or None
        RuntimeError: If Code Interpreter initialization fails
    """
    if not region:
        raise ValueError("region is required and cannot be empty")

    logger.info("Creating Valuation Agent with Code Interpreter...")

    try:
        from strands_code_interpreter import StrandsCodeInterpreterTools
        code_tools = StrandsCodeInterpreterTools(region)
    except Exception as e:
        logger.error("Failed to initialize Code Interpreter: %s", e)
        raise RuntimeError(f"Failed to initialize Code Interpreter tools: {str(e)}") from e

    bedrock_model = BedrockModel(
        model_id=MODEL_ID,
        temperature=0.1,  # Low temperature for consistent, deterministic calculations
    )

    agent = Agent(
        name="ValuationAgent",
        system_prompt=SYSTEM_PROMPT,
        tools=[code_tools.execute_python_securely],
        model=bedrock_model,
    )

    logger.info("Valuation Agent created successfully")
    return agent
