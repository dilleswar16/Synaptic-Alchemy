import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "@/api/httpClient";
import type { AcceptedJob, Identifier, IsoDateTimeString } from "@/api/types/common";

/* ── Types (doc 05 §4) ──────────────────────────────────────────────────────── */
export type LifecycleStatus = "requested" | "draft" | "onboarding" | "live" | "paused";
export type CriticalityTier = "tier_1" | "tier_2" | "tier_3";
export type EnvironmentName = "dev" | "test" | "uat" | "prod";
export type ComponentType = "azure_resource_group" | "hardware" | "mainframe" | "saas_platform";
export type StepKey =
  | "components" | "services" | "log_tools" | "knowledge" | "topology" | "runbooks" | "incidents" | "slo" | "notifications" | "access" | "review";
export type StepStatusValue = "not_started" | "in_progress" | "waiting" | "blocked" | "done";

export interface IncidentCreationPolicy {
  mode: "suggest" | "automatic";
  minimumScore: number;
  assignmentGroupName: string | null;
}

export interface Application {
  applicationId: Identifier;
  applicationName: string;
  applicationCode: string;
  applicationDescription: string | null;
  businessUnitName: string | null;
  regionCode: string | null;
  primaryLocale: string;
  timeZoneName: string;
  criticalityTier: CriticalityTier;
  lifecycleStatus: LifecycleStatus;
  adminGroupName: string;
  readerGroupName: string;
  incidentCreationPolicy: IncidentCreationPolicy | null;
  onboardingProgress: Record<string, unknown> | null;
  wentLiveAt: IsoDateTimeString | null;
  createdAt: IsoDateTimeString;
  updatedAt: IsoDateTimeString;
  canEdit: boolean;
}

export interface ApplicationSummary extends Application {
  componentTypes: ComponentType[];
  componentCount: number;
  serviceCount: number;
  openIncidentCount: number;
  sloCompliancePercentage: number | null;
  requiredDoneCount: number | null;
  requiredTotalCount: number | null;
}

export interface CreateApplicationBody {
  applicationName: string;
  applicationCode: string;
  applicationDescription?: string;
  businessUnitName?: string;
  regionCode?: string;
  primaryLocale?: string;
  criticalityTier: CriticalityTier;
}

export interface Requirement {
  requirementKey: string;
  stepKey: StepKey;
  isDone: boolean;
  detail: string | null;
  count: number | null;
}
export interface StepStatusEntry {
  stepKey: StepKey;
  status: StepStatusValue;
  summary: string | null;
}
export interface Readiness {
  required: Requirement[];
  goodToKnow: Requirement[];
  canGoLive: boolean;
  steps: StepStatusEntry[];
  nextStepKey: StepKey | null;
}

export interface AccessInformation {
  adminGroupName: string;
  adminGroupObjectId: string | null;
  readerGroupName: string;
  readerGroupObjectId: string | null;
  membersAvailable: boolean;
  adminMembers: string[];
  readerMembers: string[];
  sailpointInstructions: string;
  canEditGroupNames: boolean;
}

export interface PlatformIdentity {
  tenantId: string | null;
  clientId: string | null;
  objectId: string | null;
  displayName: string | null;
  multiTenantClientId: string | null;
  isSimulated: boolean;
  /** False when Keigan could not determine every ID (shown as a warning instead of placeholder values). */
  isComplete: boolean;
  missingValues: string[];
  identitySource: "settings" | "discovered" | "not_configured";
}

export interface GroupVerificationResult {
  role: "admin" | "reader";
  groupName: string;
  /** null = Keigan could not check (for example the Graph permission is missing). */
  exists: boolean | null;
  objectId: string | null;
  memberCount: number | null;
  sampleMemberNames: string[];
  objectIdSaved: boolean;
  message: string;
}

export interface AccessVerification {
  results: GroupVerificationResult[];
  checkedAt: IsoDateTimeString;
  directory: "entra" | "local_demo_users";
}

