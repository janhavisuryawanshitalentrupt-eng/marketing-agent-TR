"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-1">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-1">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        strong: ({ children }) => (
          <strong className="font-semibold text-foreground">{children}</strong>
        ),
        h1: ({ children }) => <h3 className="mb-2 font-heading text-base font-semibold">{children}</h3>,
        h2: ({ children }) => <h3 className="mb-2 font-heading text-base font-semibold">{children}</h3>,
        h3: ({ children }) => <h3 className="mb-1.5 font-heading text-sm font-semibold">{children}</h3>,
        a: ({ children, href }) => (
          <a href={href} className="text-[var(--brand-red)] underline" target="_blank" rel="noreferrer">
            {children}
          </a>
        ),
        code: ({ children }) => (
          <code className="rounded bg-[var(--background)] px-1 py-0.5 text-xs">{children}</code>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
