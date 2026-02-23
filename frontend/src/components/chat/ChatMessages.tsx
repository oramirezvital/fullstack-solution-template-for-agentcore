import { RefObject } from "react"
import { Message } from "./types"
import { ChatMessage } from "./ChatMessage"

interface ChatMessagesProps {
  messages: Message[]
  messagesEndRef: RefObject<HTMLDivElement | null>
  sessionId: string
  onFeedbackSubmit: (
    messageContent: string,
    feedbackType: "positive" | "negative",
    comment: string
  ) => Promise<void>
}

export function ChatMessages({
  messages,
  messagesEndRef,
  sessionId,
  onFeedbackSubmit,
}: ChatMessagesProps) {
  return (
    <div
      className={`h-full px-6 py-8 space-y-2 w-full ${
        messages.length > 0 ? "overflow-y-auto" : "overflow-hidden"
      } scroll-smooth`}
    >
      {messages.length === 0 ? (
        <div className="flex items-center justify-center h-full text-gray-400 dark:text-gray-500">
          Start a new conversation
        </div>
      ) : (
        messages.map((message, index) => (
          <ChatMessage
            key={index}
            message={message}
            sessionId={sessionId}
            onFeedbackSubmit={async (feedbackType, comment) => {
              await onFeedbackSubmit(message.content, feedbackType, comment)
            }}
          />
        ))
      )}
      <div ref={messagesEndRef} />
    </div>
  )
}
