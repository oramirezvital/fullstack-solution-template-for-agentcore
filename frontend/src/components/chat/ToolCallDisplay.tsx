"use client"

import { useState } from "react"
import { Wrench, Loader2, CheckCircle2, ChevronRight, ChevronDown, Image as ImageIcon } from "lucide-react"
import type { ToolRenderProps } from "@/hooks/useToolRenderer"

/**
 * Parse Code Interpreter result to extract images and text
 */
function parseCodeInterpreterResult(result: string): { images: string[]; text: string } {
  const images: string[] = []
  let text = result

  try {
    // Try to parse as JSON (Code Interpreter structured output)
    const parsed = JSON.parse(result)
    
    // Extract stdout/stderr text
    if (parsed.structuredContent) {
      const parts: string[] = []
      if (parsed.structuredContent.stdout) {
        parts.push(parsed.structuredContent.stdout)
      }
      if (parsed.structuredContent.stderr) {
        parts.push(parsed.structuredContent.stderr)
      }
      text = parts.join('\n\n')
    }
    
    // Extract images from content array
    if (Array.isArray(parsed.content)) {
      for (const item of parsed.content) {
        if (item.type === 'image' && item.data) {
          // Base64 image data
          images.push(`data:image/png;base64,${item.data}`)
        }
      }
    }
  } catch {
    // Not JSON, treat as plain text
    text = result
  }

  return { images, text }
}

export function ToolCallDisplay({ name, args, status, result }: ToolRenderProps) {
  const [expanded, setExpanded] = useState(false)
  
  // Parse result for Code Interpreter outputs
  const isCodeInterpreter = name === "execute_python_securely" || name.includes("code_interpreter")
  const { images, text } = isCodeInterpreter && result ? parseCodeInterpreterResult(result) : { images: [], text: result || "" }
  
  // Auto-expand if there are images
  const shouldAutoExpand = images.length > 0
  const [hasAutoExpanded] = useState(shouldAutoExpand)
  const isExpanded = expanded || (shouldAutoExpand && !hasAutoExpanded)

  return (
    <div className="my-2 text-sm">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-gray-200/50 dark:hover:bg-gray-700/50 transition-colors w-full text-left"
      >
        {isExpanded ? <ChevronDown size={12} className="text-gray-400" /> : <ChevronRight size={12} className="text-gray-400" />}
        <Wrench size={12} className="text-gray-400" />
        <span className="text-gray-600 dark:text-gray-300">{name}</span>
        {images.length > 0 && <ImageIcon size={12} className="text-blue-500 ml-1" />}
        {status === "streaming" && <Loader2 size={12} className="animate-spin text-blue-500 ml-auto" />}
        {status === "executing" && <Loader2 size={12} className="animate-spin text-amber-500 ml-auto" />}
        {status === "complete" && <CheckCircle2 size={12} className="text-green-500 ml-auto" />}
      </button>

      {isExpanded && (
        <div className="ml-6 mt-2 border-l-2 border-gray-200 dark:border-gray-700 pl-3 space-y-3">
          {args && (
            <div>
              <div className="text-xs text-gray-400 font-medium mb-1">Input</div>
              <pre className="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-words bg-gray-50 dark:bg-gray-800 p-2 rounded">{args}</pre>
            </div>
          )}
          
          {/* Display images prominently */}
          {images.length > 0 && (
            <div>
              <div className="text-xs text-gray-400 font-medium mb-2">Generated Charts</div>
              <div className="space-y-2">
                {images.map((imgSrc, idx) => (
                  <div key={idx} className="bg-white dark:bg-gray-800 p-2 rounded border border-gray-200 dark:border-gray-700">
                    <img 
                      src={imgSrc} 
                      alt={`Chart ${idx + 1}`}
                      className="w-full h-auto rounded"
                      loading="lazy"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* Display text output */}
          {text && text.trim() && (
            <div>
              <div className="text-xs text-gray-400 font-medium mb-1">Output</div>
              <pre className="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-words bg-gray-50 dark:bg-gray-800 p-2 rounded max-h-64 overflow-y-auto">{text}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

