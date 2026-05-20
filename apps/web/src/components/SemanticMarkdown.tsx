import React from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { TechnicalHighlighter } from './TechnicalHighlighter'
import MermaidChart from './common/MermaidChart'

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

const UL_STYLE: React.CSSProperties = {
  margin: '4px 0 10px',
  paddingLeft: 0,
  listStyle: 'none',
}
const OL_STYLE: React.CSSProperties = {
  margin: '4px 0 10px',
  paddingLeft: 20,
}
const LI_STYLE: React.CSSProperties = {
  position: 'relative',
  paddingLeft: 14,
  margin: '5px 0',
  lineHeight: 1.7,
}

const components: Components = {
  p: ({ children, ...props }) => (
    <p style={{ margin: '0 0 8px', lineHeight: 1.75 }} {...props}>
      {processChildren(children)}
    </p>
  ),
  ul: ({ children }) => <ul style={UL_STYLE} className="corvin-sm-ul">{children}</ul>,
  ol: ({ children }) => <ol style={OL_STYLE}>{children}</ol>,
  li: ({ children, ...props }) => (
    <li style={LI_STYLE} {...props}>
      {processChildren(children)}
    </li>
  ),
  strong: ({ children }) => (
    <strong style={{ color: 'var(--c-text)', fontWeight: 600 }}>{children}</strong>
  ),
  em: ({ children }) => (
    <em style={{ color: 'var(--c-text-muted)', fontStyle: 'italic' }}>{children}</em>
  ),
  h1: ({ children }) => (
    <h1 style={{ fontSize: '1.05rem', fontWeight: 700, margin: '16px 0 6px', color: 'var(--c-text)' }}>
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 style={{
      fontSize: '0.9rem', fontWeight: 700, margin: '14px 0 5px', color: 'var(--c-text)',
      borderBottom: '1px solid var(--c-border-glow)', paddingBottom: 4,
    }}>
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 style={{
      fontSize: '0.8rem', fontWeight: 600, margin: '10px 0 4px',
      color: 'var(--c-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em',
    }}>
      {children}
    </h3>
  ),
  td: ({ children, ...props }) => <td {...props}>{processChildren(children)}</td>,
  th: ({ children, ...props }) => <th {...props}>{processChildren(children)}</th>,
  span: ({ children, ...props }) => <span {...props}>{processChildren(children)}</span>,
  blockquote: ({ children }) => (
    <div style={{
      margin: '10px 0',
      padding: '10px 14px 10px 16px',
      borderLeft: '3px solid rgba(124,58,237,0.5)',
      background: 'rgba(124,58,237,0.05)',
      borderRadius: '0 6px 6px 0',
      color: 'var(--c-text-dim)',
      fontStyle: 'italic',
    }}>
      {children}
    </div>
  ),
  code: ({ children, className, ...props }) => {
    if (className === 'language-mermaid') {
      return <MermaidChart chart={String(children).trim()} />
    }
    const isInline = !className
    if (isInline && typeof children === 'string') {
      return <code {...props}><TechnicalHighlighter text={children} /></code>
    }
    return <code className={className} {...props}>{children}</code>
  },
}

export function SemanticMarkdown({ children }: SemanticMarkdownProps) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  )
}
