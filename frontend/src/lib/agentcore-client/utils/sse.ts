// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ChunkParser, StreamCallback } from "../types";

/**
 * Reads an SSE response stream, passing each line to the parser.
 * 
 * Handles network interruptions, malformed data, and decoder errors gracefully.
 * Provides detailed error messages for debugging and user feedback.
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
  const MAX_CONSECUTIVE_ERRORS = 10;

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
            setTimeout(() => reject(new Error("Stream timeout: No data received for 60 seconds")), 60000)
          )
        ]);
      } catch (readError) {
        // Network or timeout error during read
        if (readError instanceof Error) {
          if (readError.message.includes("timeout")) {
            throw new Error("Connection timeout. The server stopped responding. Please try again.");
          }
          throw new Error(`Network error while reading stream: ${readError.message}`);
        }
        throw new Error("Unknown error while reading stream");
      }

      const { done, value } = chunk;
      if (done) break;

      try {
        // Decode chunk with error recovery
        buffer += decoder.decode(value, { stream: true });
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
        if (line.trim()) {
          try {
            parser(line, callback);
          } catch (parseError) {
            // Log parse errors but continue processing other lines
            console.warn("Failed to parse SSE line:", line, parseError);
          }
        }
      }
    }

    // Process any remaining data in the buffer
    if (buffer.trim()) {
      try {
        parser(buffer, callback);
      } catch (parseError) {
        console.warn("Failed to parse final buffer:", buffer, parseError);
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
