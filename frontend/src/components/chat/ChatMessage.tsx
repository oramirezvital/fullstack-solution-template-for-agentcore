"use client"

import { useState } from "react"
import { ThumbsUp, ThumbsDown, User, Download } from "lucide-react"
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

  const downloadExcelFile = (base64Data: string, filename: string) => {
    try {
      // Convert base64 to blob
      const byteCharacters = atob(base64Data);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { 
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
      });
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      
      // Cleanup
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error downloading Excel file:', error);
    }
  };

  const renderAssistantContent = () => {
    // If segments exist, render them in order (interleaved text + tools)
    if (message.segments && message.segments.length > 0) {
      return message.segments.map((seg, i) => {
        if (seg.type === "text") {
          return <MarkdownRenderer key={i} content={seg.content} />;
        }
        
        // Check for Excel export tool
        if (seg.toolCall.name === "export_portfolio_to_excel" && seg.toolCall.result) {
          try {
            const result = JSON.parse(seg.toolCall.result);
            if (result.success && result.data) {
              return (
                <div key={seg.toolCall.toolUseId} className="my-3">
                  <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                    <div className="flex items-start gap-3">
                      <Download className="text-green-600 dark:text-green-400 mt-1" size={20} />
                      <div className="flex-1">
                        <h4 className="font-semibold text-green-800 dark:text-green-300 mb-1">
                          Portfolio Export Ready
                        </h4>
                        <p className="text-sm text-green-700 dark:text-green-400 mb-3">
                          Your portfolio has been exported to Excel with {result.sheets?.length || 4} sheets
                        </p>
                        <button
                          onClick={() => downloadExcelFile(result.data, result.filename)}
                          className="inline-flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors text-sm font-medium"
                        >
                          <Download size={16} />
                          Download {result.filename}
                        </button>
                        <div className="mt-2 text-xs text-green-600 dark:text-green-400">
                          Size: {result.size_kb?.toFixed(1)} KB • {result.total_positions} positions
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            }
          } catch (error) {
            console.error('Error parsing Excel export result:', error);
          }
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
        {message.role === "user" ? (
          <User size={24} />
        ) : (
          <img 
            src="/munger.jpg" 
            alt="Charlie Munger" 
            className="w-full h-full object-cover rounded-full"
          />
        )}
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
