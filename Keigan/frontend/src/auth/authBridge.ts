/**
 * A tiny seam between React auth state and non-React code (the HTTP client, i18n preference sync).
 * `AuthProvider` registers the live handlers; everything else calls `authBridge`.
 */
interface AuthBridgeHandlers {
  /** Resolves a bearer token for the Keigan API, or null when signed out. */
  getAccessToken: () => Promise<string | null>;
  /** Called by the HTTP client when the API answers 401. */
  handleUnauthorized: () => void;
  isAuthenticated: () => boolean;
}

const signedOutHandlers: AuthBridgeHandlers = {
  getAccessToken: async () => null,
  handleUnauthorized: () => undefined,
  isAuthenticated: () => false,
};

let activeHandlers: AuthBridgeHandlers = signedOutHandlers;

export function registerAuthBridge(handlers: AuthBridgeHandlers): () => void {
  activeHandlers = handlers;
  return () => {
    if (activeHandlers === handlers) {
      activeHandlers = signedOutHandlers;
    }
  };
}

export const authBridge = {
  getAccessToken: () => activeHandlers.getAccessToken(),
  notifyUnauthorized: () => activeHandlers.handleUnauthorized(),
  isAuthenticated: () => activeHandlers.isAuthenticated(),
};
