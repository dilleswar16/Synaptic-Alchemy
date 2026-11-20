import { Link } from "react-router";
import { FileQuestionMark } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";

export default function NotFoundPage() {
  const { t } = useTranslation("navigation");
  return (
    <EmptyState
      icon={FileQuestionMark}
      size="lg"
      title={t("notFound.title")}
      description={t("notFound.description")}
      action={
        <Button asChild>
          <Link to="/">{t("notFound.goHome")}</Link>
        </Button>
      }
    />
  );
}
