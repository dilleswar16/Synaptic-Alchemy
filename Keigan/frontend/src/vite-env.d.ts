/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Origin of the Keigan API. Empty means same origin (proxied `/api`). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
