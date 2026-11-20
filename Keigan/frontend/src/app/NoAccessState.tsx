import { LogOut, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/authContext";
import { KeiganLogo } from "@/components/layout/KeiganLogo";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

/** Shown to signed-in users who belong to no application group: how to request access through SailPoint. */
export function NoAccessState() {
  const { t } = useTranslation("auth");
  const { t: translateNavigation } = useTranslation("navigation");
  const { user, signOut, refreshUser } = useAuth();
  const steps = [t("noAccess.stepFindCode"), t("noAccess.stepRequestGroup"), t("noAccess.stepSignInAgain")];
  return (
    <div className="grid min-h-dvh place-items-center bg-canvas bg-hero-wash p-6">
      <div className="flex w-full max-w-xl flex-col gap-6">
        <KeiganLogo showKanji />
        <Card radius="lg" accent className="flex flex-col gap-5">
          <div>
            <h1 className="font-display text-h2 text-default">{t("noAccess.title")}</h1>
            <p className="mt-2 text-body text-muted">{t("noAccess.description")}</p>
          </div>
          <dl className="grid gap-3 text-body-sm sm:grid-cols-2">
            <div className="rounded-sm bg-surface-sunken p-3">
              <dt className="font-mono text-caption font-medium text-default">CODE_reader</dt>
              <dd className="mt-1 text-muted">{t("noAccess.readerGroupDescription")}</dd>
            </div>
            <div className="rounded-sm bg-surface-sunken p-3">
              <dt className="font-mono text-caption font-medium text-default">CODE_admin</dt>
              <dd className="mt-1 text-muted">{t("noAccess.adminGroupDescription")}</dd>
            </div>
          </dl>
          <div>
            <h2 className="font-display text-h4 text-default">{t("noAccess.stepsTitle")}</h2>
            <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-body text-default">
              {steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-4">
            {user ? <span className="text-caption text-muted">{t("noAccess.signedInAs", { name: user.displayName })}</span> : <span />}
            <div className="flex gap-2">
              <Button variant="secondary" leadingIcon={LogOut} onClick={() => void signOut()}>
                {translateNavigation("userMenu.signOut")}
              </Button>
              <Button variant="primary" leadingIcon={RefreshCw} onClick={() => void refreshUser()}>
                {t("noAccess.checkAgain")}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
