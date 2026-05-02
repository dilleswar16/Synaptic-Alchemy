/**
 * Frontend API base URL.
 *
 * - Local dev and Static Web App proxy deployments use same-origin /api.
 * - Direct App Service calls use VITE_API_URL set to the FastAPI origin.
 *
 * IMPORTANT (SSE / streaming RCA): Azure Static Web Apps buffers
 * `text/event-stream` responses sent through its proxy layer, which breaks
 * live token streaming.  In production, set `VITE_API_URL` to the App
 * Service origin so the browser hits the API directly and SSE flushes
 * frame-by-frame.  See setup/08_azure_deploy.md (Part 2, Step 2).
 */
const configuredApiUrl = import.meta.env.VITE_API_URL?.trim()

export const API_BASE = configuredApiUrl ? configuredApiUrl.replace(/\/+$/, '') : '/api'