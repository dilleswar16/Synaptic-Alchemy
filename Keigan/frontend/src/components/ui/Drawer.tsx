import { useRef, type ReactElement, type ReactNode } from "react";
import { X } from "lucide-react";
import { Dialog as RadixDialog } from "radix-ui";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";

export interface DrawerProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: ReactElement;
  title: ReactNode;
  description?: ReactNode;
  /** Extra header content under the title (chips, tabs). */
  headerContent?: ReactNode;
  /** Buttons next to the close button. */
  headerActions?: ReactNode;
  children?: ReactNode;
  /** Sticky footer with actions. */
  footer?: ReactNode;
  /** sm 480 px · md 640 px (default) · lg 880 px. */
  size?: "sm" | "md" | "lg";
  className?: string;
}

const drawerWidths = { sm: "max-w-[480px]", md: "max-w-[640px]", lg: "max-w-[880px]" } as const;

/**
 * Right-side sheet for details and multi-field edits; sticky header and footer, scrolling body. Opened with `trigger`, focus returns to it on close; opened
 * through `open` alone (no trigger), focus returns to the element that had it when the sheet opened, which Radix would otherwise lose to the page body.
 */
export function Drawer({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  headerContent,
  headerActions,
  children,
  footer,
  size = "md",
  className,
}: DrawerProps) {
  const { t } = useTranslation("common");
  const returnFocusReference = useRef<HTMLElement | null>(null);
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger> : null}
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-50 bg-overlay data-[state=closed]:animate-fade-out data-[state=open]:animate-fade-in" />
        <RadixDialog.Content
          {...(description ? {} : { "aria-describedby": undefined })}
          onOpenAutoFocus={() => {
            returnFocusReference.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
          }}
          onCloseAutoFocus={(event) => {
            if (!trigger) {
              event.preventDefault();
              returnFocusReference.current?.focus();
            }
          }}
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-hairline bg-surface shadow-lg sm:rounded-l-lg",
            "data-[state=closed]:animate-drawer-out data-[state=open]:animate-drawer-in focus-visible:outline-none",
            drawerWidths[size],
            className,
          )}
        >
          <header className="shrink-0 border-b border-hairline px-6 pt-5 pb-4">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <RadixDialog.Title className="font-display text-h2 text-default">{title}</RadixDialog.Title>
                {description ? <RadixDialog.Description className="mt-1 text-body-sm text-muted">{description}</RadixDialog.Description> : null}
              </div>
              {headerActions ? <div className="flex items-center gap-1">{headerActions}</div> : null}
              <RadixDialog.Close
                aria-label={t("actions.close")}
                className="-mr-2 grid size-9 shrink-0 place-items-center rounded-sm text-muted transition-colors hover:bg-surface-hover hover:text-default"
              >
                <X aria-hidden="true" size={18} strokeWidth={1.75} />
              </RadixDialog.Close>
            </div>
            {headerContent ? <div className="mt-3">{headerContent}</div> : null}
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
          {footer ? (
            <footer className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-hairline bg-surface px-6 py-4">
              {footer}
            </footer>
          ) : null}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