export interface AccessCheck {
  checkName: string;
  passed: boolean;
  message: string;
  missingRoleName: string | null;
}
export interface DiscoverySummary {
  resourcesFound: number;
  monitoredServices: number;
  telemetrySources: number;
  withoutDiagnosticSetting: number;
  noLongerFound: number;
  servicesCreated: number;
  servicesUpdated: number;
  resourcesByType: Record<string, number>;
}
export interface ApplicationComponent {
  componentId: Identifier;
  applicationId: Identifier;
  componentType: ComponentType;
  componentName: string;
  environmentName: EnvironmentName;
  azureTenantId: string | null;
  azureSubscriptionId: string | null;
  azureSubscriptionName: string | null;
  azureResourceGroupName: string | null;
  componentConfiguration: Record<string, unknown> | null;
  accessVerificationStatus: "not_checked" | "checking" | "verified" | "missing_roles" | "failed" | "not_applicable";
  accessVerificationDetails: AccessCheck[] | null;
  lastVerifiedAt: IsoDateTimeString | null;
  lastDiscoveredAt: IsoDateTimeString | null;
  discoverySummary: DiscoverySummary | null;
  serviceCount: number;
  isSimulated: boolean;
}
export interface CreateComponentBody {
  componentType: ComponentType;
  componentName: string;
  environmentName: EnvironmentName;
  azureTenantId?: string;
  azureSubscriptionId?: string;
  azureSubscriptionName?: string;
  azureResourceGroupName?: string;
  componentConfiguration?: Record<string, unknown>;
}
export interface RoleCommands {
  cli: string;
  powershell: string;
  terraform: string;
  portalSteps: string[];
  requiredRoles: { roleName: string; purpose: string }[];
  tenantNote: string | null;
}
export interface DiscoveredResource {
  discoveredResourceId: Identifier;
  componentId: Identifier;
  azureResourceId: string;
  resourceName: string;
  resourceType: string;
  resourceTypeDisplayName: string;
  resourceKind: string | null;
  locationName: string | null;
  monitoringClassification: "monitored_service" | "telemetry_source" | "not_monitored_type";
  hasDiagnosticSetting: boolean;
  lastSeenAt: IsoDateTimeString;
  noLongerFoundAt: IsoDateTimeString | null;
  serviceId: Identifier | null;
}

