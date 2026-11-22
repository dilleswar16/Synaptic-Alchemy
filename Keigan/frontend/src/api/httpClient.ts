import { authBridge } from "@/auth/authBridge";
import { apiUrl } from "@/config/runtimeConfiguration";
import type { FieldError, ProblemDetails } from "./types/common";

/**
 * Typed HTTP client for the Keigan API (doc 05 §1).
 * Paths are relative to `/api`: `apiGet<CurrentUser>("/auth/me")`.
 * Adds the bearer token and `X-Correlation-Id`, parses JSON and turns problem+json errors into `ApiError`.
 */

export type QueryParameterValue = string | number | boolean | null | undefined | ReadonlyArray<string | number>;
export type QueryParameters = Record<string, QueryParameterValue>;

export interface RequestOptions {
  /** Query parameters; arrays are sent comma-separated (`applicationIds=a,b`), empty values are skipped. */
  query?: QueryParameters;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Public endpoint: do not attach a bearer token. */
  isPublic?: boolean;
  /** Do not treat a 401 as an expired session (sign-in endpoints). */
  ignoreUnauthorized?: boolean;
}

export interface UploadOptions extends RequestOptions {
  /** Upload progress from 0 to 100. */
  onUploadProgress?: (percentComplete: number) => void;
}

export class ApiError extends Error {
  /** HTTP status; 0 means the request never reached the server (network error). */
  readonly status: number;
  readonly title: string;
  readonly detail: string | undefined;
  readonly errorCode: string | undefined;
  readonly fieldErrors: FieldError[];
  readonly correlationId: string | undefined;
  readonly problemType: string | undefined;
  readonly answerRunId: string | undefined;

  constructor(status: number, problem: ProblemDetails, requestCorrelationId?: string) {
    const title = problem.title ?? (status === 0 ? "Network error" : `Request failed with status ${status}`);
    super(problem.detail ?? title);
    this.name = "ApiError";
    this.status = status;
    this.title = title;
    this.detail = problem.detail;
    this.errorCode = problem.errorCode;
    this.fieldErrors = problem.fieldErrors ?? [];
    this.correlationId = problem.correlationId ?? requestCorrelationId;
    this.problemType = problem.type;
    this.answerRunId = problem.answerRunId;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }

  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500;
  }

  /** Server-side validation message for a form field (camelCase field name). */
  fieldErrorFor(fieldName: string): string | undefined {
    return this.fieldErrors.find((fieldError) => fieldError.field === fieldName)?.message;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function createCorrelationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Non-secure contexts (plain http on a non-localhost host) have no randomUUID.
  const randomBytes = new Uint8Array(16);
  crypto.getRandomValues(randomBytes);
  randomBytes[6] = ((randomBytes[6] ?? 0) & 0x0f) | 0x40;
  randomBytes[8] = ((randomBytes[8] ?? 0) & 0x3f) | 0x80;
  const hexadecimal = Array.from(randomBytes, (byteValue) => byteValue.toString(16).padStart(2, "0")).join("");
  return `${hexadecimal.slice(0, 8)}-${hexadecimal.slice(8, 12)}-${hexadecimal.slice(12, 16)}-${hexadecimal.slice(16, 20)}-${hexadecimal.slice(20)}`;
}

export function buildApiUrl(path: string, query?: QueryParameters): string {
  const url = apiUrl(path);
  if (!query) {
    return url;
  }
  const searchParameters = new URLSearchParams();
  for (const [parameterName, parameterValue] of Object.entries(query)) {
    if (parameterValue === null || parameterValue === undefined || parameterValue === "") {
      continue;
    }
    if (Array.isArray(parameterValue)) {
      if (parameterValue.length > 0) {
        searchParameters.set(parameterName, parameterValue.join(","));
      }
      continue;
    }
    searchParameters.set(parameterName, String(parameterValue));
  }
  const queryString = searchParameters.toString();
  return queryString ? `${url}${url.includes("?") ? "&" : "?"}${queryString}` : url;
}

async function buildHeaders(options: RequestOptions, correlationId: string, hasJsonBody: boolean): Promise<Headers> {
  const headers = new Headers({ Accept: "application/json, application/problem+json", "X-Correlation-Id": correlationId });
  if (hasJsonBody) {
    headers.set("Content-Type", "application/json");
  }
  if (!options.isPublic) {
    const accessToken = await authBridge.getAccessToken();
    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }
  }
  for (const [headerName, headerValue] of Object.entries(options.headers ?? {})) {
    headers.set(headerName, headerValue);
  }
  return headers;
}

function parseResponseText(responseText: string, contentType: string | null): unknown {
  if (!responseText) {
    return undefined;
  }
  if (contentType?.includes("json")) {
    try {
      return JSON.parse(responseText) as unknown;
    } catch {
      return responseText;
    }
  }
  return responseText;
}

function toProblemDetails(body: unknown): ProblemDetails {
  if (body && typeof body === "object") {
    return body as ProblemDetails;
  }
  return typeof body === "string" && body.length > 0 && body.length < 500 ? { detail: body } : {};
}

