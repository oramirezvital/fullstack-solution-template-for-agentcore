// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentCoreConfig, AgentPattern, ChunkParser, StreamCallback } from "./types";
import { parseStrandsChunk } from "./parsers/strands";
import { parseLanggraphChunk } from "./parsers/langgraph";
import { readSSEStream } from "./utils/sse";

const PARSERS: Record<AgentPattern, ChunkParser> = {
  "strands-single-agent": parseStrandsChunk,
  "langgraph-single-agent": parseLanggraphChunk,
};

export class AgentCoreClient {
  private runtimeArn: string;
  private region: string;
  private parser: ChunkParser;
  private maxRetries: number = 2; // Maximum number of retry attempts
  private baseDelay: number = 1000; // Base delay in ms (1 second)

  constructor(config: AgentCoreConfig) {
    this.runtimeArn = config.runtimeArn;
    this.region = config.region ?? "us-east-1";
    this.parser = PARSERS[config.pattern];
  }

  generateSessionId(): string {
    return crypto.randomUUID();
  }

  /**
   * Determines if an error is retryable based on its characteristics.
   * 
   * @param error - The error to check
   * @returns true if the error should trigger a retry
   */
  private isRetryableError(error: Error): boolean {
    const message = error.message.toLowerCase();
    
    // Retry on network errors, timeouts, and stream interruptions
    return (
      message.includes("network error") ||
      message.includes("timeout") ||
      message.includes("error in input stream") ||
      message.includes("stream") ||
      message.includes("connection") ||
      message.includes("fetch")
    );
  }

  /**
   * Calculates exponential backoff delay with jitter.
   * 
   * @param attempt - Current retry attempt number (0-indexed)
   * @returns Delay in milliseconds
   */
  private calculateBackoff(attempt: number): number {
    // Exponential backoff: baseDelay * 2^attempt + random jitter
    const exponentialDelay = this.baseDelay * Math.pow(2, attempt);
    const jitter = Math.random() * 1000; // 0-1000ms random jitter
    return Math.min(exponentialDelay + jitter, 10000); // Cap at 10 seconds
  }

  /**
   * Sleeps for the specified duration.
   * 
   * @param ms - Duration in milliseconds
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async invoke(
    query: string,
    sessionId: string,
    accessToken: string,
    onEvent: StreamCallback
  ): Promise<void> {
    if (!accessToken) throw new Error("No valid access token found.");
    if (!this.runtimeArn) throw new Error("Agent Runtime ARN not configured.");

    let lastError: Error | null = null;

    // Attempt the request with retries
    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        await this.invokeOnce(query, sessionId, accessToken, onEvent);
        return; // Success - exit retry loop
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        
        // Check if we should retry
        const isLastAttempt = attempt === this.maxRetries;
        const shouldRetry = this.isRetryableError(lastError);

        if (isLastAttempt || !shouldRetry) {
          // Don't retry - throw the error
          throw lastError;
        }

        // Calculate backoff delay
        const delay = this.calculateBackoff(attempt);
        
        console.warn(
          `Request failed (attempt ${attempt + 1}/${this.maxRetries + 1}): ${lastError.message}. ` +
          `Retrying in ${Math.round(delay / 1000)}s...`
        );

        // Wait before retrying
        await this.sleep(delay);
      }
    }

    // This should never be reached, but TypeScript needs it
    throw lastError || new Error("Unknown error during retry");
  }

  /**
   * Performs a single invocation attempt without retry logic.
   * 
   * @param query - User's query
   * @param sessionId - Session identifier
   * @param accessToken - JWT access token
   * @param onEvent - Callback for streaming events
   */
  private async invokeOnce(
    query: string,
    sessionId: string,
    accessToken: string,
    onEvent: StreamCallback
  ): Promise<void> {
    const endpoint = `https://bedrock-agentcore.${this.region}.amazonaws.com`;
    const escapedArn = encodeURIComponent(this.runtimeArn);
    const url = `${endpoint}/runtimes/${escapedArn}/invocations?qualifier=DEFAULT`;

    const traceId = `1-${Math.floor(Date.now() / 1000).toString(16)}-${crypto.randomUUID()}`;

    // User identity is extracted server-side from the validated JWT token
    // (Authorization header), not sent in the payload body. This prevents
    // impersonation via prompt injection.
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "X-Amzn-Trace-Id": traceId,
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": sessionId,
      },
      body: JSON.stringify({
        prompt: query,
        runtimeSessionId: sessionId,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    await readSSEStream(response, this.parser, onEvent);
  }
}
