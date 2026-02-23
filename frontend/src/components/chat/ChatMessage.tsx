"use client"

import { useState } from "react"
import { ThumbsUp, ThumbsDown, Bot, User } from "lucide-react"
import { Message } from "./types"
import { FeedbackDialog } from "./FeedbackDialog"
import { getToolRenderer } from "@/hooks/useToolRenderer"
import { MarkdownRenderer } from "./MarkdownRenderer"

interface ChatMessageProps {
  message: Message
  sessionId: string
  onFeedbackSubmit: (feedbackType: "positive" | "negative", comment: string) => Promise<void>
}

export function ChatMessage({ message, sessionId: _sessionId, onFeedbackSubmit }: ChatMessageProps) {
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [selectedFeedbackType, setSelectedFeedbackType] = useState<"positive" | "negative">(
    "positive"
  )
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false)

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  }

  const handleFeedbackClick = (type: "positive" | "negative") => {
    setSelectedFeedbackType(type)
    setIsDialogOpen(true)
  }

  const handleFeedbackSubmit = async (comment: string) => {
    await onFeedbackSubmit(selectedFeedbackType, comment)
    setFeedbackSubmitted(true)
  }

  const renderAssistantContent = () => {
    // If segments exist, render them in order (interleaved text + tools)
    if (message.segments && message.segments.length > 0) {
      return message.segments.map((seg, i) => {
        if (seg.type === "text") {
          return <MarkdownRenderer key={i} content={seg.content} />;
        }
        const render = getToolRenderer(seg.toolCall.name);
        if (!render) return null;
        return (
          <div key={seg.toolCall.toolUseId} className="my-1">
            {render({ name: seg.toolCall.name, args: seg.toolCall.input, status: seg.toolCall.status, result: seg.toolCall.result })}
          </div>
        );
      });
    }
    // Fallback: just render content as markdown
    return <MarkdownRenderer content={message.content} />;
  };

  return (
    <div className={`flex gap-3 mb-6 animate-fade-in ${message.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div className={`avatar ${message.role === "user" ? "avatar-user" : "avatar-assistant"} shadow-md`}>
        {message.role === "user" ? <User size={18} /> : <Bot size={18} />}
      </div>

      {/* Message content */}
      <div className={`flex flex-col ${message.role === "user" ? "items-end" : "items-start"} max-w-[75%]`}>
        <div
          className={`message-bubble break-words ${
            message.role === "user"
              ? "px-5 py-3 rounded-2xl gradient-bg-user text-white shadow-lg rounded-tr-sm"
              : "px-5 py-4 rounded-2xl bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 shadow-md border border-gray-100 dark:border-gray-700 rounded-tl-sm"
          }`}
        >
          {message.role === "assistant" ? (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              {renderAssistantContent()}
            </div>
          ) : (
            <div className="whitespace-pre-wrap">{message.content}</div>
          )}
        </div>

        {/* Timestamp and Feedback buttons */}
        <div className="flex items-center gap-3 mt-2 px-2">
          <div className="text-xs text-gray-500 dark:text-gray-400">{formatTime(message.timestamp)}</div>

          {/* Show feedback buttons only for assistant messages with content */}
          {message.role === "assistant" && message.content && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => handleFeedbackClick("positive")}
                disabled={feedbackSubmitted}
                className="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed hover:scale-110"
                aria-label="Positive feedback"
                title="Good response"
              >
                <ThumbsUp size={15} />
              </button>
              <button
                onClick={() => handleFeedbackClick("negative")}
                disabled={feedbackSubmitted}
                className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed hover:scale-110"
                aria-label="Negative feedback"
                title="Bad response"
              >
                <ThumbsDown size={15} />
              </button>
              {feedbackSubmitted && (
                <span className="text-xs text-gray-500 dark:text-gray-400 ml-2 animate-fade-in">
                  Thanks for your feedback!
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Feedback Dialog */}
      <FeedbackDialog
        isOpen={isDialogOpen}
        onClose={() => setIsDialogOpen(false)}
        onSubmit={handleFeedbackSubmit}
        feedbackType={selectedFeedbackType}
      />
    </div>
  )
}
