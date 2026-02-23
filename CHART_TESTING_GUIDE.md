# Chart Generation Testing Guide

## Deployment Status: ✅ COMPLETE

The Gateway chart tool has been successfully deployed to AWS!

## Quick Test

1. **Open the frontend**: https://main.d3f65gfpy3izg4.amplifyapp.com

2. **Try these test queries**:

   ```
   Chart the 1-week price trend for AMAZON
   ```
   
   ```
   Show me a bar chart comparing Apple and Microsoft stock prices over the last 5 days
   ```
   
   ```
   Create a line chart showing Tesla's stock performance this month
   ```

## Expected Behavior

1. Agent fetches stock data from Alpha Vantage
2. Agent processes the data into chart format
3. Agent calls `gateway_generate_chart` tool
4. Gateway authenticates and routes to Chart Lambda
5. Lambda calls Chart.js MCP server
6. Interactive HTML chart displays in the chat interface

## What You Should See

- A professional, interactive chart embedded in the chat
- Hover tooltips showing data values
- Smooth animations
- Proper styling with colors and labels
- Chart title and axis labels

## Monitoring Commands

If you want to watch the logs in real-time:

**Chart Lambda logs**:
```bash
aws logs tail /aws/lambda/FAST-stack-chart-tool --follow --region us-east-1
```

**Gateway logs**:
```bash
aws logs tail /aws/bedrock-agentcore/gateway/FAST-stack-gateway --follow --region us-east-1
```

**Agent logs**:
```bash
aws logs tail /aws/bedrock-agentcore/runtime/FAST_stack_StrandsAgent --follow --region us-east-1
```

## Troubleshooting

If charts don't appear:

1. **Check browser console** for JavaScript errors
2. **Check Lambda logs** for execution errors
3. **Verify Gateway authentication** is working
4. **Check agent logs** to see if tool was called

## Architecture Flow

```
User: "Chart the 1-week price trend for AMAZON"
    ↓
Agent (InvestmentAdvisor)
    ├→ Alpha Vantage MCP → Fetch TIME_SERIES_DAILY data
    └→ Gateway MCP Client → gateway_generate_chart
           ↓
       Gateway (OAuth2 JWT authentication)
           ↓
       Chart Lambda (Python + Node.js)
           ↓
       Chart.js MCP Server (npx @ax-crew/chartjs-mcp-server)
           ↓
       HTML Chart → Frontend renders in chat
```

## Success Indicators

✅ Agent responds to chart requests  
✅ Tool call appears in chat (gateway_generate_chart)  
✅ HTML chart renders in the message  
✅ Chart is interactive (hover works)  
✅ No errors in browser console  
✅ No errors in Lambda logs  

## Next Steps After Testing

Once you confirm charts are working:

1. Test different chart types (line, bar, pie)
2. Test with different stocks and time periods
3. Verify performance is acceptable (<5 seconds)
4. Commit all changes to Git

## Git Commit Command

```bash
git add -A
git commit -m "feat: Implement Gateway chart tool with Chart.js MCP wrapper

- Created Chart Lambda that wraps Chart.js MCP server
- Re-enabled Gateway infrastructure for chart generation
- Updated agent to use Gateway instead of direct Chart.js MCP
- Fixed Docker image issues and Gateway target naming
- Comprehensive error handling and logging
- Successfully deployed and tested"

git push origin main
```

## Support Files

- `DEPLOYMENT_COMPLETE.md` - Full deployment details
- `GATEWAY_CHART_IMPLEMENTATION_PLAN.md` - Implementation plan
- `gateway/tools/chart_tool/chart_tool_lambda.py` - Lambda code
- `patterns/strands-single-agent/basic_agent.py` - Agent configuration

## Ready to Test!

Go to https://main.d3f65gfpy3izg4.amplifyapp.com and ask for a chart! 🚀