export type LogSourceKind = "log_analytics" | "application_insights" | "azure_monitor_metrics" | "log_tool" | "synthetic_probe" | "vendor_status_page";
export interface LogSourceInput {
  sourceKind: LogSourceKind;
  logToolConnectionId?: string | null;
  logAnalyticsWorkspaceResourceId?: string | null;
  logAnalyticsWorkspaceCustomerId?: string | null;
  queryScope?: Record<string, unknown> | null;
  isPrimarySource: boolean;
}
export interface LogSource extends Required<Omit<LogSourceInput, "queryScope">> {
  serviceLogSourceId: Identifier;
  serviceId: Identifier;
  logToolConnectionName: string | null;
  queryScope: Record<string, unknown> | null;
  wasAutoDetected: boolean;
  lastReadTestStatus: "not_tested" | "passed" | "failed";
  lastReadTestAt: IsoDateTimeString | null;
}
export interface MetricDefinition {
  name: string;
  displayName: string;
  unit: string | null;
  primaryAggregationType: string | null;
}
export interface MonitoredServiceRow {
  serviceId: Identifier;
  applicationId: Identifier;
  componentId: Identifier | null;
  componentName: string | null;
  componentType: ComponentType | null;
  serviceName: string;
  serviceType: string;
  externalResourceIdentifier: string | null;
  environmentName: EnvironmentName;
  criticalityTier: CriticalityTier;
  isMonitoringEnabled: boolean;
  aksNamespaceFilter: string | null;
  applicationInsightsRoleName: string | null;
  availableMetricCount: number;
  availableMetrics: MetricDefinition[] | null;
  repositoryProvider: string | null;
  repositoryUrl: string | null;
  repositoryDefaultBranch: string | null;
  repositoryPath: string | null;
  repositoryCredentialConfigured: boolean;
  serviceDescription: string | null;
  logSources: LogSource[];
  hasDiagnosticSetting: boolean | null;
  noLongerFoundAt: IsoDateTimeString | null;
  dependsOnServiceIds: Identifier[];
}
export interface ServiceUpdateBody {
  serviceName?: string;
  environmentName?: EnvironmentName;
  criticalityTier?: CriticalityTier;
  isMonitoringEnabled?: boolean;
  aksNamespaceFilter?: string | null;
  repositoryProvider?: string | null;
  repositoryUrl?: string | null;
  repositoryDefaultBranch?: string | null;
  repositoryPath?: string | null;
  serviceDescription?: string | null;
}
export interface CreateServiceBody {
  serviceName: string;
  serviceType: string;
  componentId?: string | null;
  environmentName: EnvironmentName;
  criticalityTier: CriticalityTier;
  aksNamespaceFilter?: string | null;
}
export interface ServiceBulkChanges {
  environmentName?: EnvironmentName;
  criticalityTier?: CriticalityTier;
  isMonitoringEnabled?: boolean;
  addLogSource?: LogSourceInput;
}
export interface ServiceDependency {
  serviceDependencyId: Identifier;
  upstreamServiceId: Identifier;
  downstreamServiceId: Identifier;
  dependencyKind: string;
  dependencySource: string;
}
export interface DiagnosticSettingCommand {
  hasDiagnosticSetting: boolean;
  cliCommand: string;
  powershellCommand: string;
  explanation: string;
}
export interface TestResult {
  succeeded: boolean;
  message: string;
  newestLogTimestamp: IsoDateTimeString | null;
  readerNotAvailable?: boolean;
}

export type LogToolType = "elastic" | "splunk" | "datadog" | "solarwinds" | "ibm_z_log_analytics" | "vendor_api" | "other";
export interface LogToolConnection {
  logToolConnectionId: Identifier;
  applicationId: Identifier;
  toolType: LogToolType;
  connectionName: string;
  endpointUrl: string | null;
  authenticationMethod: string;
  connectionConfiguration: Record<string, unknown> | null;
  hasCredential: boolean;
  credentialSetAt: IsoDateTimeString | null;
  connectionStatus: "not_tested" | "connected" | "failed" | "reader_not_available";
  lastTestedAt: IsoDateTimeString | null;
  lastTestMessage: string | null;
  newestLogTimestampSeenAt: IsoDateTimeString | null;
  readerAvailable: boolean;
  usedByServiceNames: string[];
}
export interface LogToolConnectionBody {
  toolType?: LogToolType;
  connectionName?: string;
  endpointUrl?: string | null;
  authenticationMethod?: string;
  connectionConfiguration?: Record<string, unknown>;
  credentialValue?: string;
}

export interface IntegrationField {
  key: string;
  label: string;
  fieldType: "text" | "url" | "select" | "secret" | "key_value_list" | "textarea";
  required?: boolean;
  placeholder?: string;
  helpText?: string;
  defaultValue?: string;
  options?: [string, string][];
}
export interface Integration {
  integrationKind: string;
  displayName: string;
  purpose: string;
  readerAvailable: boolean;
  fields: IntegrationField[];
  integrationConfiguration: Record<string, unknown>;
  hasCredential: boolean;
  integrationStatus: string;
  integrationNotes: string | null;
}
export interface RecordLink {
  applicationRecordLinkId: Identifier;
  recordSystem: "eai" | "cmdb";
  recordIdentifier: string;
  linkStatus: string;
  createdAt: IsoDateTimeString;
}
export interface ServiceNowGroup {
  assignmentGroupId: Identifier;
  groupName: string;
  verificationStatus: "verified" | "unverified";
}
export interface ServiceNowGroupSearchResult {
  groupName: string;
  isVerified: boolean;
}

