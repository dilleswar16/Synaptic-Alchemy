import React from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { TechnicalHighlighter } from './TechnicalHighlighter'

interface SemanticMarkdownProps {
  children: string
}

function processChildren(children: React.ReactNode): React.ReactNode {
  return React.Children.map(children, child => {
    if (typeof child === 'string') {
      return <TechnicalHighlighter text={child} />
    }
    return child
  })
}

const components: Components = {
  p: ({ children, ...props }) => <p {...props}>{processChildren(children)}</p>,
  li: ({ children, ...props }) => <li {...props}>{processChildren(children)}</li>,
  td: ({ children, ...props }) => <td {...props}>{processChildren(children)}</td>,
  th: ({ children, ...props }) => <th {...props}>{processChildren(children)}</th>,
  span: ({ children, ...props }) => <span {...props}>{processChildren(children)}</span>,
  code: ({ children, className, ...props }) => {
    const isInline = !className
    if (isInline && typeof children === 'string') {
      return <code {...props}><TechnicalHighlighter text={children} /></code>
    }
    return <code className={className} {...props}>{children}</code>
  }
}

export function SemanticMarkdown({ children }: SemanticMarkdownProps) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  )
}
