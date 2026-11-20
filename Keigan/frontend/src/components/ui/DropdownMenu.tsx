import type { ReactElement, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Check } from "lucide-react";
import { DropdownMenu as RadixDropdownMenu } from "radix-ui";
import { cn } from "@/utils/cn";

export interface DropdownMenuActionItem {
  type?: "item";
  key: string;
  label: ReactNode;
  description?: ReactNode;
  icon?: LucideIcon;
  onSelect?: () => void;
  tone?: "default" | "danger";
  disabled?: boolean;
  /** Keyboard hint shown on the right, e.g. "Ctrl K". */
  shortcut?: string;
}

export interface DropdownMenuSeparatorItem {
  type: "separator";
  key: string;
}

export interface DropdownMenuLabelItem {
  type: "label";
  key: string;
  label: ReactNode;
}

export interface DropdownMenuRadioGroupItem {
  type: "radioGroup";
  key: string;
  value: string;
  onValueChange: (value: string) => void;
  options: Array<{ value: string; label: ReactNode; icon?: LucideIcon; lang?: string }>;
}

export type DropdownMenuEntry = DropdownMenuActionItem | DropdownMenuSeparatorItem | DropdownMenuLabelItem | DropdownMenuRadioGroupItem;

export interface DropdownMenuProps {
  trigger: ReactElement;
  entries: DropdownMenuEntry[];
  /** Content above the entries (e.g. the signed-in user card). */
  header?: ReactNode;
  align?: "start" | "center" | "end";
  side?: "top" | "right" | "bottom" | "left";
  className?: string;
}

const itemClassName =
  "relative flex cursor-pointer select-none items-center gap-2.5 rounded-sm px-2.5 py-2 text-body text-default outline-none data-[highlighted]:bg-surface-hover data-[disabled]:pointer-events-none data-[disabled]:opacity-50";

/** Action menu (Radix DropdownMenu) described by a typed `entries` array. */
export function DropdownMenu({ trigger, entries, header, align = "end", side = "bottom", className }: DropdownMenuProps) {
  return (
    <RadixDropdownMenu.Root>
      <RadixDropdownMenu.Trigger asChild>{trigger}</RadixDropdownMenu.Trigger>
      <RadixDropdownMenu.Portal>
        <RadixDropdownMenu.Content
          align={align}
          side={side}
          sideOffset={8}
          collisionPadding={12}
          className={cn(
            "z-[60] min-w-56 overflow-hidden rounded-md border border-hairline bg-surface p-1 shadow-lg",
            "origin-[var(--radix-dropdown-menu-content-transform-origin)] data-[state=closed]:animate-pop-out data-[state=open]:animate-pop-in",
            className,
          )}
        >
          {header ? <div className="-mx-1 -mt-1 mb-1 border-b border-hairline px-3.5 py-3">{header}</div> : null}
          {entries.map((entry) => {
            if (entry.type === "separator") {
              return <RadixDropdownMenu.Separator key={entry.key} className="-mx-1 my-1 h-px bg-hairline" />;
            }
            if (entry.type === "label") {
              return (
                <RadixDropdownMenu.Label key={entry.key} className="eyebrow px-2.5 pt-2 pb-1">
                  {entry.label}
                </RadixDropdownMenu.Label>
              );
            }
            if (entry.type === "radioGroup") {
              return (
                <RadixDropdownMenu.RadioGroup key={entry.key} value={entry.value} onValueChange={entry.onValueChange}>
                  {entry.options.map((option) => {
                    const OptionIcon = option.icon;
                    return (
                      <RadixDropdownMenu.RadioItem
                        key={option.value}
                        value={option.value}
                        lang={option.lang}
                        className={cn(itemClassName, "pr-9 data-[state=checked]:font-medium")}
                      >
                        {OptionIcon ? <OptionIcon aria-hidden="true" size={16} strokeWidth={1.75} className="text-muted" /> : null}
                        {option.label}
                        <RadixDropdownMenu.ItemIndicator className="absolute right-2.5 text-action">
                          <Check aria-hidden="true" size={16} strokeWidth={2.25} />
                        </RadixDropdownMenu.ItemIndicator>
                      </RadixDropdownMenu.RadioItem>
                    );
                  })}
                </RadixDropdownMenu.RadioGroup>
              );
            }
            const ItemIcon = entry.icon;
            return (
              <RadixDropdownMenu.Item
                key={entry.key}
                disabled={entry.disabled}
                onSelect={entry.onSelect}
                className={cn(itemClassName, entry.tone === "danger" && "text-danger data-[highlighted]:bg-danger-soft")}
              >
                {ItemIcon ? (
                  <ItemIcon
                    aria-hidden="true"
                    size={16}
                    strokeWidth={1.75}
                    className={cn("shrink-0", entry.tone === "danger" ? "text-danger" : "text-muted")}
                  />
                ) : null}
                <span className="min-w-0 flex-1">
                  <span className="block">{entry.label}</span>
                  {entry.description ? <span className="block text-caption text-muted">{entry.description}</span> : null}
                </span>
                {entry.shortcut ? <span className="ml-4 font-mono text-micro text-subtle">{entry.shortcut}</span> : null}
              </RadixDropdownMenu.Item>
            );
          })}
        </RadixDropdownMenu.Content>
      </RadixDropdownMenu.Portal>
    </RadixDropdownMenu.Root>
  );
}