function handleErrorStatus(status: number, body: unknown, correlationId: string, options: RequestOptions): never {
  if (status === 401 && !options.ignoreUnauthorized && !options.isPublic) {
    authBridge.notifyUnauthorized();
  }
  throw new ApiError(status, toProblemDetails(body), correlationId);
}

/** `fetch` that rethrows an abort as is and turns any other failure to reach the server into an `ApiError` with status 0. */
async function fetchOrThrowApiError(method: string, path: string, body: unknown, options: RequestOptions, headers: Headers, correlationId: string): Promise<Response> {
  try {
    return await fetch(buildApiUrl(path, options.query), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: options.signal,
      credentials: "same-origin",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(0, { detail: error instanceof Error ? error.message : undefined }, correlationId);
  }
}

async function sendRequest<ResponseType>(
  method: string,
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<ResponseType> {
  const correlationId = createCorrelationId();
  const hasJsonBody = body !== undefined;
  const headers = await buildHeaders(options, correlationId, hasJsonBody);
  const response = await fetchOrThrowApiError(method, path, body, options, headers, correlationId);

  const responseBody = parseResponseText(await response.text(), response.headers.get("Content-Type"));
  if (!response.ok) {
    handleErrorStatus(response.status, responseBody, response.headers.get("X-Correlation-Id") ?? correlationId, options);
  }
  return responseBody as ResponseType;
}

export function apiGet<ResponseType>(path: string, options?: RequestOptions): Promise<ResponseType> {
  return sendRequest<ResponseType>("GET", path, undefined, options);
}

export function apiPost<ResponseType, RequestBody = unknown>(
  path: string,
  body?: RequestBody,
  options?: RequestOptions,
): Promise<ResponseType> {
  return sendRequest<ResponseType>("POST", path, body, options);
}

export function apiPut<ResponseType, RequestBody = unknown>(path: string, body: RequestBody, options?: RequestOptions): Promise<ResponseType> {
  return sendRequest<ResponseType>("PUT", path, body, options);
}

export function apiPatch<ResponseType, RequestBody = unknown>(
  path: string,
  body: RequestBody,
  options?: RequestOptions,
): Promise<ResponseType> {
  return sendRequest<ResponseType>("PATCH", path, body, options);
}

export function apiDelete<ResponseType = void>(path: string, options?: RequestOptions): Promise<ResponseType> {
  return sendRequest<ResponseType>("DELETE", path, undefined, options);
}

/**
 * POST that returns the open response so the caller can read its body as a stream (server-sent events: `EventSource` cannot send a
 * POST body or an `Authorization` header). The body is not consumed here; an error status is read and thrown as `ApiError` first.
 */
export async function apiStream<RequestBody = unknown>(path: string, body: RequestBody, options: RequestOptions = {}): Promise<Response> {
  const correlationId = createCorrelationId();
  const headers = await buildHeaders({ ...options, headers: { Accept: "text/event-stream", ...options.headers } }, correlationId, true);
  const response = await fetchOrThrowApiError("POST", path, body, options, headers, correlationId);
  if (!response.ok) {
    handleErrorStatus(response.status, parseResponseText(await response.text(), response.headers.get("Content-Type")), response.headers.get("X-Correlation-Id") ?? correlationId, options);
  }
  return response;
}

/**
 * Multipart upload (`FormData`). Uses XMLHttpRequest because fetch cannot report upload progress.
 */
export async function apiUpload<ResponseType>(path: string, formData: FormData, options: UploadOptions = {}): Promise<ResponseType> {
  const correlationId = createCorrelationId();
  const headers = await buildHeaders(options, correlationId, false);

  return new Promise<ResponseType>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", buildApiUrl(path, options.query));
    headers.forEach((headerValue, headerName) => request.setRequestHeader(headerName, headerValue));

    if (options.onUploadProgress) {
      const reportProgress = options.onUploadProgress;
      request.upload.addEventListener("progress", (progressEvent) => {
        if (progressEvent.lengthComputable) {
          reportProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100));
        }
      });
    }

    request.addEventListener("load", () => {
      const responseBody = parseResponseText(request.responseText, request.getResponseHeader("Content-Type"));
      if (request.status >= 200 && request.status < 300) {
        options.onUploadProgress?.(100);
        resolve(responseBody as ResponseType);
        return;
      }
      try {
        handleErrorStatus(request.status, responseBody, request.getResponseHeader("X-Correlation-Id") ?? correlationId, options);
      } catch (error) {
        reject(error);
      }
    });
    request.addEventListener("error", () => reject(new ApiError(0, {}, correlationId)));
    request.addEventListener("abort", () => reject(new DOMException("Upload aborted", "AbortError")));

    if (options.signal) {
      if (options.signal.aborted) {
        request.abort();
        return;
      }
      options.signal.addEventListener("abort", () => request.abort(), { once: true });
    }
    request.send(formData);
  });
}