/* ── Query keys ─────────────────────────────────────────────────────────────── */
export const applicationQueryKeys = {
  all: ["applications"] as const,
  list: () => ["applications", "list"] as const,
  detail: (applicationId: string) => ["applications", applicationId, "detail"] as const,
  readiness: (applicationId: string) => ["applications", applicationId, "readiness"] as const,
  access: (applicationId: string) => ["applications", applicationId, "access"] as const,
  components: (applicationId: string) => ["applications", applicationId, "components"] as const,
  resources: (applicationId: string, componentId: string) => ["applications", applicationId, "resources", componentId] as const,
  services: (applicationId: string) => ["applications", applicationId, "services"] as const,
  dependencies: (applicationId: string) => ["applications", applicationId, "dependencies"] as const,
  logTools: (applicationId: string) => ["applications", applicationId, "log-tools"] as const,
  integrations: (applicationId: string) => ["applications", applicationId, "integrations"] as const,
  recordLinks: (applicationId: string) => ["applications", applicationId, "record-links"] as const,
  servicenowGroups: (applicationId: string) => ["applications", applicationId, "servicenow-groups"] as const,
  platformIdentity: ["platform", "identity"] as const,
};

const applicationPath = (applicationId: string) => `/applications/${applicationId}`;

/* ── Queries ────────────────────────────────────────────────────────────────── */
export const useApplications = () => useQuery({ queryKey: applicationQueryKeys.list(), queryFn: () => apiGet<ApplicationSummary[]>("/applications") });
export const useApplication = (applicationId: string) =>
  useQuery({ queryKey: applicationQueryKeys.detail(applicationId), queryFn: () => apiGet<Application>(applicationPath(applicationId)) });
export const useReadiness = (applicationId: string) =>
  useQuery({ queryKey: applicationQueryKeys.readiness(applicationId), queryFn: () => apiGet<Readiness>(`${applicationPath(applicationId)}/readiness`) });
export const useAccessInformation = (applicationId: string) =>
  useQuery({ queryKey: applicationQueryKeys.access(applicationId), queryFn: () => apiGet<AccessInformation>(`${applicationPath(applicationId)}/access`) });
export const usePlatformIdentity = () => useQuery({ queryKey: applicationQueryKeys.platformIdentity, queryFn: () => apiGet<PlatformIdentity>("/platform/identity"), staleTime: 5 * 60_000 });

/** Components that are being verified poll with back-off (5, 10, 20, then every 30 s) so the step shows live progress. */
export function useComponents(applicationId: string) {
  return useQuery({
    queryKey: applicationQueryKeys.components(applicationId),
    queryFn: () => apiGet<ApplicationComponent[]>(`${applicationPath(applicationId)}/components`),
    refetchInterval: (query) => (query.state.data?.some((component) => component.accessVerificationStatus === "checking") ? 4000 : false),
  });
}
export const useDiscoveredResources = (applicationId: string, componentId: string, isEnabled: boolean) =>
  useQuery({
    queryKey: applicationQueryKeys.resources(applicationId, componentId),
    queryFn: () => apiGet<DiscoveredResource[]>(`${applicationPath(applicationId)}/components/${componentId}/resources`),
    enabled: isEnabled,
  });
export const useRoleCommands = (applicationId: string, componentId: string, isEnabled: boolean) =>
  useQuery({
    queryKey: ["applications", applicationId, "role-commands", componentId],
    queryFn: () => apiGet<RoleCommands>(`${applicationPath(applicationId)}/components/${componentId}/role-commands`),
    enabled: isEnabled,
  });
export const useServices = (applicationId: string) =>
  useQuery({ queryKey: applicationQueryKeys.services(applicationId), queryFn: () => apiGet<MonitoredServiceRow[]>(`${applicationPath(applicationId)}/services`) });
export const useServiceDependencies = (applicationId: string) =>
  useQuery({ queryKey: applicationQueryKeys.dependencies(applicationId), queryFn: () => apiGet<ServiceDependency[]>(`${applicationPath(applicationId)}/service-dependencies`) });
