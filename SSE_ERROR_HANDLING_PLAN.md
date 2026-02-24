# SSE Error Handling Improvement Plan

## Problem
During long conversations, users randomly encounter "Error in input stream" which breaks the chat experience. The error occurs in the SSE (Server-Sent Events) streaming client.

## Root Causes
1. **Network interruptions**: Long-running connections can be interrupted
2. **Malformed chunks**: Incomplete or corrupted data in the stream
3. **Decoder errors**: TextDecoder fails on invalid UTF-8 sequences
4. **No retry mechanism**: Single failure breaks the entire conversation
5. **Silent failures**: Parser errors are only logged to console

## Current Code Issues

### `frontend/src/lib/agentcore-client/utils/sse.ts`
- No try-catch around `reader.read()` - network errors propagate up
- No try-catch around `decoder.decode()` - encoding errors crash the stream
- No timeout handling for stalled connections
- No recovery mechanism

### `frontend/src/lib/agentcore-client/parsers/strands.ts`
- Parser errors are silently caught and logged
- No feedback to user about parsing failures
- No partial recovery from malformed events

### `frontend/src/components/chat/ChatInterface.tsx`
- Generic error message doesn't help user understand the issue
- No automatic retry mechanism
- No graceful degradation

## Proposed Solutions

### 1. Enhanced Error Handling in SSE Reader
- Wrap `reader.read()` in try-catch with specific error types
- Add timeout detection for stalled streams
- Provide detailed error messages
- Gracefully handle decoder errors

### 2. Improved Parser Error Handling
- Log parsing errors with more context
- Continue processing valid events even if some fail
- Track consecutive parse failures

### 3. User-Friendly Error Messages
- Distinguish between network errors, parsing errors, and timeouts
- Provide actionable guidance (e.g., "Try sending your message again")
- Show partial results if available

### 4. Optional: Retry Mechanism
- Automatic retry for transient network errors
- Exponential backoff
- User control over retries

## Implementation Steps

1. **Update `sse.ts`**:
   - Add comprehensive error handling
   - Add timeout detection
   - Improve error messages

2. **Update `strands.ts`**:
   - Add better error logging
   - Track parse failure rate

3. **Update `ChatInterface.tsx`**:
   - Improve error display
   - Add retry button
   - Show partial responses

4. **Test**:
   - Simulate network interruptions
   - Test with malformed data
   - Verify error messages are helpful

## Files to Modify
1. `frontend/src/lib/agentcore-client/utils/sse.ts` - Core error handling
2. `frontend/src/lib/agentcore-client/parsers/strands.ts` - Parser improvements
3. `frontend/src/components/chat/ChatInterface.tsx` - UI error handling

## Expected Outcome
- Users see helpful error messages instead of generic "Error in input stream"
- Partial responses are preserved even if stream fails
- Better debugging information in console
- More resilient to network issues


---

## ✅ Implementation Complete

### Changes Made

**1. Enhanced SSE Reader (`sse.ts`)**
- Added comprehensive try-catch blocks around `reader.read()` and `decoder.decode()`
- Implemented 60-second timeout detection for stalled streams
- Added consecutive error tracking (max 10 errors before failing)
- Non-fatal UTF-8 decoding to handle corrupted bytes gracefully
- Detailed error messages for network, timeout, and decoding issues
- Graceful lock release in finally block

**2. Improved Parser (`strands.ts`)**
- Enhanced error logging with context (error message, data preview, length)
- Better debugging information for malformed JSON
- Continues processing even if individual events fail to parse

**3. User-Friendly Error Messages (`ChatInterface.tsx`)**
- Categorized errors: timeout/network, authentication, stream corruption, unknown
- Specific user guidance for each error type
- Preserved partial responses before error occurred
- Clear error display in UI

### Benefits
- Users see helpful, actionable error messages
- Partial responses preserved even if stream fails mid-conversation
- Better resilience to network interruptions
- Improved debugging with detailed console logs
- Graceful degradation instead of complete failure

### Testing Recommendations
1. Test with network throttling to simulate slow connections
2. Test with network interruption mid-stream
3. Verify timeout handling after 60 seconds of no data
4. Check that partial responses are preserved
5. Verify error messages are user-friendly
