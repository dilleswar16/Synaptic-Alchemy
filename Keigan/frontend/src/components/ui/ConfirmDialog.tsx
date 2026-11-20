import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "./Button";
import { Dialog } from "./Dialog";

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  /** Say exactly what happens, e.g. "Keigan stops watching 6 services in claims-rg." */
  description?: ReactNode;
  children?: ReactNode;
  /** Verb + object: "Remove component". */
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "danger" | "primary";
  /** May return a promise; the button shows a spinner until it settles and the dialog closes on success. */
  onConfirm: () => void | Promise<void>;
}

/** Confirmation for destructive or irreversible actions. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  confirmLabel,
  cancelLabel,
  tone = "danger",
  onConfirm,
}: ConfirmDialogProps) {
  const { t } = useTranslation("common");
  const [isConfirming, setIsConfirming] = useState(false);

  const handleConfirm = async () => {
    setIsConfirming(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setIsConfirming(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => (isConfirming ? undefined : onOpenChange(nextOpen))}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={isConfirming}>
            {cancelLabel ?? t("actions.cancel")}
          </Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} onClick={handleConfirm} isLoading={isConfirming}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}
