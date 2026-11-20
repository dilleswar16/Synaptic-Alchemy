import type { ReactNode } from "react";
import { Link } from "react-router";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";

export interface BreadcrumbItem {
  label: ReactNode;
  /** Omit for the current page. */
  to?: string;
}

export interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
  /** Right-aligned actions; at most one primary button. */
  actions?: ReactNode;
  /** Extra row under the description (filters, chips, tabs). */
  children?: ReactNode;
  className?: string;
}

/** Breadcrumb (caption, muted) → H1 → one-line description → right-aligned actions (doc 04 §3). */
export function PageHeader({ title, description, breadcrumbs, actions, children, className }: PageHeaderProps) {
  const { t } = useTranslation("navigation");
  return (
    <header className={cn("mb-6 flex flex-col gap-3", className)}>
      {breadcrumbs && breadcrumbs.length > 0 ? (
        <nav aria-label={t("breadcrumb")}>
          <ol className="flex flex-wrap items-center gap-1 text-caption text-muted">
            {breadcrumbs.map((item, itemIndex) => (
              <li key={itemIndex} className="inline-flex items-center gap-1">
                {itemIndex > 0 ? <ChevronRight aria-hidden="true" size={14} className="text-subtle" /> : null}
                {item.to ? (
                  <Link to={item.to} className="rounded-xs hover:text-action hover:underline">
                    {item.label}
                  </Link>
                ) : (
                  <span aria-current="page">{item.label}</span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h1 className="font-display text-h1 text-default">{title}</h1>
          {description ? <p className="mt-1 max-w-3xl text-body text-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </header>
  );
}
