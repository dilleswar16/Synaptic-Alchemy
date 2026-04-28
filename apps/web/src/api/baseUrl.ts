/**
 * Frontend API base URL.
 *
 * - Local dev and Static Web App proxy deployments use same-origin /api.
 * - Direct App Service calls use VITE_API_URL set to the FastAPI origin.
 */
const configuredApiUrl = import.meta.env.VITE_API_URL?.trim()

export const API_BASE = configuredApiUrl ? configuredApiUrl.replace(/\/+$/, '') : '/api'