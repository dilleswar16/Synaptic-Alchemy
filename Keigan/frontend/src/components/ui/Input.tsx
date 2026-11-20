import type { ComponentProps, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/utils/cn";
import { controlBoxClassName, describedByIds, FormField, useFormFieldIds, type FieldDecorationProps } from "./FormField";

export interface InputProps extends Omit<ComponentProps<"input">, "size">, FieldDecorationProps {
  size?: "sm" | "md";
  leadingIcon?: LucideIcon;
  /** Element inside the right edge (unit, button, kbd). */
  trailingContent?: ReactNode;
  containerClassName?: string;
}

/**
 * Text input with label, helper and error. Works with react-hook-form: `<Input {...register("name")} />`
 * (React 19 passes `ref` as a prop).
 */
export function Input({
  label,
  helperText,
  errorMessage,
  isOptional,
  labelAction,
  size = "md",
  leadingIcon: LeadingIcon,
  trailingContent,
  containerClassName,
  className,
  id,
  ...inputProps
}: InputProps) {
  const fieldIds = useFormFieldIds(id);
  const hasError = Boolean(errorMessage);
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
      <div className="relative flex items-center">
        {LeadingIcon ? (
          <LeadingIcon aria-hidden="true" size={18} strokeWidth={1.75} className="pointer-events-none absolute left-3 text-subtle" />
        ) : null}
        <input
          id={fieldIds.controlId}
          aria-invalid={hasError || undefined}
          aria-describedby={describedByIds(fieldIds, Boolean(helperText), hasError)}
          className={cn(controlBoxClassName(size), LeadingIcon && "pl-10", trailingContent ? "pr-11" : null, className)}
          {...inputProps}
        />
        {trailingContent ? <div className="absolute right-1.5 flex items-center">{trailingContent}</div> : null}
      </div>
    </FormField>
  );
}
