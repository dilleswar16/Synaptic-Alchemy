import { useEffect, useState } from "react";
import { CheckCircle2, Plus, Radio, Send, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useCreateAlertSource, usePreviewAlertMapping, useRecentAlertEvents, useSendTestAlert, useUpdateAlertSource,
  type AlertSourceCreated, type AlertTool, type MappingPreview,
} from "@/api/alertsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { Drawer } from "@/components/ui/Drawer";
import { Input } from "@/components/ui/Input";
import { KeyValueList } from "@/components/ui/KeyValueList";
import { Select } from "@/components/ui/Select";
import { StatusChip } from "@/components/ui/StatusChip";
import { Switch } from "@/components/ui/Switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Textarea } from "@/components/ui/Textarea";

type SheetStep = "tool" | "endpoint" | "configure" | "mapping" | "services" | "test";
const canonicalFields = ["ruleName", "ruleId", "externalId", "status", "severity", "resourceRef", "serviceHint", "summary", "startedAt", "link"] as const;

export function AddAlertSourceSheet({ applicationId, open, onOpenChange, onFinished }: { applicationId: string; open: boolean; onOpenChange: (open: boolean) => void; onFinished?: () => void }) {
  const { t } = useTranslation("alerts");
  const [step, setStep] = useState<SheetStep>("tool");
  const [tool, setTool] = useState<AlertTool>("azure_monitor");
  const [sourceName, setSourceName] = useState("");
  const [created, setCreated] = useState<AlertSourceCreated | null>(null);
  const [samplePayloadText, setSamplePayloadText] = useState("");
  const [fieldMapping, setFieldMapping] = useState<Record<string, string>>({});
  const [severityRows, setSeverityRows] = useState<Array<{ value: string; severity: string }>>([{ value: "critical", severity: "0" }, { value: "warning", severity: "3" }]);
  const [serviceFieldPath, setServiceFieldPath] = useState("");
  const [autoMatch, setAutoMatch] = useState(true);
  const [preview, setPreview] = useState<MappingPreview | null>(null);
  const [isListening, setIsListening] = useState(false);

  const createSource = useCreateAlertSource(applicationId);
  const updateSource = useUpdateAlertSource(applicationId);
  const previewMapping = usePreviewAlertMapping(applicationId);
  const sendTest = useSendTestAlert(applicationId);
  const eventsQuery = useRecentAlertEvents(applicationId, created?.alertSource.alertSourceId ?? null, isListening);
  const latestParsedEvent = eventsQuery.data?.find((event) => event.parsedAlert);

  useEffect(() => {
    if (!open) {
      setStep("tool"); setTool("azure_monitor"); setSourceName(""); setCreated(null); setPreview(null); setIsListening(false); setSamplePayloadText(""); setFieldMapping({});
    }
  }, [open]);

  const severityMapping = () => Object.fromEntries(severityRows.filter((row) => row.value.trim()).map((row) => [row.value.trim(), Number(row.severity)]));
  const parseSample = (): Record<string, unknown> | null => {
    try { return samplePayloadText.trim() ? (JSON.parse(samplePayloadText) as Record<string, unknown>) : null; } catch { return null; }
  };
  const runPreview = () =>
    previewMapping.mutate({ sourceTool: tool, samplePayload: parseSample(), fieldMapping: Object.keys(fieldMapping).length ? fieldMapping : null, severityMapping: severityMapping(), serviceMapping: { field_path: serviceFieldPath || undefined, auto_match: autoMatch } }, {
      onSuccess: (result) => {
        setPreview(result);
        if (!Object.keys(fieldMapping).length) setFieldMapping(result.suggestedFieldMapping);
      },
    });
  const order: SheetStep[] = tool === "generic" ? ["tool", "endpoint", "configure", "mapping", "services", "test"] : tool === "elastic" ? ["tool", "endpoint", "configure", "services", "test"] : ["tool", "endpoint", "configure", "test"];
  const goNext = () => setStep(order[Math.min(order.indexOf(step) + 1, order.length - 1)] ?? "tool");
  const goBack = () => setStep(order[Math.max(order.indexOf(step) - 1, 0)] ?? "tool");
  const saveMappingsAndContinue = () => {
    if (!created) return;
    updateSource.mutate(
      { alertSourceId: created.alertSource.alertSourceId, body: { fieldMapping: Object.keys(fieldMapping).length ? fieldMapping : null, severityMapping: severityMapping(), serviceMapping: tool === "azure_monitor" ? null : { field_path: serviceFieldPath || undefined, auto_match: autoMatch } } },
      { onSuccess: goNext },
    );
  };

  const stepFooter = (
    <div className="flex w-full items-center justify-between">
      <Button variant="ghost" onClick={step === "tool" ? () => onOpenChange(false) : goBack}>{step === "tool" ? t("sheet.cancel") : t("sheet.back")}</Button>
      {step === "tool" ? (
        <Button isLoading={createSource.isPending} disabled={sourceName.trim().length < 2}
          onClick={() => createSource.mutate({ sourceTool: tool, sourceName }, { onSuccess: (result) => { setCreated(result); setStep("endpoint"); } })}>{t("sheet.createSource")}</Button>
      ) : step === "mapping" || step === "services" ? (
        <Button isLoading={updateSource.isPending} onClick={saveMappingsAndContinue}>{t("sheet.saveContinue")}</Button>
      ) : step === "test" ? (
        <Button onClick={() => { onFinished?.(); onOpenChange(false); }}>{t("sheet.done")}</Button>
      ) : (
        <Button onClick={goNext}>{t("sheet.next")}</Button>
      )}
    </div>
  );

  return (
    <Drawer open={open} onOpenChange={onOpenChange} size="lg" title={t("sheet.title")} description={t(`sheet.steps.${step}`)} footer={stepFooter}>
      {step === "tool" ? (
        <div className="flex flex-col gap-4">
          <Select<AlertTool> label={t("sheet.tool")} value={tool} onValueChange={setTool} options={[
            { value: "azure_monitor", label: t("tools.azure_monitor"), description: t("sheet.toolHelp.azure_monitor") },
            { value: "elastic", label: t("tools.elastic"), description: t("sheet.toolHelp.elastic") },
            { value: "generic", label: t("tools.generic"), description: t("sheet.toolHelp.generic") },
          ]} />
          <Input label={t("sheet.name")} value={sourceName} onChange={(event) => setSourceName(event.target.value)} placeholder={t("sheet.namePlaceholder")} />
        </div>
      ) : null}

      {step === "endpoint" && created ? (
        <div className="flex flex-col gap-4">
          <Banner tone="warning" title={t("sheet.secretOnceTitle")}>{t("sheet.secretOnceBody")}</Banner>
          <KeyValueList layout="stacked" isDivided items={[
            { key: "url", label: t("sheet.webhookUrl"), value: created.webhookUrl, copyValue: created.webhookUrl, isMonospace: true, helperText: t("sheet.webhookUrlHelp") },
            { key: "secret", label: t("sheet.secret"), value: created.webhookSecret, copyValue: created.webhookSecret, isMonospace: true, helperText: t("sheet.secretHelp") },
            { key: "header", label: t("sheet.header"), value: `X-Keigan-Token: ${created.webhookSecret}`, copyValue: `X-Keigan-Token: ${created.webhookSecret}`, isMonospace: true, helperText: t("sheet.headerHelp") },
          ]} />
        </div>
      ) : null}

      {step === "configure" && created ? (
        <Tabs defaultValue={created.setupInstructions.tabs[0]?.tabKey}>
          <TabsList>{created.setupInstructions.tabs.map((tab) => <TabsTrigger key={tab.tabKey} value={tab.tabKey}>{tab.tabTitle}</TabsTrigger>)}</TabsList>
          {created.setupInstructions.tabs.map((tab) => (
            <TabsContent key={tab.tabKey} value={tab.tabKey} className="flex flex-col gap-4 pt-4">
              <ol className="list-decimal space-y-1.5 pl-5 text-body-sm">{tab.steps.map((instruction) => <li key={instruction}>{instruction}</li>)}</ol>
              {tab.codeBlocks.map((block) => <CommandBlock key={block.title} title={block.title} commands={block.content} wrapLines />)}
            </TabsContent>
          ))}
        </Tabs>
      ) : null}

      {step === "mapping" ? (
        <div className="flex flex-col gap-4">
          <Textarea label={t("sheet.samplePayload")} helperText={t("sheet.samplePayloadHelp")} isMonospace rows={8} value={samplePayloadText} onChange={(event) => setSamplePayloadText(event.target.value)} />
          <div><Button variant="secondary" size="sm" isLoading={previewMapping.isPending} onClick={runPreview}>{t("sheet.suggestMapping")}</Button></div>
          {preview?.errorMessage ? <Banner tone="danger">{preview.errorMessage}</Banner> : null}
          <div className="grid gap-2">
            {canonicalFields.map((field) => (
              <div key={field} className="grid grid-cols-[10rem_1fr] items-center gap-3">
                <span className="text-body-sm font-semibold">{t(`sheet.fields.${field}`)}</span>
                <Input size="sm" aria-label={t(`sheet.fields.${field}`)} list={`paths-${field}`} value={fieldMapping[field] ?? ""} onChange={(event) => setFieldMapping({ ...fieldMapping, [field]: event.target.value })} placeholder="$.path.to.field" />
                <datalist id={`paths-${field}`}>{preview?.availablePaths.map((path) => <option key={path} value={path} />)}</datalist>
              </div>
            ))}
          </div>
          <div className="flex flex-col gap-2">
            <span className="text-body-sm font-semibold">{t("sheet.severityMapping")}</span>
            {severityRows.map((row, index) => (
              <div key={index} className="flex items-center gap-2">
                <Input size="sm" aria-label={t("sheet.toolValue")} value={row.value} onChange={(event) => setSeverityRows(severityRows.map((item, itemIndex) => (itemIndex === index ? { ...item, value: event.target.value } : item)))} />
                <Select size="sm" aria-label={t("sheet.severityLevel")} value={row.severity} onValueChange={(value) => setSeverityRows(severityRows.map((item, itemIndex) => (itemIndex === index ? { ...item, severity: value } : item)))}
                  options={["0", "1", "2", "3", "4"].map((level) => ({ value: level, label: t("severity", { level }) }))} />
                <Button variant="ghost" size="sm" aria-label={t("sheet.removeRow")} leadingIcon={Trash2} onClick={() => setSeverityRows(severityRows.filter((_, itemIndex) => itemIndex !== index))} />
              </div>
            ))}
            <div><Button variant="ghost" size="sm" leadingIcon={Plus} onClick={() => setSeverityRows([...severityRows, { value: "", severity: "3" }])}>{t("sheet.addRow")}</Button></div>
          </div>
          {preview?.parsedAlert ? <KeyValueList dense isDivided items={Object.entries(preview.parsedAlert).filter(([, value]) => value !== null && typeof value !== "object").map(([key, value]) => ({ key, label: key, value: String(value), isMonospace: true }))} /> : null}
        </div>
      ) : null}

      {step === "services" ? (
        <div className="flex flex-col gap-4">
          <p className="text-body-sm text-muted">{t("sheet.servicesHelp")}</p>
          <Input label={t("sheet.serviceField")} helperText={t("sheet.serviceFieldHelp")} value={serviceFieldPath} onChange={(event) => setServiceFieldPath(event.target.value)} placeholder="$.service.name" />
          <Switch label={t("sheet.autoMatch")} description={t("sheet.autoMatchHelp")} checked={autoMatch} onCheckedChange={setAutoMatch} />
        </div>
      ) : null}

      {step === "test" && created ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" leadingIcon={Send} isLoading={sendTest.isPending} onClick={() => { setIsListening(true); sendTest.mutate(created.alertSource.alertSourceId); }}>{t("sheet.sendTest")}</Button>
            <Button variant={isListening ? "primary" : "secondary"} leadingIcon={Radio} onClick={() => setIsListening(!isListening)}>{isListening ? t("sheet.stopListening") : t("sheet.listen")}</Button>
          </div>
          {latestParsedEvent ? (
            <div className="flex flex-col gap-3">
              <StatusChip tone="success" icon={CheckCircle2}>{t("sheet.connected")}</StatusChip>
              <KeyValueList isDivided dense items={[
                { key: "rule", label: t("sheet.fields.ruleName"), value: String(latestParsedEvent.parsedAlert?.ruleName ?? "") },
                { key: "severity", label: t("sheet.fields.severity"), value: t("severity", { level: latestParsedEvent.parsedAlert?.severity as number }) },
                { key: "service", label: t("sheet.matchedService"), value: latestParsedEvent.matchedServiceName ?? t("drawer.applicationLevel") },
                { key: "status", label: t("sheet.processing"), value: latestParsedEvent.processingStatus },
              ]} />
              <details><summary className="cursor-pointer text-body-sm font-semibold">{t("sheet.rawPayload")}</summary><pre className="mt-2 max-h-64 overflow-auto rounded-md bg-surface-sunken p-3 text-caption">{JSON.stringify(latestParsedEvent.rawPayload, null, 2)}</pre></details>
            </div>
          ) : <p className="text-body-sm text-muted">{isListening ? t("sheet.waiting") : t("sheet.testHelp")}</p>}
        </div>
      ) : null}
    </Drawer>
  );
}

