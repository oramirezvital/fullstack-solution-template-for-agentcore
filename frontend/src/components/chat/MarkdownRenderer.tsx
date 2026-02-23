"use client"

import { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism"
import { Copy, Check } from "lucide-react"

import { ChartRenderer } from "./ChartRenderer"

function completePartialMarkdown(text: string): string {
  const fenceCount = (text.match(/^```/gm) || []).length
  if (fenceCount % 2 !== 0) return text + "\n```"
  return text
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={handleCopy} className="p-1 text-gray-400 hover:text-gray-600 transition-colors" aria-label="Copy code">
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  )
}

// react-markdown v10 + React 19 has overly strict component types for element-specific refs.
// Using Record<string, ...> to avoid the type mismatch on pre, p, th, td, etc.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const components: Record<string, any> = {
  code({ className, children }: { className?: string; children?: React.ReactNode }) {
    const match = /language-(\w+)/.exec(className || "")
    const codeString = String(children).replace(/\n$/, "")
    
    if (match) {
      const language = match[1]
      
      // Detect and render chart JSON
      if (language === 'json') {
        try {
          const jsonData = JSON.parse(codeString)
          // Check if it's a chart specification
          if (jsonData.type === 'chart' && jsonData.chartType && jsonData.data) {
            return <ChartRenderer chartSpec={jsonData} />
          }
        } catch (e) {
          // Not valid JSON or not a chart, fall through to regular rendering
        }
      }
      
      // Render HTML code blocks as actual HTML for interactive charts (legacy support)
      // This handles both ```html blocks and plain HTML that looks like Chart.js output
      if (language === 'html' || (codeString.includes('<div id="chart-container-') && codeString.includes('</script>'))) {
        return (
          <div className="my-3">
            <div className="flex items-center justify-between px-3 py-1 bg-gray-100 border border-gray-300 rounded-t-md">
              <span className="text-xs text-gray-500">Interactive Chart</span>
              <CopyButton text={codeString} />
            </div>
            <div 
              className="border border-t-0 border-gray-300 rounded-b-md p-4 bg-white"
              dangerouslySetInnerHTML={{ __html: codeString }}
            />
          </div>
        )
      }
      
      // Regular syntax highlighting for other languages
      return (
        <div className="my-2 rounded-md overflow-hidden border border-gray-300 bg-white">
          <div className="flex items-center justify-between px-3 py-1 bg-gray-100 border-b border-gray-300">
            <span className="text-xs text-gray-500">{language}</span>
            <CopyButton text={codeString} />
          </div>
          <SyntaxHighlighter
            style={oneLight}
            language={language}
            PreTag="div"
            customStyle={{ margin: 0, padding: "0.75rem", fontSize: "0.8rem", background: "white" }}
          >
            {codeString}
          </SyntaxHighlighter>
        </div>
      )
    }
    
    // Handle inline code or code blocks without language
    // Check if it's Chart.js HTML even without language specification
    if (codeString.includes('<div id="chart-container-') && codeString.includes('</script>')) {
      return (
        <div className="my-3">
          <div className="flex items-center justify-between px-3 py-1 bg-gray-100 border border-gray-300 rounded-t-md">
            <span className="text-xs text-gray-500">Interactive Chart</span>
            <CopyButton text={codeString} />
          </div>
          <div 
            className="border border-t-0 border-gray-300 rounded-b-md p-4 bg-white"
            dangerouslySetInnerHTML={{ __html: codeString }}
          />
        </div>
      )
    }
    
    return <code className="px-1 py-0.5 bg-gray-200/60 rounded text-[0.85em] font-mono">{children}</code>
  },
  pre({ children }: { children?: React.ReactNode }) {
    return <>{children}</>
  },
  img({ src, alt }: { src?: string; alt?: string }) {
    // Handle base64 images from Code Interpreter with proper sizing
    return (
      <div className="my-3 rounded-lg overflow-hidden border border-gray-200 bg-white p-3">
        <img 
          src={src} 
          alt={alt || "Chart"} 
          className="w-full h-auto max-w-full rounded"
          style={{ maxHeight: '500px', objectFit: 'contain' }}
          loading="lazy"
        />
      </div>
    )
  },
}

export function MarkdownRenderer({ content }: { content: string }) {
  if (!content) return null
  
  // Check if content contains Chart.js HTML (div with chart-container id)
  const hasChartJsHtml = content.includes('<div id="chart-container-') && content.includes('</script>')
  
  if (hasChartJsHtml) {
    // Split content into text and HTML parts
    const parts: Array<{ type: 'text' | 'html', content: string }> = []
    
    // Match Chart.js HTML blocks
    const chartRegex = /<div id="chart-container-[^"]+">[\s\S]*?<\/script>\s*<\/div>/g
    let lastIndex = 0
    let match
    
    while ((match = chartRegex.exec(content)) !== null) {
      // Add text before the chart
      if (match.index > lastIndex) {
        const textBefore = content.substring(lastIndex, match.index).trim()
        if (textBefore) {
          parts.push({ type: 'text', content: textBefore })
        }
      }
      
      // Add the chart HTML
      parts.push({ type: 'html', content: match[0] })
      lastIndex = match.index + match[0].length
    }
    
    // Add remaining text after the last chart
    if (lastIndex < content.length) {
      const textAfter = content.substring(lastIndex).trim()
      if (textAfter) {
        parts.push({ type: 'text', content: textAfter })
      }
    }
    
    // Render mixed content
    return (
      <div className="space-y-3">
        {parts.map((part, idx) => {
          if (part.type === 'html') {
            return (
              <div 
                key={idx}
                className="my-4 bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700"
                dangerouslySetInnerHTML={{ __html: part.content }}
              />
            )
          }
          return (
            <div key={idx} className="markdown-body leading-relaxed [&_p]:my-1.5 [&_ul]:my-1.5 [&_ul]:pl-5 [&_ul]:list-disc [&_ol]:my-1.5 [&_ol]:pl-5 [&_ol]:list-decimal [&_li]:my-0.5 [&_h1]:text-lg [&_h1]:font-semibold [&_h1]:mt-3 [&_h1]:mb-1.5 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:mt-2.5 [&_h2]:mb-1 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1 [&_blockquote]:border-l-2 [&_blockquote]:border-gray-300 [&_blockquote]:pl-3 [&_blockquote]:my-1.5 [&_blockquote]:text-gray-600 [&_table]:my-2 [&_table]:min-w-full [&_table]:border-collapse [&_table]:text-xs [&_th]:px-2 [&_th]:py-1 [&_th]:bg-gray-100 [&_th]:border [&_th]:border-gray-300 [&_th]:text-left [&_th]:font-medium [&_td]:px-2 [&_td]:py-1 [&_td]:border [&_td]:border-gray-300 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
                {completePartialMarkdown(part.content)}
              </ReactMarkdown>
            </div>
          )
        })}
      </div>
    )
  }
  
  // Regular markdown rendering
  return (
    <div className="markdown-body leading-relaxed [&_p]:my-1.5 [&_ul]:my-1.5 [&_ul]:pl-5 [&_ul]:list-disc [&_ol]:my-1.5 [&_ol]:pl-5 [&_ol]:list-decimal [&_li]:my-0.5 [&_h1]:text-lg [&_h1]:font-semibold [&_h1]:mt-3 [&_h1]:mb-1.5 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:mt-2.5 [&_h2]:mb-1 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1 [&_blockquote]:border-l-2 [&_blockquote]:border-gray-300 [&_blockquote]:pl-3 [&_blockquote]:my-1.5 [&_blockquote]:text-gray-600 [&_table]:my-2 [&_table]:min-w-full [&_table]:border-collapse [&_table]:text-xs [&_th]:px-2 [&_th]:py-1 [&_th]:bg-gray-100 [&_th]:border [&_th]:border-gray-300 [&_th]:text-left [&_th]:font-medium [&_td]:px-2 [&_td]:py-1 [&_td]:border [&_td]:border-gray-300 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {completePartialMarkdown(content)}
      </ReactMarkdown>
    </div>
  )
}
