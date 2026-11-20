import { useState, type ReactNode } from "react";
import { Activity, Bell, Download, Gauge, Plus, Siren, Trash2 } from "lucide-react";
import { BarChart } from "@/components/charts/BarChart";
import { DonutChart } from "@/components/charts/DonutChart";
import { FunnelChart } from "@/components/charts/FunnelChart";
import { HeatmapGrid } from "@/components/charts/HeatmapGrid";
import { Sparkline } from "@/components/charts/Sparkline";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { KeiganLogo } from "@/components/layout/KeiganLogo";
import { PageHeader } from "@/components/layout/PageHeader";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { TopologyGraph } from "@/components/topology/TopologyGraph";
import { AiGeneratedChip } from "@/components/ui/AiGeneratedChip";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Banner } from "@/components/ui/Banner";
import { Button, type ButtonVariant } from "@/components/ui/Button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/Checkbox";
import { Combobox } from "@/components/ui/Combobox";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { CopyButton } from "@/components/ui/CopyButton";
import { CountWithInfo } from "@/components/ui/CountWithInfo";
import { DataTable } from "@/components/ui/DataTable";
import { Dialog } from "@/components/ui/Dialog";
import { Drawer } from "@/components/ui/Drawer";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { EvidenceChip } from "@/components/ui/EvidenceChip";
import { FileDrop } from "@/components/ui/FileDrop";
import { IconButton } from "@/components/ui/IconButton";
import { Input } from "@/components/ui/Input";
import { Kbd } from "@/components/ui/Kbd";
import { KeyValueList } from "@/components/ui/KeyValueList";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { Popover } from "@/components/ui/Popover";
import { PriorityChip } from "@/components/ui/PriorityChip";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { RadioGroup } from "@/components/ui/RadioGroup";
import { ReadinessBar } from "@/components/ui/ReadinessBar";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { SaveIndicator } from "@/components/ui/SaveIndicator";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { Skeleton, SkeletonText } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { StatTile } from "@/components/ui/StatTile";
import { StatusChip } from "@/components/ui/StatusChip";
import { Stepper } from "@/components/ui/Stepper";
import { Switch } from "@/components/ui/Switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Textarea } from "@/components/ui/Textarea";
import { Timeline } from "@/components/ui/Timeline";
import { useToast } from "@/components/ui/Toast";
import { TokenInput } from "@/components/ui/TokenInput";
import { Tooltip } from "@/components/ui/Tooltip";
import { statusTones } from "@/components/ui/toneStyles";

/**
 * Developer-only showcase (`/design-system`, local and dev environments): every UI-kit component in its main
 * variants. Switch the theme with the toggle to review both. Copy here is intentionally English-only.
 */

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-10" aria-label={title}>
      <SectionHeader title={title} className="mb-4" />
      <div className="flex flex-col gap-6">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      {label ? <p className="text-caption font-medium text-muted">{label}</p> : null}
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  );
}

const buttonVariants: ButtonVariant[] = ["primary", "secondary", "subtle", "ghost", "danger", "gradient-outline"];
const chartDays = Array.from({ length: 14 }, (_, dayIndex) => `Nov ${dayIndex + 1}`);
const sloSeries = chartDays.map((day, dayIndex) => ({ time: day, availability: 99.6 + Math.sin(dayIndex / 2) * 0.25 + (dayIndex === 9 ? -0.6 : 0), budget: 60 - dayIndex * 2.5 }));
const tokensSeries = chartDays.slice(0, 7).map((day, dayIndex) => ({ category: day, rca: 40 + dayIndex * 6, chat: 25 + (dayIndex % 3) * 9, comms: 12 + dayIndex * 2 }));

