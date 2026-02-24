/**
 * MessageHistory Component
 * 
 * Displays recent conversation history as clickable chips.
 * Users can click on previous messages to reuse them.
 */

import { Clock } from "lucide-react";

interface MessageHistoryProps {
  messages: string[];
  onSelectMessage: (message: string) => void;
  isLoading?: boolean;
}

export function MessageHistory({ messages, onSelectMessage, isLoading = false }: MessageHistoryProps) {
  if (messages.length === 0) {
    return null;
  }

  return (
    <div className="px-6 py-3 border-b border-tv-border bg-tv-background-secondary">
      <div className="flex items-center gap-2 mb-2">
        <Clock className="h-4 w-4 text-tv-text-secondary" />
        <span className="text-sm text-tv-text-secondary">Recent queries:</span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin">
        {messages.map((message, index) => (
          <button
            key={`${message}-${index}`}
            onClick={() => onSelectMessage(message)}
            disabled={isLoading}
            className="flex-shrink-0 px-3 py-1.5 text-sm bg-tv-background-tertiary border border-tv-border text-tv-text-primary rounded-lg hover:border-tv-accent-blue hover:bg-tv-background-primary transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap max-w-xs truncate"
            title={message}
          >
            {message}
          </button>
        ))}
      </div>
    </div>
  );
}
