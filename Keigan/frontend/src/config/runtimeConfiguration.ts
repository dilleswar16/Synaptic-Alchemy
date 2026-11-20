import { createContext, useContext } from "react";
import { defaultAllowedLinkHosts } from "./allowedLinkHosts";

/**
 * Runtime configuration served by the backend (doc 05 §2) so one frontend build serves every environment
 * and `AUTH_MODE` in `backend/.env` switches both tiers.
 */
export type AuthMode = "local" | "entra";

export interface EntraConfiguration {
  tenantId: string;
  spaClientId: string;
  apiScope: string;
  authority: string;
}

export interface RuntimeConfiguration {
  authMode: AuthMode;
  entra: EntraConfiguration | null;
  /** `local`, `dev`, `test` or `prod` (backend `ENVIRONMENT`). */
  environmentName: string;
  supportedLocales: string[];
  defaultLocale: string;
  featureFlags: Record<string, boolean>;
  productVersion: string;
  /** Hosts that links in Markdown may point to; the backend value when it publishes one, otherwise `defaultAllowedLinkHosts`. */
  allowedLinkHosts: readonly string[];
  /** True when the API was unreachable in a development build and a local fallback is in use. */
  isFallback?: boolean;
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

/** Absolute or same-origin URL of an API path: `apiUrl("/auth/me")` → `/api/auth/me`. */
export function apiUrl(path: string): string {
  const normalisedPath = path.startsWith("/") ? path : `/${path}`;
  return `${apiBaseUrl}/api${normalisedPath}`;
}

const developmentFallbackConfiguration: RuntimeConfiguration = {
  authMode: "local",
  entra: null,
  environmentName: "local",
  supportedLocales: ["en", "ja", "zh-CN", "es", "es-MX", "nl", "fr"],
  defaultLocale: "en",
  featureFlags: {},
  productVersion: "0.0.0-dev",
  allowedLinkHosts: defaultAllowedLinkHosts,
  isFallback: true,
};

let configurationPromise: Promise<RuntimeConfiguration> | null = null;
let loadedConfiguration: RuntimeConfiguration | null = null;

function normaliseConfiguration(rawConfiguration: Partial<RuntimeConfiguration>): RuntimeConfiguration {
  return {
    authMode: rawConfiguration.authMode === "entra" ? "entra" : "local",
    entra: rawConfiguration.entra ?? null,
    environmentName: (rawConfiguration.environmentName ?? "local").toLowerCase(),
    supportedLocales: rawConfiguration.supportedLocales?.length
      ? rawConfiguration.supportedLocales
      : developmentFallbackConfiguration.supportedLocales,
    defaultLocale: rawConfiguration.defaultLocale ?? "en",
    featureFlags: rawConfiguration.featureFlags ?? {},
    productVersion: rawConfiguration.productVersion ?? "",
    allowedLinkHosts: rawConfiguration.allowedLinkHosts?.length ? rawConfiguration.allowedLinkHosts : defaultAllowedLinkHosts,
  };
}

async function fetchRuntimeConfiguration(): Promise<RuntimeConfiguration> {
  try {
    const response = await fetch(apiUrl("/public/client-configuration"), {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) {
      throw new Error(`Client configuration request failed with status ${response.status}`);
    }
    return normaliseConfiguration((await response.json()) as Partial<RuntimeConfiguration>);
  } catch (error) {
    if (import.meta.env.DEV) {
      console.warn("[Keigan] Client configuration unavailable; using the local development fallback.", error);
      return developmentFallbackConfiguration;
    }
    throw error;
  }
}

/** Loads the configuration once per page load (memoised). Call `resetRuntimeConfiguration()` to retry after a failure. */
export function loadRuntimeConfiguration(): Promise<RuntimeConfiguration> {
  configurationPromise ??= fetchRuntimeConfiguration().then((configuration) => {
    loadedConfiguration = configuration;
    return configuration;
  });
  return configurationPromise;
}

export function resetRuntimeConfiguration(): void {
  configurationPromise = null;
  loadedConfiguration = null;
}

/** Synchronous access for non-React code once the bootstrap has finished. */
export function getLoadedRuntimeConfiguration(): RuntimeConfiguration | null {
  return loadedConfiguration;
}

export const RuntimeConfigurationContext = createContext<RuntimeConfiguration | null>(null);

export function useRuntimeConfiguration(): RuntimeConfiguration {
  const configuration = useContext(RuntimeConfigurationContext);
  if (!configuration) {
    throw new Error("useRuntimeConfiguration must be used inside the application bootstrap.");
  }
  return configuration;
}

/** `true` when the backend enabled the named feature flag. */
export function useFeatureFlag(featureFlagName: string): boolean {
  return useRuntimeConfiguration().featureFlags[featureFlagName] === true;
}

/** Developer tooling (design-system showcase, devtools) is only offered in local and dev environments. */
export function isDeveloperEnvironment(configuration: RuntimeConfiguration): boolean {
  return configuration.environmentName === "local" || configuration.environmentName === "dev";
}

/** Production is `prod` or `production`; everything else is treated as non-production. */
export function isProductionEnvironment(configuration: RuntimeConfiguration): boolean {
  return configuration.environmentName === "prod" || configuration.environmentName === "production";
}
