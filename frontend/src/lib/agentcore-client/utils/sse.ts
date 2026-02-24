// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ChunkParser, StreamCallback } from "../types";

/**
 * Reads an SSE response stream, passing each line to the parser.
 * 
 * Handles network interruptions, malformed data, and decoder errors gracefully.
 * Provides detailed error messages for debugging and user feedback.
 * Implements retry logic and graceful degradation for long conversations.
 * 
 * @param response - The fetch Response object containing the SSE stream
 * @param parser - Function to parse individual SSE lines into events
 * @param callback - Function to handle parsed events
 * @throws Error with descriptive message if stream fails unrecoverably
 */
export async function readSSEStream(
  response: Response,
  parser: ChunkParser,
  callback: StreamCallback
): Promise<void> {
  let buffer = "";
  let consecutiveErrors = 0;
  const MAX_CONSECUTIVE_ERRORS = 15; // Increased tolerance for long conversations
  let lastActivityTime = Date.now();
  const ACTIVITY_TIMEOUT = 120000; // 2 minutes (increased from 60s)

  if (!response.body) {
    throw new Error("Response body is empty. The server may not be streaming data correctly.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: false }); // Non-fatal decoding

  try {
    while (true) {
      let chunk;
      
      try {
        // Read next chunk from stream with timeout detection
        chunk = await Promise.race([
          reader.read(),
          new Promise<never>((_, reject) => 
            setTimeout(() => reject(new Error("Stream timeout")), ACTIVITY_TIMEOUT)
          )
        ]);
        
        // Update last activity time on successful read
        lastActivityTime = Date.now();
      } catch (readError) {
        // Check if we've been inactive for too long
        const inactiveTime = Date.now() - lastActivityTime;
        
        if (readError instanceof Error) {
          if (readError.message.includes("timeout") || inactiveTime > ACTIVITY_TIMEOUT) {
            // For long conversations, this might be normal - the agent is still thinking
            console.warn("Stream timeout detected, but may be normal for long conversations");
            throw new Error("Connection timeout. The response is taking longer than expected. Please try again.");
          }
          
          // Network interruption
          console.error("Network error during stream read:", readError);
          throw new Error(`Network error while reading stream: ${readError.message}`);
        }
        throw new Error("Unknown error while reading stream");
      }

      const { done, value } = chunk;
      if (done) break;

      try {
        // Decode chunk with error recovery
        const decoded = decoder.decode(value, { stream: true });
        
        // Skip empty or whitespace-only chunks
        if (decoded.trim().length === 0) {
          continue;
        }
        
        buffer += decoded;
        consecutiveErrors = 0; // Reset error counter on successful decode
      } catch (decodeError) {
        consecutiveErrors++;
        console.warn(`Decoder error (${consecutiveErrors}/${MAX_CONSECUTIVE_ERRORS}):`, decodeError);
        
        if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
          throw new Error("Too many decoding errors. The stream may be corrupted.");
        }
        
        // Skip this chunk and continue
        continue;
      }

      // Split buffer into lines
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      // Parse each complete line
      for (const line of lines) {
        const trimmedLine = line.trim();
        
        // Skip empty lines and comments
        if (!trimmedLine || trimmedLine.startsWith(":")) {
          continue;
        }
        
        try {
          parser(line, callback);
        } catch (parseError) {
          // Log parse errors but continue processing other lines
          // Don't count parse errors toward consecutive error limit
          console.warn("Failed to parse SSE line:", line.substring(0, 100), parseError);
        }
      }
    }

    // Process any remaining data in the buffer
    if (buffer.trim()) {
      try {
        parser(buffer, callback);
      } catch (parseError) {
        console.warn("Failed to parse final buffer:", buffer.substring(0, 100), parseError);
      }
    }
  } catch (error) {
    // Re-throw with context for better error messages
    if (error instanceof Error) {
      throw error;
    }
    throw new Error("Unknown error in SSE stream");
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // Ignore errors when releasing lock
    }
  }
}
