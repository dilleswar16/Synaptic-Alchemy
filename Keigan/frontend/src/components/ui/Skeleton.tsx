import type { ComponentProps } from "react";
import { cn } from "@/utils/cn";

export interface SkeletonProps extends ComponentProps<"div"> {
  shape?: "block" | "text" | "circle";
}

/** Low-contrast shimmer placeholder. Size it with classes: `<Skeleton className="h-4 w-40" />`. */
export function Skeleton({ shape = "block", className, ...divProps }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "skeleton-shimmer",
        shape === "block" && "rounded-sm",
        shape === "text" && "h-3.5 rounded-xs",
        shape === "circle" && "rounded-full",
        className,
      )}
      {...divProps}
    />
  );
}

export interface SkeletonTextProps {
  lineCount?: number;
  className?: string;
}

/** Paragraph placeholder; the last line is shorter. */
export function SkeletonText({ lineCount = 3, className }: SkeletonTextProps) {
  return (
    <div aria-hidden="true" className={cn("flex flex-col gap-2.5", className)}>
      {Array.from({ length: lineCount }, (_, lineIndex) => (
        <Skeleton key={lineIndex} shape="text" className={lineIndex === lineCount - 1 ? "w-3/5" : "w-full"} />
      ))}
    </div>
  );
}