export const useLogToolConnections = (applicationId: string) =>
  useQuery({ queryKey: applicationQueryKeys.logTools(applicationId), queryFn: () => apiGet<LogToolConnection[]>(`${applicationPath(applicationId)}/log-tool-connections`) });
export const useIntegrations = (applicationId: string) =>
  useQuery({ queryKey: applicationQueryKeys.integrations(applicationId), queryFn: () => apiGet<Integration[]>(`${applicationPath(applicationId)}/integrations`) });
export const useRecordLinks = (applicationId: string) =>
  useQuery({ queryKey: applicationQueryKeys.recordLinks(applicationId), queryFn: () => apiGet<RecordLink[]>(`${applicationPath(applicationId)}/record-links`) });
export const useServiceNowGroups = (applicationId: string) =>
  useQuery({ queryKey: applicationQueryKeys.servicenowGroups(applicationId), queryFn: () => apiGet<ServiceNowGroup[]>(`${applicationPath(applicationId)}/servicenow-groups`) });
export const searchServiceNowGroups = (query: string) => apiGet<ServiceNowGroupSearchResult[]>("/servicenow/groups/search", { query: { query } });
export const fetchDiagnosticSettingCommand = (applicationId: string, serviceId: string) =>
  apiGet<DiagnosticSettingCommand>(`${applicationPath(applicationId)}/services/${serviceId}/diagnostic-setting-command`);

/* ── Mutations ──────────────────────────────────────────────────────────────── */
/** Runs a mutation and refreshes everything under `applications/<id>` afterwards (readiness included). */
function useApplicationMutation<Result, Variables>(applicationId: string, mutate: (variables: Variables) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: mutate,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications", applicationId] }),
  });
}

export function useCreateApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateApplicationBody) => apiPost<Application, CreateApplicationBody>("/applications", body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: applicationQueryKeys.list() }),
  });
}
export const useUpdateApplication = (applicationId: string) =>
  useApplicationMutation(applicationId, (body: Partial<Application> & { incidentCreationPolicy?: IncidentCreationPolicy }) => apiPatch<Application>(applicationPath(applicationId), body));
export const useApplicationLifecycleAction = (applicationId: string) =>
  useApplicationMutation(applicationId, (action: "go-live" | "pause" | "resume") => apiPost<Application>(`${applicationPath(applicationId)}/${action}`));
export const useDeleteApplication = (applicationId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiDelete<void>(applicationPath(applicationId)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: applicationQueryKeys.list() }),
  });
};
export const useUpdateAccess = (applicationId: string) =>
  useApplicationMutation(applicationId, (body: Partial<Pick<AccessInformation, "adminGroupName" | "adminGroupObjectId" | "readerGroupName" | "readerGroupObjectId">>) =>
    apiPatch<AccessInformation>(`${applicationPath(applicationId)}/access`, body));

export const useVerifyAccessGroups = (applicationId: string) =>
  useApplicationMutation(applicationId, () => apiPost<AccessVerification>(`${applicationPath(applicationId)}/access/verify`));

export const useAddComponent = (applicationId: string) =>
  useApplicationMutation(applicationId, (body: CreateComponentBody) => apiPost<ApplicationComponent, CreateComponentBody>(`${applicationPath(applicationId)}/components`, body));
export const useDeleteComponent = (applicationId: string) =>
  useApplicationMutation(applicationId, (componentId: string) => apiDelete<void>(`${applicationPath(applicationId)}/components/${componentId}`));
export const useComponentJob = (applicationId: string, jobKind: "verify" | "discover") =>
  useApplicationMutation(applicationId, (componentId: string) => apiPost<AcceptedJob>(`${applicationPath(applicationId)}/components/${componentId}/${jobKind}`));

export const useAddService = (applicationId: string) =>
  useApplicationMutation(applicationId, (body: CreateServiceBody) => apiPost<MonitoredServiceRow, CreateServiceBody>(`${applicationPath(applicationId)}/services`, body));
