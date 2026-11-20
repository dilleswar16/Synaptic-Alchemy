import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/httpClient";
import { useAuth } from "./authContext";

/**
 * Application scope (top bar): "All my applications" (no selection) or a set of applications. Lists, counts and
 * chat answers follow it. Feature code: `const { applicationIds } = useApplicationScope();` and pass
 * `applicationIds` as the `applicationIds` query parameter (an empty array = everything the user can read,
 * and the API already filters by access).
 */

export interface ScopeApplication {
  applicationId: string;
  applicationCode: string;
  applicationName: string;
  role?: "admin" | "reader";
}

const scopeStorageKey = "keigan.applicationScope";
const scopeListeners = new Set<() => void>();

function readStoredScope(): string[] {
  try {
    const storedValue = window.localStorage.getItem(scopeStorageKey);
    const parsedValue: unknown = storedValue ? JSON.parse(storedValue) : [];
    return Array.isArray(parsedValue) ? parsedValue.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

let selectedIdentifiers: string[] = typeof window === "undefined" ? [] : readStoredScope();

function writeScope(nextIdentifiers: string[]): void {
  selectedIdentifiers = nextIdentifiers;
  try {
    window.localStorage.setItem(scopeStorageKey, JSON.stringify(nextIdentifiers));
  } catch {
    // The scope still applies for this tab.
  }
  scopeListeners.forEach((notifyListener) => notifyListener());
}

function subscribeToScope(onScopeChange: () => void): () => void {
  scopeListeners.add(onScopeChange);
  return () => scopeListeners.delete(onScopeChange);
}

interface RawApplicationSummary {
  id?: string;
  applicationId?: string;
  code?: string;
  applicationCode?: string;
  name?: string;
  applicationName?: string;
}

export const scopeApplicationsQueryKey = ["applications", "scope-options"] as const;

export interface ApplicationScope {
  /** Applications the user can pick from. */
  availableApplications: ScopeApplication[];
  isLoadingApplications: boolean;
  /** Explicit selection; empty means "all my applications". */
  selectedApplicationIds: string[];
  /** Ready for `applicationIds=` query parameters; empty = no restriction beyond the user's access. */
  applicationIds: string[];
  isAllSelected: boolean;
  setSelectedApplicationIds: (applicationIds: string[]) => void;
  clearSelection: () => void;
}

export function useApplicationScope(): ApplicationScope {
  const { user, status } = useAuth();
  const storedSelection = useSyncExternalStore(subscribeToScope, () => selectedIdentifiers, () => selectedIdentifiers);

  const { data: summaries, isLoading } = useQuery({
    queryKey: scopeApplicationsQueryKey,
    enabled: status === "authenticated",
    staleTime: 5 * 60_000,
    queryFn: async () => {
      const response = await apiGet<RawApplicationSummary[] | { items?: RawApplicationSummary[] }>("/applications", { query: { pageSize: 200 } });
      return Array.isArray(response) ? response : (response.items ?? []);
    },
  });

  const availableApplications = useMemo<ScopeApplication[]>(() => {
    const roleByApplicationId = new Map((user?.applicationRoles ?? []).map((assignment) => [assignment.applicationId, assignment.role]));
    const fromApi: ScopeApplication[] = (summaries ?? [])
      .map((summary) => ({
        applicationId: summary.applicationId ?? summary.id ?? "",
        applicationCode: summary.applicationCode ?? summary.code ?? "",
        applicationName: summary.applicationName ?? summary.name ?? "",
      }))
      .filter((application) => application.applicationId)
      .map((application) => ({ ...application, role: roleByApplicationId.get(application.applicationId) }));
    const source = fromApi.length > 0 ? fromApi : (user?.applicationRoles ?? []).map((assignment) => ({ ...assignment }));
    return [...source].sort((first, second) => first.applicationName.localeCompare(second.applicationName));
  }, [summaries, user]);

  const validSelection = useMemo(() => {
    const knownIdentifiers = new Set(availableApplications.map((application) => application.applicationId));
    return knownIdentifiers.size === 0 ? storedSelection : storedSelection.filter((identifier) => knownIdentifiers.has(identifier));
  }, [availableApplications, storedSelection]);

  return {
    availableApplications,
    isLoadingApplications: isLoading,
    selectedApplicationIds: validSelection,
    applicationIds: validSelection,
    isAllSelected: validSelection.length === 0,
    setSelectedApplicationIds: useCallback((applicationIds: string[]) => writeScope(applicationIds), []),
    clearSelection: useCallback(() => writeScope([]), []),
  };
}
