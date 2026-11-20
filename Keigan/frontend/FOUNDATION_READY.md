# Frontend foundation: READY

Status: `npm run build` passes with zero TypeScript errors (Vite 6, React 19, Tailwind v4, React Router 7). Feature agents may start frontend work.

## Run
- Install (already done): `cd frontend && npm install`
- Dev server: `npm run dev` (http://localhost:5173). Point `/api` at another backend with `VITE_API_PROXY_TARGET` (default `http://localhost:8000`). PowerShell: `$env:VITE_API_PROXY_TARGET="http://localhost:8002"; npm run dev -- --port 5175`
- Check: `npm run build` (runs `tsc -b` then `vite build`)
- Local sign-in users: `keigan.admin@keigan.local` (Keigan admin), `aiko.appadmin@keigan.local`, `rui.reader@keigan.local`, `noa.noaccess@keigan.local`.
- Showcase of every component: `/design-system` (local/dev only).

## Where to work
Each feature agent edits only `src/features/<area>/**`. Stub pages already exist at the exact paths used by `app/routes.tsx`; replace their content and keep the default export. Shared code (`components/ui|layout|charts|topology`, `api/httpClient.ts`, `auth/*`, `i18n/index.ts`, `styles/*`, `app/*`) is lead-owned: if something is missing, implement it locally in your feature and add a line to `My Plans/09_LEARNINGS_LOG.md`.
Full guide: `My Plans/04_UI_UX_DESIGN_SYSTEM.md` section 10.

## Export index
- UI kit `@/components/ui/*`: Button, IconButton, Card (CardHeader/Body/Footer), StatTile, StatusChip, Badge, PriorityChip, AiGeneratedChip, EvidenceChip, Avatar, Kbd, Tabs, SegmentedControl, Input, Textarea, Select, Combobox, TokenInput, RadioGroup, Checkbox, Switch, FormField, Dialog, ConfirmDialog, Drawer, Popover, Tooltip, DropdownMenu, DataTable, EmptyState, ErrorState, Skeleton, Spinner, Banner, Toast (useToast), CommandBlock, MarkdownView, ConfidenceMeter, Timeline, Stepper, ReadinessBar, SaveIndicator, FileDrop, CountWithInfo, KeyValueList, SectionHeader, ProgressBar, RelativeTime, CopyButton, toneStyles.
- Charts `@/components/charts`: Sparkline, TimeSeriesChart, BarChart, DonutChart, FunnelChart, HeatmapGrid, ChartFrame, chartTheme helpers. Topology: `@/components/topology/TopologyGraph`.
- Layout `@/components/layout`: PageHeader, KeiganLogo, AppShell, Sidebar, TopBar, CommandPalette, ApplicationScopeSwitcher, LanguageSwitcher, ThemeToggle.
- API: `@/api/httpClient` (apiGet/apiPost/apiPut/apiPatch/apiDelete/apiUpload, ApiError, isApiError), `@/api/queryClient`, `@/api/authApi`, `@/api/types/common`.
- Auth: `@/auth/authContext` (useAuth, useCurrentUser), `@/auth/accessControl` (useAccessControl, canReadApplication, canEditApplication), `@/auth/applicationScope` (useApplicationScope).
- Hooks and utils: `@/hooks/useTheme`, `useDebouncedValue`, `useMediaQuery`; `@/utils/cn`, `@/utils/formatters`; `@/config/runtimeConfiguration` (useRuntimeConfiguration, useFeatureFlag).
- i18n: `useTranslation("<namespace>")`; namespaces: common, navigation, auth, home, incidents, investigations, alerts, slo, intelligence, chat, applications, onboarding, knowledge, notifications, administration.

## Notes
- The scope switcher reads `GET /api/applications?pageSize=200` (falls back to the user's role assignments) and accepts an array or `{items}`; fields `id|applicationId`, `code|applicationCode`, `name|applicationName`.
- The `/design-system` page and the bootstrap error screen use English-only copy by design.
- Not smoke-tested in a browser (build and type check only).
