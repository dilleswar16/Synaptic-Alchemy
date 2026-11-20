import type { ReactElement, ReactNode } from "react";
import { X } from "lucide-react";
import { Dialog as RadixDialog } from "radix-ui";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";

export interface DialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  defaultOpen?: boolean;
  /** Optional element that opens the dialog (rendered with `asChild`). */
  trigger?: ReactElement;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  /** Actions row (right-aligned). Use verb + object labels: "Create application", never "OK". */
  footer?: ReactNode;
  /** md 560 px (default) · lg 760 px. */
  size?: "md" | "lg";
  hideCloseButton?: boolean;
  className?: string;
}

/**
 * Modal dialog: radius 16, shadow-lg, title h2, focus trap, Esc closes and focus returns to the trigger.
 * Controlled with `open`/`onOpenChange` or self-contained with `trigger`.
 */
export function Dialog({
  open,
  onOpenChange,
  defaultOpen,
  trigger,
  title,
  description,
  children,
  footer,
  size = "md",
  hideCloseButton = false,
  className,
}: DialogProps) {
  const { t } = useTranslation("common");
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange} defaultOpen={defaultOpen}>
      {trigger ? <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger> : null}
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-overlay p-4 backdrop-blur-[2px] data-[state=closed]:animate-fade-out data-[state=open]:animate-fade-in sm:p-6">
          <RadixDialog.Content
            {...(description ? {} : { "aria-describedby": undefined })}
            className={cn(
              "relative flex max-h-[calc(100dvh-2rem)] w-full flex-col overflow-hidden rounded-lg border border-hairline bg-surface shadow-lg",
              "data-[state=closed]:animate-pop-out data-[state=open]:animate-dialog-in focus-visible:outline-none",
              size === "md" ? "max-w-[560px]" : "max-w-[760px]",
              className,
            )}
          >
            <div className="flex items-start gap-4 px-6 pt-6 pb-4">
              <div className="min-w-0 flex-1">
                <RadixDialog.Title className="font-display text-h2 text-default">{title}</RadixDialog.Title>
                {description ? <RadixDialog.Description className="mt-1 text-body text-muted">{description}</RadixDialog.Description> : null}
              </div>
              {hideCloseButton ? null : (
                <RadixDialog.Close
                  aria-label={t("actions.close")}
                  className="-mt-1 -mr-2 grid size-9 shrink-0 place-items-center rounded-sm text-muted transition-colors hover:bg-surface-hover hover:text-default"
                >
                  <X aria-hidden="true" size={18} strokeWidth={1.75} />
                </RadixDialog.Close>
              )}
            </div>
            {children ? <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">{children}</div> : null}
            {footer ? (
              <div className="flex flex-wrap items-center justify-end gap-2 border-t border-hairline bg-surface-sunken/50 px-6 py-4">{footer}</div>
            ) : null}
          </RadixDialog.Content>
        </RadixDialog.Overlay>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

/** Closes the surrounding Dialog or Drawer when the child is clicked: `<DialogClose asChild><Button>…</Button></DialogClose>`. */
export const DialogClose = RadixDialog.Close;
