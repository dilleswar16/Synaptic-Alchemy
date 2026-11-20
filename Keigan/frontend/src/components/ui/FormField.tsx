import { useId, type ReactNode } from "react";
import { CircleExclamationPoint } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";

export interface FormFieldIds {
  controlId: string;
  labelId: string;
  helperId: string;
  errorId: string;
}

/** Stable ids for a control and its label / helper / error, honouring a caller-provided id. */
export function useFormFieldIds(providedId?: string): FormFieldIds {
  const generatedId = useId();
  const controlId = providedId ?? `field-${generatedId}`;
  return { controlId, labelId: `${controlId}-label`, helperId: `${controlId}-helper`, errorId: `${controlId}-error` };
}

/** `aria-describedby` value for the parts that are actually rendered. */
export function describedByIds(fieldIds: FormFieldIds, hasHelper: boolean, hasError: boolean): string | undefined {
  const describedBy = [hasError ? fieldIds.errorId : null, hasHelper ? fieldIds.helperId : null].filter(Boolean).join(" ");
  return describedBy || undefined;
}

/** Shared props of every labelled form control. */
export interface FieldDecorationProps {
  /** Label above the control (body-sm 14/600). */
  label?: ReactNode;
  /** Helper text below (caption, muted). */
  helperText?: ReactNode;
  /** Error message below (danger, with icon). Only pass it after the user has interacted. */
  errorMessage?: ReactNode;
  /** Adds a muted "Optional" marker after the label. */
  isOptional?: boolean;
  /** Content aligned to the right of the label (e.g. a "Generate" link). */
  labelAction?: ReactNode;
}

export interface FormFieldProps extends FieldDecorationProps {
  fieldIds: FormFieldIds;
  children: ReactNode;
  className?: string;
  /** Use `<span>` instead of `<label>` (for groups such as radio groups that label themselves). */
  isLabelElementless?: boolean;
}

/** Label → control → helper / error layout used by Input, Select, Combobox, TokenInput and custom controls. */
export function FormField({
  label,
  helperText,
  errorMessage,
  isOptional = false,
  labelAction,
  fieldIds,
  children,
  className,
  isLabelElementless = false,
}: FormFieldProps) {
  const { t } = useTranslation("common");
  const LabelElement = isLabelElementless ? "span" : "label";
  return (
    <div className={cn("flex min-w-0 flex-col gap-2", className)}>
      {label || labelAction ? (
        <div className="flex items-baseline justify-between gap-3">
          {label ? (
            <LabelElement
              id={fieldIds.labelId}
              {...(isLabelElementless ? {} : { htmlFor: fieldIds.controlId })}
              className="text-body-sm font-semibold text-default"
            >
              {label}
              {isOptional ? <span className="ml-1.5 font-normal text-muted">({t("states.optional")})</span> : null}
            </LabelElement>
          ) : (
            <span />
          )}
          {labelAction}
        </div>
      ) : null}
      {children}
      {errorMessage ? (
        <p id={fieldIds.errorId} role="alert" className="flex items-start gap-1.5 text-caption text-danger">
          <CircleExclamationPoint aria-hidden="true" size={14} strokeWidth={2} className="mt-0.5 shrink-0" />
          <span>{errorMessage}</span>
        </p>
      ) : null}
      {helperText ? (
        <p id={fieldIds.helperId} className="text-caption font-normal text-muted">
          {helperText}
        </p>
      ) : null}
    </div>
  );
}

/** Classes for an input-like box: 40 px, radius 8, border-control, focus ring, invalid state. */
export function controlBoxClassName(size: "sm" | "md" = "md"): string {
  return cn(
    "w-full min-w-0 rounded-sm border border-control bg-surface text-default shadow-xs transition-[border-color,box-shadow]",
    "placeholder:text-subtle hover:border-subtle focus-visible:border-action",
    "disabled:cursor-not-allowed disabled:bg-surface-sunken disabled:text-muted disabled:shadow-none",
    "aria-[invalid=true]:border-danger-fill",
    size === "md" ? "h-10 px-3 text-body" : "h-8 px-2.5 text-body-sm",
  );
}
