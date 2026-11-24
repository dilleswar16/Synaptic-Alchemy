import { useLayoutEffect, useRef, type ComponentProps, type Ref } from "react";
import { cn } from "@/utils/cn";
import { describedByIds, FormField, useFormFieldIds, type FieldDecorationProps } from "./FormField";

export interface TextareaProps extends ComponentProps<"textarea">, FieldDecorationProps {
  /** Grow with content up to `maximumRows` (default 12). */
  autoResize?: boolean;
  maximumRows?: number;
  containerClassName?: string;
  /** Use the monospace font (queries, markdown sources). */
  isMonospace?: boolean;
}

function assignRef<ElementType>(ref: Ref<ElementType> | undefined, element: ElementType | null): void {
  if (typeof ref === "function") {
    ref(element);
  } else if (ref) {
    ref.current = element;
  }
}

export function Textarea({
  label,
  helperText,
  errorMessage,
  isOptional,
  labelAction,
  autoResize = false,
  maximumRows = 12,
  containerClassName,
  isMonospace = false,
  className,
  id,
  rows = 4,
  ref,
  ...textareaProps
}: TextareaProps) {
  const fieldIds = useFormFieldIds(id);
  const hasError = Boolean(errorMessage);
  const textareaElementRef = useRef<HTMLTextAreaElement | null>(null);

  useLayoutEffect(() => {
    const textareaElement = textareaElementRef.current;
    if (!autoResize || !textareaElement) {
      return;
    }
    const resize = () => {
      const lineHeight = Number.parseFloat(getComputedStyle(textareaElement).lineHeight) || 24;
      textareaElement.style.height = "auto";
      textareaElement.style.height = `${Math.min(textareaElement.scrollHeight + 2, lineHeight * maximumRows + 20)}px`;
    };
    resize();
    textareaElement.addEventListener("input", resize);
    return () => textareaElement.removeEventListener("input", resize);
  }, [autoResize, maximumRows, textareaProps.value]);

  return (
    <FormField
      label={label}
      helperText={helperText}
      errorMessage={errorMessage}
      isOptional={isOptional}
      labelAction={labelAction}
      fieldIds={fieldIds}
      className={containerClassName}
    >
      <textarea
        ref={(element) => {
          textareaElementRef.current = element;
          assignRef(ref, element);
        }}
        id={fieldIds.controlId}
        rows={rows}
        aria-invalid={hasError || undefined}
        aria-describedby={describedByIds(fieldIds, Boolean(helperText), hasError)}
        className={cn(
          "w-full min-w-0 rounded-sm border border-control bg-surface px-[var(--control-px-md,0.75rem)] py-[var(--control-py,0.5rem)] text-body text-default shadow-xs transition-[border-color,box-shadow]",
          "placeholder:text-subtle hover:border-subtle focus-visible:border-action",
          "disabled:cursor-not-allowed disabled:bg-surface-sunken disabled:text-muted aria-[invalid=true]:border-danger-fill",
          autoResize ? "resize-none overflow-y-auto" : "resize-y",
          isMonospace && "font-mono text-code",
          className,
        )}
        {...textareaProps}
      />
    </FormField>
  );
}
