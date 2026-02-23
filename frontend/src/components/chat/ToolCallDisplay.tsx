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
    // Try to parse as JSON (Code Interpreter returns array of results)
    const parsed = JSON.parse(result)
    
    // Handle array of results from Code Interpreter
    if (Array.isArray(parsed)) {
      const textParts: string[] = []
      
      for (const item of parsed) {
        // Check for structuredContent (Code Interpreter output format)
        if (item.structuredContent) {
          if (item.structuredContent.stdout) {
            const stdout = item.structuredContent.stdout
            // Extract all base64 images from stdout
            const base64Regex = /!\[.*?\]\(data:image\/png;base64,([A-Za-z0-9+/=]+)\)/g
            let match
            let cleanedStdout = stdout
            
            while ((match = base64Regex.exec(stdout)) !== null) {
              images.push(`data:image/png;base64,${match[1]}`)
              // Remove the markdown image from text
              cleanedStdout = cleanedStdout.replace(match[0], '[Chart generated]')
            }
            
            if (cleanedStdout.trim()) {
              textParts.push(cleanedStdout)
            }
          }
          if (item.structuredContent.stderr) {
            textParts.push(item.structuredContent.stderr)
          }
        }
        
        // Check for direct content array
        if (Array.isArray(item.content)) {
          for (const contentItem of item.content) {
            if (contentItem.type === 'image' && contentItem.data) {
              images.push(`data:image/png;base64,${contentItem.data}`)
            } else if (contentItem.type === 'text' && contentItem.text) {
              textParts.push(contentItem.text)
            }
          }
        }
      }
      
      text = textParts.join('\n\n')
    } else {
      // Single object result
      if (parsed.structuredContent) {
        const parts: string[] = []
        if (parsed.structuredContent.stdout) {
          const stdout = parsed.structuredContent.stdout
          const base64Regex = /!\[.*?\]\(data:image\/png;base64,([A-Za-z0-9+/=]+)\)/g
          let match
          let cleanedStdout = stdout
          
          while ((match = base64Regex.exec(stdout)) !== null) {
            images.push(`data:image/png;base64,${match[1]}`)
            cleanedStdout = cleanedStdout.replace(match[0], '[Chart generated]')
          }
          
          if (cleanedStdout.trim()) {
            parts.push(cleanedStdout)
          }
        }
        if (parsed.structuredContent.stderr) {
          parts.push(parsed.structuredContent.stderr)
        }
        text = parts.join('\n\n')
      }
    }
  } catch {
    // Not JSON, check if it's raw text with base64 images
    const base64Regex = /!\[.*?\]\(data:image\/png;base64,([A-Za-z0-9+/=]+)\)/g
    let match
    let cleanedText = result
    
    while ((match = base64Regex.exec(result)) !== null) {
      images.push(`data:image/png;base64,${match[1]}`)
      cleanedText = cleanedText.replace(match[0], '[Chart generated]')
    }
    
    text = cleanedText
  }

  return { images, text }
}

export function ToolCallDisplay({ name, args, status, result }: ToolRenderProps) {
  const [expanded, setExpanded] = useState(false)
  
  // Parse result for Code Interpreter outputs
  const isCodeInterpreter = name === "execute_python_securely" || name.includes("code_interpreter")
  const { images, text } = isCodeInterpreter && result ? parseCodeInterpreterResult(result) : { images: [], text: result || "" }
  
  // Check if this is Chart.js MCP output (HTML chart)
  const isChartJsOutput = name === "chartjs_generateChart" && result && result.includes("<div id=\"chart-container-")
  
  // Auto-expand if there are images or charts
  const shouldAutoExpand = images.length > 0 || isChartJsOutput
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
        {isChartJsOutput && <ImageIcon size={12} className="text-blue-500 ml-1" />}
        {status === "streaming" && <Loader2 size={12} className="animate-spin text-blue-500 ml-auto" />}
        {status === "executing" && <Loader2 size={12} className="animate-spin text-amber-500 ml-auto" />}
        {status === "complete" && <CheckCircle2 size={12} className="text-green-500 ml-auto" />}
      </button>

      {isExpanded && (
        <div className="ml-6 mt-2 border-l-2 border-gray-200 dark:border-gray-700 pl-3 space-y-3">
          {args && (
            <div>
              <div className="text-xs text-gray-400 font-medium mb-1">Input</div>
              <pre className="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-words bg-gray-50 dark:bg-gray-800 p-2 rounded max-h-32 overflow-y-auto">{args}</pre>
            </div>
          )}
          
          {/* Display Chart.js HTML output */}
          {isChartJsOutput && result && (
            <div>
              <div className="text-xs text-gray-400 font-medium mb-2">Interactive Chart</div>
              <div 
                className="bg-white dark:bg-gray-800 p-4 rounded border border-gray-200 dark:border-gray-700"
                dangerouslySetInnerHTML={{ __html: result }}
              />
            </div>
          )}
          
          {/* Display images prominently */}
          {!isChartJsOutput && images.length > 0 && (
            <div>
              <div className="text-xs text-gray-400 font-medium mb-2">Generated Charts</div>
              <div className="space-y-2">
                {images.map((imgSrc, idx) => (
                  <div key={idx} className="bg-white dark:bg-gray-800 p-3 rounded border border-gray-200 dark:border-gray-700">
                    <img 
                      src={imgSrc} 
                      alt={`Chart ${idx + 1}`}
                      className="w-full h-auto max-w-full rounded"
                      style={{ maxHeight: '500px', objectFit: 'contain' }}
                      loading="lazy"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* Display text output only if not Chart.js HTML */}
          {!isChartJsOutput && text && text.trim() && (
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

