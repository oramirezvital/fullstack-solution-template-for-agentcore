"use client"

import { FormEvent, KeyboardEvent, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Loader2Icon, Send } from "lucide-react"

interface ChatInputProps {
  input: string
  setInput: (input: string) => void
  handleSubmit: (e: FormEvent) => void
  isLoading: boolean
  className?: string
}

export function ChatInput({
  input,
  setInput,
  handleSubmit,
  isLoading,
  className = "",
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize the textarea based on content
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = "0px"
      const scrollHeight = textarea.scrollHeight
      textarea.style.height = scrollHeight + "px"
    }
  }, [input])

  // Handle key presses for Ctrl+Enter to add new line and Enter to submit
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter") {
      if (e.ctrlKey) {
        // Add a new line when Ctrl+Enter is pressed
        setInput(`${input}\n\n`)
        e.preventDefault()
      } else if (!e.shiftKey) {
        // Submit the form when Enter is pressed without Shift
        if (input.trim()) {
          e.preventDefault()
          handleSubmit(e as unknown as FormEvent)
        }
      }
    }
  }

  return (
    <div className={`p-4 w-full ${className}`}>
      <form
        onSubmit={handleSubmit}
        className="flex space-x-3 w-full items-end bg-tv-background-tertiary rounded-xl shadow-xl p-4 border-2 border-tv-border focus-within:border-tv-accent-blue transition-all duration-200"
      >
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about stocks, market trends, or portfolio analysis..."
          disabled={isLoading}
          className="flex-1 min-h-[40px] max-h-[200px] resize-none py-2 bg-transparent border-none focus-visible:ring-0 focus-visible:ring-offset-0 text-tv-text-primary placeholder:text-tv-text-secondary"
          rows={1}
          autoFocus
        />

        <Button 
          type="submit" 
          disabled={!input.trim() || isLoading} 
          className="h-11 px-6 rounded-lg bg-tv-accent-blue hover:bg-blue-600 text-white transition-all duration-200 shadow-md hover:shadow-lg"
        >
          {isLoading ? (
            <>
              <Loader2Icon className="mr-2 h-4 w-4 animate-spin" />
              Thinking...
            </>
          ) : (
            <>
              <Send className="h-4 w-4 mr-2" />
              Send
            </>
          )}
        </Button>
      </form>
    </div>
  )
}