export const useUpdateService = (applicationId: string) =>
  useApplicationMutation(applicationId, (variables: { serviceId: string; body: ServiceUpdateBody }) =>
    apiPatch<MonitoredServiceRow>(`${applicationPath(applicationId)}/services/${variables.serviceId}`, variables.body));
export const useDeleteService = (applicationId: string) =>
  useApplicationMutation(applicationId, (serviceId: string) => apiDelete<void>(`${applicationPath(applicationId)}/services/${serviceId}`));
export const useBulkUpdateServices = (applicationId: string) =>
  useApplicationMutation(applicationId, (variables: { serviceIds: string[]; changes: ServiceBulkChanges }) =>
    apiPatch<MonitoredServiceRow[]>(`${applicationPath(applicationId)}/services/bulk`, variables));
export const useReplaceLogSources = (applicationId: string) =>
  useApplicationMutation(applicationId, (variables: { serviceId: string; sources: LogSourceInput[] }) =>
    apiPut<LogSource[]>(`${applicationPath(applicationId)}/services/${variables.serviceId}/log-sources`, variables.sources));
export const useTestLogSource = (applicationId: string) =>
  useApplicationMutation(applicationId, (variables: { serviceId: string; logSourceId: string }) =>
    apiPost<TestResult>(`${applicationPath(applicationId)}/services/${variables.serviceId}/log-sources/${variables.logSourceId}/test`));
export const useReplaceDependencies = (applicationId: string) =>
  useApplicationMutation(applicationId, (dependencies: { upstreamServiceId: string; downstreamServiceId: string; dependencyKind?: string }[]) =>
    apiPut<ServiceDependency[]>(`${applicationPath(applicationId)}/service-dependencies`, { dependencies }));

export const useSaveLogToolConnection = (applicationId: string) =>
  useApplicationMutation(applicationId, (variables: { connectionId?: string; body: LogToolConnectionBody }) =>
    variables.connectionId
      ? apiPatch<LogToolConnection>(`${applicationPath(applicationId)}/log-tool-connections/${variables.connectionId}`, variables.body)
      : apiPost<LogToolConnection>(`${applicationPath(applicationId)}/log-tool-connections`, variables.body));
export const useDeleteLogToolConnection = (applicationId: string) =>
  useApplicationMutation(applicationId, (connectionId: string) => apiDelete<void>(`${applicationPath(applicationId)}/log-tool-connections/${connectionId}`));
export const useTestLogToolConnection = (applicationId: string) =>
  useApplicationMutation(applicationId, (connectionId: string) => apiPost<TestResult>(`${applicationPath(applicationId)}/log-tool-connections/${connectionId}/test`));

export const useSaveIntegration = (applicationId: string) =>
  useApplicationMutation(applicationId, (variables: { integrationKind: string; integrationConfiguration: Record<string, unknown>; credentialValue?: string; integrationNotes?: string }) =>
    apiPut<Integration>(`${applicationPath(applicationId)}/integrations/${variables.integrationKind}`, {
      integrationConfiguration: variables.integrationConfiguration,
      credentialValue: variables.credentialValue,
      integrationNotes: variables.integrationNotes,
    }));
export const useAddRecordLink = (applicationId: string) =>
  useApplicationMutation(applicationId, (body: { recordSystem: "eai" | "cmdb"; recordIdentifier: string }) => apiPost<RecordLink>(`${applicationPath(applicationId)}/record-links`, body));
export const useDeleteRecordLink = (applicationId: string) =>
  useApplicationMutation(applicationId, (recordLinkId: string) => apiDelete<void>(`${applicationPath(applicationId)}/record-links/${recordLinkId}`));
export const useReplaceServiceNowGroups = (applicationId: string) =>
  useApplicationMutation(applicationId, (groupNames: string[]) => apiPut<ServiceNowGroup[]>(`${applicationPath(applicationId)}/servicenow-groups`, { groupNames }));
