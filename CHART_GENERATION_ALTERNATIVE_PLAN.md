# Chart Generation Alternative Plan

## Current Problem
The LLM keeps passing `chartConfig` as a JSON string instead of an object to the Chart.js MCP server:
- Input: `{"chartConfig": "{\n  \"type\": \"line\", ..."}` ❌ (string)
- Expected: `{"chartConfig": {"type": "line", ...}}` ✅ (object)

This causes the Chart.js MCP server to fail or produce invalid output.

## Root Cause
Despite clear instructions in the system prompt, the LLM serializes the configuration object to a string when calling the MCP tool. This is a fundamental limitation of how the LLM interprets tool calling with complex nested objects.

## Solution Options

### Option 1: Use Code Interpreter with Matplotlib (RECOMMENDED)
**Pros:**
- Already working and integrated
- Generates base64 PNG images that display reliably
- No dependency on external MCP servers
- LLM is familiar with matplotlib syntax
- Frontend already handles base64 images perfectly

**Cons:**
- Static images, not interactive
- Slightly larger file sizes

**Implementation:**
- Update system prompt to use Code Interpreter for chart generation
- Remove Chart.js MCP instructions
- Keep Chart.js MCP client code for future use

### Option 2: Create Custom MCP Wrapper
**Pros:**
- Keeps interactive Chart.js charts
- Handles JSON string-to-object conversion server-side

**Cons:**
- Requires building and maintaining custom MCP server
- More complex deployment
- Additional infrastructure

### Option 3: Simplify Chart.js Configuration
**Pros:**
- Might reduce serialization issues
- Keeps interactive charts

**Cons:**
- May not solve the fundamental problem
- Limited chart customization

## Recommended Approach

**Switch to Code Interpreter with Matplotlib** for the following reasons:

1. **Reliability**: Code Interpreter already works perfectly
2. **Simplicity**: No external dependencies or MCP server issues
3. **Quality**: Matplotlib produces professional, publication-quality charts
4. **Flexibility**: Full control over chart styling and customization
5. **Performance**: Base64 images load quickly and display reliably

## Implementation Steps

1. Update agent system prompt to use Code Interpreter for charts
2. Provide matplotlib examples for common chart types
3. Keep Chart.js MCP code commented out for future experimentation
4. Test with various chart requests

## Example Matplotlib Code

```python
import matplotlib.pyplot as plt
import io
import base64

# Create chart
fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(dates, prices, marker='o', linewidth=2, color='#3fb950')
ax.set_title('Amazon (AMZN) - 1 Week Price Trend', fontsize=16, fontweight='bold')
ax.set_xlabel('Date', fontsize=12)
ax.set_ylabel('Price (USD)', fontsize=12)
ax.grid(True, alpha=0.3)

# Convert to base64
buf = io.BytesIO()
plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
buf.seek(0)
img_base64 = base64.b64encode(buf.read()).decode()
plt.close()

# Display
print(f"![Chart](data:image/png;base64,{img_base64})")
```

## Decision

Proceed with Option 1 (Code Interpreter with Matplotlib) as it provides the most reliable and maintainable solution.
