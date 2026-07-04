import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { Components } from 'react-markdown'

interface MarkdownMessageProps {
  content: string
}

export function MarkdownMessage({ content }: MarkdownMessageProps) {
  const components: Components = {
    code({ node, className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '')
      const inline = !match && !String(children).includes('\n')

      return inline ? (
        <code
          className="bg-light text-dark px-1 rounded"
          style={{ fontSize: '0.9em' }}
          {...props}
        >
          {children}
        </code>
      ) : (
        <SyntaxHighlighter
          style={oneDark}
          language={match ? match[1] : 'text'}
          PreTag="div"
          customStyle={{
            margin: '0.5rem 0',
            borderRadius: '0.375rem',
            fontSize: '0.875rem',
          }}
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      )
    },
    table({ children }) {
      return (
        <div className="table-responsive my-2">
          <table className="table table-sm table-bordered">{children}</table>
        </div>
      )
    },
    a({ children, href }) {
      return (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      )
    },
  }

  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}