import type { ComponentProps } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { CopyButton } from "./CopyButton";

export interface MarkdownViewProps {
  content: string;
  /** `large` uses body-lg (16/26) for long-form prose: RCA, chat answers, postmortems. */
  size?: "default" | "large";
  className?: string;
}

interface HastNode {
  type: string;
  value?: string;
  children?: HastNode[];
}

function textOfNode(node: HastNode | undefined): string {
  if (!node) {
    return "";
  }
  if (node.type === "text") {
    return node.value ?? "";
  }
  return (node.children ?? []).map(textOfNode).join("");
}

function CodeBlock({ node, children }: ComponentProps<"pre"> & { node?: HastNode }) {
  const { t } = useTranslation("common");
  const codeText = textOfNode(node).replace(/\n$/, "");
  return (
    <div className="keigan-prose-code-block flex items-start overflow-hidden rounded-md border border-[#1E3044] bg-code-surface">
      <pre tabIndex={0} className="min-w-0 flex-1 overflow-x-auto px-4 py-3.5 font-mono text-code whitespace-pre text-on-code">
        {children}
      </pre>
      <div className="shrink-0 border-l border-white/8 p-1.5">
        <CopyButton value={codeText} label={t("markdown.copyCode")} variant="onDark" />
      </div>
    </div>
  );
}

/** Headings render one level down (a markdown `#` becomes an h2) so content never competes with the page h1. */
const markdownComponents: Components = {
  h1: ({ node: _node, ...headingProps }) => <h2 {...headingProps} />,
  h2: ({ node: _node, ...headingProps }) => <h3 {...headingProps} />,
  h3: ({ node: _node, ...headingProps }) => <h4 {...headingProps} />,
  h4: ({ node: _node, ...headingProps }) => <h5 {...headingProps} />,
  h5: ({ node: _node, ...headingProps }) => <h6 {...headingProps} />,
  a: ({ node: _node, ...anchorProps }) => <a {...anchorProps} target="_blank" rel="noopener noreferrer" />,
  pre: ({ node, children }) => <CodeBlock node={node as HastNode | undefined}>{children}</CodeBlock>,
  table: ({ node: _node, ...tableProps }) => <table {...tableProps} />,
};

/**
 * Safe Markdown (GFM tables, task lists, code with copy). Raw HTML is dropped; links open in a new tab with
 * `rel="noopener noreferrer"`; unsafe URL schemes are removed by react-markdown's default URL transform.
 */
export function MarkdownView({ content, size = "default", className }: MarkdownViewProps) {
  return (
    <div className={cn("keigan-prose", size === "large" && "keigan-prose-large", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
