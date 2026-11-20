import { cn } from "@/utils/cn";

export interface AvatarProps {
  name: string;
  /** sm 24 · md 32 (default) · lg 40. */
  size?: "sm" | "md" | "lg";
  className?: string;
}

const avatarSizes = { sm: "size-6 text-[10px]", md: "size-8 text-micro", lg: "size-10 text-body-sm" } as const;

/** Two initials ("Aiko AppAdmin" → "AA"); first character for CJK names. */
export function initialsFor(name: string): string {
  const nameParts = name.trim().split(/\s+/).filter(Boolean);
  if (nameParts.length === 0) {
    return "?";
  }
  const firstPart = nameParts[0] ?? "";
  if (/[぀-ヿ㐀-鿿]/.test(firstPart)) {
    return firstPart.charAt(0);
  }
  const lastPart = nameParts.length > 1 ? (nameParts[nameParts.length - 1] ?? "") : "";
  return `${firstPart.charAt(0)}${lastPart.charAt(0)}`.toUpperCase();
}

/** Initials on the soft brand gradient (doc 04 §5). Decorative: pair it with the visible name. */
export function Avatar({ name, size = "md", className }: AvatarProps) {
  return (
    <span
      aria-hidden="true"
      title={name}
      className={cn(
        "inline-grid shrink-0 place-items-center rounded-full bg-gradient-brand-soft font-semibold text-brand ring-1 ring-brand/20 select-none",
        avatarSizes[size],
        className,
      )}
    >
      {initialsFor(name)}
    </span>
  );
}
