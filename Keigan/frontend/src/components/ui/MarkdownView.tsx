import { useContext, useMemo, type ComponentProps, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { useTranslation } from "react-i18next";
import { defaultAllowedLinkHosts } from "@/config/allowedLinkHosts";
import { RuntimeConfigurationContext } from "@/config/runtimeConfiguration";
import { cn } from "@/utils/cn";
import { splitCitationCodes } from "@/utils/citationCodes";
import { allowedLinkUrl } from "@/utils/linkSafety";
import { CopyButton } from "./CopyButton";

export interface MarkdownViewProps {
  content: string;
  /** `large` uses body-lg (16/26) for long-form prose: RCA, chat answers, postmortems. */
  size?: "default" | "large";
  /**
   * Turns a citation code written in the text (`[T2]`, `[E3]`, `[R1]`) into a chip. Return null for a code that has no source: it stays as plain text.
   * Without this prop the text is rendered as written.
   */
  renderCitation?: (citationCode: string) => ReactNode | null;
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
    <div className="keigan-prose-code-block flex items-start overflow-hidden rounded-md border border-white/10 bg-code-surface">
      <pre tabIndex={0} className="min-w-0 flex-1 overflow-x-auto px-4 py-3.5 font-mono text-code whitespace-pre text-on-code">
        {children}
      </pre>
      <div className="shrink-0 border-l border-white/8 p-1.5">
        <CopyButton value={codeText} label={t("markdown.copyCode")} variant="onDark" />
      </div>
    </div>
  );
}

interface MarkdownTreeNode {
  type: string;
  value?: string;
  children?: MarkdownTreeNode[];
  data?: { hName: string; hProperties: Record<string, string> };
}

/** Remark plugin: replaces each citation code inside a text node with an empty `span` carrying the code, which `markdownComponentsFor` renders. */
function remarkCitationCodes() {
  const replaceCitationCodes = (parent: MarkdownTreeNode) => {
    parent.children = parent.children?.flatMap((child): MarkdownTreeNode[] => {
      if (child.type !== "text" || child.value === undefined) {
        replaceCitationCodes(child);
        return [child];
      }
      const parts = splitCitationCodes(child.value);
      if (parts.length === 1) {
        return [child];
      }
      return parts.map((part): MarkdownTreeNode =>
        part.kind === "text"
          ? { type: "text", value: part.text }
          : { type: "citation", children: [], data: { hName: "span", hProperties: { dataCitationCode: part.code } } },
      );
    });
  };
  return replaceCitationCodes;
}

/**
 * Headings render one level down (a markdown `#` becomes an h2) so content never competes with the page h1.
 * Links to hosts outside the allow-list become plain text and images become their alt text (security review V8).
 */
function markdownComponentsFor(allowedLinkHosts: readonly string[], renderCitation: MarkdownViewProps["renderCitation"]): Components {
  return {
    h1: ({ node: _node, ...headingProps }) => <h2 {...headingProps} />,
    h2: ({ node: _node, ...headingProps }) => <h3 {...headingProps} />,
    h3: ({ node: _node, ...headingProps }) => <h4 {...headingProps} />,
    h4: ({ node: _node, ...headingProps }) => <h5 {...headingProps} />,
    h5: ({ node: _node, ...headingProps }) => <h6 {...headingProps} />,
    a: ({ node: _node, href, children, ...anchorProps }) => {
      const safeHref = allowedLinkUrl(href, allowedLinkHosts);
      return safeHref ? <a {...anchorProps} href={safeHref} target="_blank" rel="noopener noreferrer">{children}</a> : <>{children}</>;
    },
    img: ({ alt }) => <>{alt ?? ""}</>,
    pre: ({ node, children }) => <CodeBlock node={node as HastNode | undefined}>{children}</CodeBlock>,
    table: ({ node: _node, ...tableProps }) => <table {...tableProps} />,
    span: ({ node: _node, ...spanProps }) => {
      const citationCode = (spanProps as Record<string, unknown>)["data-citation-code"];
      return typeof citationCode === "string" ? (renderCitation?.(citationCode) ?? `[${citationCode}]`) : <span {...spanProps} />;
    },
  };
}

/**
 * Safe Markdown (GFM tables, task lists, code with copy). Raw HTML is dropped; only https links to allow-listed hosts are
 * rendered, opening in a new tab with `rel="noopener noreferrer"`; other links show their text only and images show their alt text.
 */
export function MarkdownView({ content, size = "default", renderCitation, className }: MarkdownViewProps) {
  const allowedLinkHosts = useContext(RuntimeConfigurationContext)?.allowedLinkHosts ?? defaultAllowedLinkHosts;
  const markdownComponents = useMemo(() => markdownComponentsFor(allowedLinkHosts, renderCitation), [allowedLinkHosts, renderCitation]);
  return (
    <div className={cn("keigan-prose", size === "large" && "keigan-prose-large", className)}>
      <ReactMarkdown remarkPlugins={renderCitation ? [remarkGfm, remarkCitationCodes] : [remarkGfm]} skipHtml components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
