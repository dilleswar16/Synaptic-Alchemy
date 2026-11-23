import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useTheme } from "@/hooks/useTheme";
import { CopyButton } from "./CopyButton";

/** The server refuses a longer diagram (spec 36, D4); the library is told the same ceiling so a diagram it was never meant to see cannot reach it. */
const maximumDiagramCharacters = 20_000;
const maximumDiagramEdges = 500;

type DrawState = { kind: "drawing" } | { kind: "drawn"; svg: string } | { kind: "failed" };

/** Mermaid draws one diagram at a time (it keeps global state while it does), so the draws wait in line. */
let drawQueue: Promise<unknown> = Promise.resolve();

async function drawDiagram(identifier: string, source: string, theme: "light" | "dark"): Promise<string> {
  const draw = async (): Promise<string> => {
    const { default: mermaid } = await import("mermaid");
    mermaid.initialize({
      startOnLoad: false,
      // Strict: no scripts, no click handlers, no links; labels are drawn as SVG text, never as HTML (spec 36, D2).
      securityLevel: "strict",
      flowchart: { htmlLabels: false },
      theme: theme === "dark" ? "dark" : "default",
      suppressErrorRendering: true,
      maxTextSize: maximumDiagramCharacters,
      maxEdges: maximumDiagramEdges,
    });
    try {
      return (await mermaid.render(identifier, source)).svg;
    } finally {
      document.getElementById(`d${identifier}`)?.remove(); // a failed draw can leave its scratch element behind
    }
  };
  const result = drawQueue.then(draw, draw);
  drawQueue = result.catch(() => undefined);
  return result;
}

/** The first line names the diagram type; it is the screen reader's description of a picture that has no text of its own. */
function diagramKind(source: string): string {
  return (source.trim().split(/\s+/)[0] ?? "").replace(/[^A-Za-z0-9-]/g, "");
}

function SourceView({ source }: { source: string }) {
  const { t } = useTranslation("common");
  return (
    <div className="flex items-start overflow-hidden rounded-md border border-white/10 bg-code-surface">
      <pre tabIndex={0} className="min-w-0 flex-1 overflow-x-auto px-4 py-3.5 font-mono text-code whitespace-pre text-on-code">{source}</pre>
      <div className="shrink-0 border-l border-white/8 p-1.5">
        <CopyButton value={source} label={t("markdown.copyCode")} variant="onDark" />
      </div>
    </div>
  );
}

/**
 * A Mermaid diagram written by Keigan's AI, drawn in the browser (spec 36). The server has already checked the text; the library loads only when a diagram appears. A diagram that
 * cannot be drawn is shown as its source with a note, and every drawn one says it is an illustration and can show its source.
 */
export function MermaidDiagram({ source, caption }: { source: string; caption?: string }) {
  const { t } = useTranslation("common");
  const { resolvedTheme } = useTheme();
  const identifier = `mermaid-${useId().replace(/[^A-Za-z0-9]/g, "")}`;
  const [state, setState] = useState<DrawState>({ kind: "drawing" });
  const containerReference = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let isCurrent = true;
    setState({ kind: "drawing" });
    drawDiagram(identifier, source, resolvedTheme).then(
      (svg) => { if (isCurrent) setState({ kind: "drawn", svg }); },
      () => { if (isCurrent) setState({ kind: "failed" }); },
    );
    return () => { isCurrent = false; };
  }, [identifier, source, resolvedTheme]);

  useEffect(() => {
    if (containerReference.current && state.kind === "drawn") {
      containerReference.current.innerHTML = state.svg; // already sanitised by the library in strict mode
    }
  }, [state]);

  if (state.kind === "failed") {
    return (
      <div className="my-3 flex flex-col gap-2">
        <p role="note" className="text-body-sm text-muted">{t("mermaid.failed")}</p>
        <SourceView source={source} />
      </div>
    );
  }
  return (
    <figure className="my-3 flex min-w-0 flex-col gap-2 rounded-md border border-hairline bg-surface p-3">
      {state.kind === "drawing" ? <p role="status" className="text-body-sm text-muted">{t("mermaid.drawing")}</p> : null}
      <div ref={containerReference} role="img" aria-label={t("mermaid.label", { kind: diagramKind(source) })} className="max-h-[32rem] overflow-auto [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full" />
      <figcaption className="text-caption text-muted">{caption ?? t("mermaid.illustration")}</figcaption>
      <details className="text-body-sm">
        <summary className="cursor-pointer text-muted hover:text-default">{t("mermaid.showSource")}</summary>
        <div className="mt-2"><SourceView source={source} /></div>
      </details>
    </figure>
  );
}

/** A diagram the server did not let through: the source as code, and why. `reason` is the server's problem code (spec 36, D3). */
export function WithheldDiagram({ source, reason }: { source: string; reason: string }) {
  const { t } = useTranslation("common");
  return (
    <div className="my-3 flex flex-col gap-2">
      <p role="note" className="text-body-sm text-muted">{t(`mermaid.withheld.${reason}`, { defaultValue: t("mermaid.withheld.other") })}</p>
      <SourceView source={source} />
    </div>
  );
}