export default function DesignSystemShowcasePage() {
  const { showToast } = useToast();
  const [segment, setSegment] = useState<"table" | "board">("table");
  const [selectedOption, setSelectedOption] = useState("claims");
  const [comboboxValue, setComboboxValue] = useState<string | null>(null);
  const [tokens, setTokens] = useState(["checkout", "claims-api"]);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [radioValue, setRadioValue] = useState("a");

  return (
    <>
      <PageHeader
        title="Design system"
        description="Every Keigan UI component in its main variants. Use the theme toggle to review light and dark."
        actions={<ThemeToggle />}
      />

      <Section title="Brand">
        <Row>
          <KeiganLogo showKanji size={40} />
          <KeiganLogo variant="mark" size={32} />
          <KeiganLogo variant="mark" size={16} />
          <span className="rounded-md bg-gradient-brand p-4">
            <KeiganLogo tone="inverse" showKanji />
          </span>
        </Row>
      </Section>

      <Section title="Buttons">
        {(["sm", "md", "lg"] as const).map((size) => (
          <Row key={size} label={`Size ${size}`}>
            {buttonVariants.map((variant) => (
              <Button key={variant} variant={variant} size={size} leadingIcon={Plus}>
                {variant}
              </Button>
            ))}
          </Row>
        ))}
        <Row label="States">
          <Button isLoading>Loading</Button>
          <Button disabled>Disabled</Button>
          <Button variant="secondary" trailingIcon={Download}>
            Trailing icon
          </Button>
          <IconButton icon={Bell} label="Notifications" />
          <IconButton icon={Trash2} label="Delete" variant="secondary" />
          <IconButton icon={Plus} label="Add" variant="primary" />
          <CopyButton value="keigan" showLabel />
        </Row>
      </Section>

      <Section title="Chips, badges and status">
        <Row label="Status tones">
          {statusTones.map((tone) => (
            <StatusChip key={tone} tone={tone}>
              {tone}
            </StatusChip>
          ))}
          <StatusChip tone="info" dot pulse>
            Investigating
          </StatusChip>
          <StatusChip tone="success" variant="outline">
            Supporting
          </StatusChip>
        </Row>
        <Row label="Badges">
          {statusTones.map((tone) => (
            <Badge key={tone} tone={tone}>
              {tone}
            </Badge>
          ))}
        </Row>
        <Row label="Priority">
          {(["P1", "P2", "P3", "P4"] as const).map((priority) => (
            <PriorityChip key={priority} priority={priority} />
          ))}
        </Row>
        <Row label="AI and evidence">
          <AiGeneratedChip modelName="claude" generatedAt={new Date(Date.now() - 120_000)} />
          <EvidenceChip code="E3" title="Error spike in claims-api" relation="supporting" />
          <EvidenceChip code="E7" title="Unrelated deploy" relation="contradicting" />
          <EvidenceChip code="E9" />
          <Avatar name="Aiko AppAdmin" size="sm" />
          <Avatar name="Kai Admin" />
          <Avatar name="Rui Reader" size="lg" />
          <Kbd>Ctrl</Kbd>
          <Kbd>K</Kbd>
          <RelativeTime value={new Date(Date.now() - 12 * 60_000)} />
        </Row>
      </Section>

      <Section title="Cards and tiles">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatTile icon={Siren} iconTone="danger" label="Open incidents" value="7" secondaryText="+2 since yesterday" secondaryTone="negative" to="/incidents" />
          <StatTile icon={Gauge} iconTone="success" label="SLO compliance" value="99.94%" secondaryText="Above target" secondaryTone="positive" trend={<Sparkline values={[3, 4, 3, 5, 6, 5, 7]} />} />
          <StatTile icon={Activity} iconTone="info" label="Alerts grouped" value="1,284" />
          <StatTile icon={Bell} iconTone="alert" label="Noise reduced" value="82%" />
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader title="Card header" description="Supporting description" icon={Activity} actions={<Button size="sm" variant="subtle">Action</Button>} />
            <CardBody>Body content sits here.</CardBody>
            <CardFooter>Footer</CardFooter>
          </Card>
          <Card interactive>
            <CardHeader title="Interactive card" description="Hover lifts it" />
          </Card>
          <Card accent radius="lg">
            <CardHeader title="Accent card" description="3 px gradient stripe" />
          </Card>
        </div>
      </Section>

      <Section title="Form controls">
        <div className="grid gap-5 md:grid-cols-2">
          <Input label="Application name" placeholder="Claims Processing (JP)" helperText="Shown across Keigan" />
          <Input label="Code" defaultValue="CLM" errorMessage="Code must be 3 to 8 letters" />
          <Select label="Region" value={selectedOption} onValueChange={setSelectedOption} options={[{ value: "claims", label: "Claims" }, { value: "payments", label: "Payments" }]} />
          <Combobox label="Service" value={comboboxValue} onValueChange={setComboboxValue} options={[{ value: "a", label: "claims-api" }, { value: "b", label: "payments-api" }]} isClearable />
          <TokenInput label="Services" value={tokens} onValueChange={setTokens} placeholder="Type and press Enter" />
          <Textarea label="Notes" placeholder="Markdown supported" autoResize />
          <RadioGroup label="Choice" value={radioValue} onValueChange={setRadioValue} options={[{ value: "a", label: "Option A" }, { value: "b", label: "Option B", description: "With description" }]} />
          <div className="flex flex-col gap-3">
            <Checkbox label="Checkbox" defaultChecked />
            <Checkbox label="Indeterminate" checked="indeterminate" />
            <Switch label="Switch" defaultChecked />
            <SegmentedControl aria-label="View" value={segment} onValueChange={setSegment} options={[{ value: "table", label: "Table" }, { value: "board", label: "Board" }]} />
          </div>
        </div>
        <FileDrop acceptedTypesLabel="PDF, Markdown" onFilesSelected={() => undefined} items={[{ key: "1", fileName: "runbook.md", fileSizeBytes: 20480, status: "uploading", progressPercentage: 60 }]} />
        <Row>
          <SaveIndicator status="saving" />
          <SaveIndicator status="saved" savedAt={new Date()} />
          <SaveIndicator status="error" onRetry={() => undefined} />
        </Row>
      </Section>

      <Section title="Feedback">
        <Banner tone="info" title="Info">Keigan suggests; people decide.</Banner>
        <Banner tone="warning" title="Local mode — not for production">These are test users.</Banner>
        <Banner tone="danger" title="Something failed">Try again in a moment.</Banner>
        <Banner tone="success">Saved.</Banner>
        <Row>
          <Button variant="secondary" onClick={() => showToast({ tone: "success", title: "Saved", description: "Your changes are saved." })}>Show toast</Button>
          <Spinner label="Loading" />
          <Skeleton className="h-6 w-40" />
          <SkeletonText lineCount={2} />
        </Row>
        <div className="grid gap-4 md:grid-cols-2">
          <EmptyState isBordered title="Nothing here yet" description="Add your first component to get started." action={<Button leadingIcon={Plus}>Add component</Button>} />
          <ErrorState error={new Error("Network down")} onRetry={() => undefined} />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <ProgressBar value={62} label="Readiness" showValue />
          <ReadinessBar completedRequiredCount={6} requiredCount={8} nextStepLabel="Add SLOs" onSeeAll={() => undefined} />
          <ConfidenceMeter percentage={82} />
          <CountWithInfo count={27} label="available" title="Top services" items={[{ key: "1", label: "claims-api", secondary: "12" }, { key: "2", label: "payments-api", secondary: "9" }]} />
        </div>
      </Section>

      <Section title="Overlays and menus">
        <Row>
          <Tooltip content="Tooltip text">
            <Button variant="secondary">Tooltip</Button>
          </Tooltip>
          <Popover trigger={<Button variant="secondary">Popover</Button>}>Popover content</Popover>
          <DropdownMenu trigger={<Button variant="secondary">Menu</Button>} entries={[{ key: "edit", label: "Edit" }, { key: "sep", type: "separator" }, { key: "delete", label: "Delete", tone: "danger", icon: Trash2 }]} />
          <Dialog trigger={<Button variant="secondary">Dialog</Button>} title="Dialog title" description="Focus is trapped; Esc closes.">Dialog body</Dialog>
          <Button variant="secondary" onClick={() => setIsDrawerOpen(true)}>Drawer</Button>
          <Button variant="danger" onClick={() => setIsConfirmOpen(true)}>Confirm dialog</Button>
        </Row>
        <Drawer open={isDrawerOpen} onOpenChange={setIsDrawerOpen} title="Drawer title" description="Sticky header and footer" footer={<Button onClick={() => setIsDrawerOpen(false)}>Done</Button>}>
          Drawer body
        </Drawer>
        <ConfirmDialog open={isConfirmOpen} onOpenChange={setIsConfirmOpen} title="Delete application?" description="This cannot be undone." confirmLabel="Delete application" tone="danger" onConfirm={() => undefined} />
      </Section>

      <Section title="Navigation and content">
        <Tabs defaultValue="rca">
          <TabsList>
            <TabsTrigger value="rca">RCA</TabsTrigger>
            <TabsTrigger value="evidence" count={4}>Evidence</TabsTrigger>
            <TabsTrigger value="timeline">Timeline</TabsTrigger>
          </TabsList>
          <TabsContent value="rca" className="pt-4">RCA content</TabsContent>
          <TabsContent value="evidence" className="pt-4">Evidence content</TabsContent>
          <TabsContent value="timeline" className="pt-4">Timeline content</TabsContent>
        </Tabs>
        <div className="grid gap-6 lg:grid-cols-2">
          <Stepper
            aria-label="Onboarding"
            currentStepKey="services"
            stages={[
              { key: "setup", label: "Set up", steps: [{ key: "components", label: "Components", status: "done" }, { key: "services", label: "Services", status: "in_progress" }] },
              { key: "connect", label: "Connect", steps: [{ key: "tools", label: "Tools", status: "waiting" }, { key: "knowledge", label: "Knowledge", status: "blocked" }, { key: "slos", label: "SLOs", status: "not_started" }] },
            ]}
          />
          <Timeline
            events={[
              { key: "1", timestamp: new Date(Date.now() - 3_600_000), title: "Alert fired", tone: "danger", icon: Bell },
              { key: "2", timestamp: new Date(Date.now() - 1_800_000), title: "Investigation started", tone: "info" },
              { key: "3", timestamp: new Date(Date.now() - 600_000), title: "Fix proposed", tone: "success", description: "Roll back deploy 4821" },
            ]}
          />
        </div>
        <KeyValueList items={[{ key: "a", label: "Environment", value: "Local" }, { key: "b", label: "Token", value: "kg_live_123", copyValue: "kg_live_123", isMonospace: true }]} />
        <CommandBlock
          title="Roll back"
          riskLevel="medium"
          commands={[{ key: "cli", label: "CLI", content: "az aks rollout undo deployment/claims-api" }, { key: "ps", label: "PowerShell", content: "kubectl rollout undo deployment/claims-api" }]}
        />
        <MarkdownView content={"### Summary\n\nThe **claims-api** pods restarted after a bad deploy.\n\n| Metric | Value |\n|---|---|\n| Errors | 312 |\n\n- Roll back\n- Verify"} />
        <DataTable
          caption="Example incidents"
          rows={[{ id: "1", number: "INC0001", title: "Claims API 5xx", priority: "P1" as const }, { id: "2", number: "INC0002", title: "Slow search", priority: "P3" as const }]}
          getRowId={(row) => row.id}
          columns={[
            { key: "priority", header: "Priority", cell: (row) => <PriorityChip priority={row.priority} />, sortValue: (row) => row.priority },
            { key: "number", header: "Number", cell: (row) => <span className="font-mono">{row.number}</span>, sortValue: (row) => row.number },
            { key: "title", header: "Title", cell: (row) => row.title },
          ]}
        />
      </Section>

      <Section title="Charts">
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Availability" description="With target line and anomaly" />
            <TimeSeriesChart
              ariaLabel="Availability over 14 days"
              data={sloSeries}
              series={[{ key: "availability", label: "Availability" }]}
              targetValue={99.5}
              anomalies={[{ x: "Nov 10", y: sloSeries[9]?.availability ?? 99 }]}
              valueFormatter={(value) => `${value.toFixed(2)}%`}
            />
          </Card>
          <Card>
            <CardHeader title="Tokens by feature" description="Stacked bars" />
            <BarChart ariaLabel="Tokens by feature" data={tokensSeries} stacked series={[{ key: "rca", label: "RCA" }, { key: "chat", label: "Chat" }, { key: "comms", label: "Comms" }]} />
          </Card>
          <Card>
            <CardHeader title="Error budget" description="Donut" />
            <DonutChart ariaLabel="Error budget" centerValue="62%" centerLabel="remaining" slices={[{ key: "left", label: "Remaining", value: 62, color: "success" }, { key: "used", label: "Used", value: 38, color: "warning" }]} />
          </Card>
          <Card>
            <CardHeader title="Alert funnel" description="Funnel" />
            <FunnelChart ariaLabel="Alert funnel" stages={[{ key: "raw", label: "Raw alerts", count: 1284 }, { key: "dedup", label: "Deduplicated", count: 420 }, { key: "groups", label: "Groups", count: 96 }, { key: "incidents", label: "Incidents", count: 12 }]} />
          </Card>
        </div>
        <Card>
          <CardHeader title="Compliance heatmap" description="Applications by day" />
          <HeatmapGrid
            ariaLabel="Compliance by application"
            minimumValue={98}
            maximumValue={100}
            rows={[{ key: "clm", label: "Claims" }, { key: "pay", label: "Payments" }, { key: "chn", label: "Channels" }]}
            columns={chartDays.slice(0, 10).map((day) => ({ key: day, label: day.replace("Nov ", "") }))}
            getValue={(rowKey, columnKey) => 98.5 + ((rowKey.length * 7 + columnKey.length * 3 + columnKey.charCodeAt(columnKey.length - 1)) % 15) / 10}
          />
        </Card>
        <Card>
          <CardHeader title="Topology" description="Impacted paths animate" />
          <TopologyGraph
            height={360}
            nodes={[
              { key: "gateway", name: "api-gateway", type: "api_management" },
              { key: "claims", name: "claims-api", type: "aks" },
              { key: "payments", name: "payments-api", type: "app_service" },
              { key: "db", name: "claims-db", type: "database" },
              { key: "queue", name: "events-queue", type: "queue" },
            ]}
            edges={[
              { source: "gateway", target: "claims" },
              { source: "gateway", target: "payments" },
              { source: "claims", target: "db" },
              { source: "claims", target: "queue" },
            ]}
            highlightedNodeKeys={{ claims: "direct", db: "indirect" }}
          />
        </Card>
      </Section>
    </>
  );
}
