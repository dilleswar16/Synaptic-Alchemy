/** Shared API shapes (doc 05 §1). JSON is camelCase; identifiers are UUID strings; times are ISO 8601 UTC. */

export type Identifier = string;

/** ISO 8601 UTC timestamp such as `2026-11-19T04:12:00Z`. */
export type IsoDateTimeString = string;

/** Paginated list response: `GET …?page=&pageSize=` (max page size 200). */
export interface PagedResult<ItemType> {
  items: ItemType[];
  totalCount: number;
  page: number;
  pageSize: number;
}

export interface PaginationParameters {
  page?: number;
  pageSize?: number;
}

export interface FieldError {
  field: string;
  message: string;
}

/** RFC 9457 problem+json body returned for every error. */
export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  errorCode?: string;
  correlationId?: string;
  fieldErrors?: FieldError[];
  /** Extension member of `answer_in_progress` and `duplicate_request` (Ask Keigan): the run that already exists. */
  answerRunId?: string;
}

/** `202 Accepted` body for endpoints that start background jobs. */
export interface AcceptedJob {
  jobId: Identifier;
  status: "queued" | "running" | "succeeded" | "failed" | (string & {});
}

export type ApplicationRole = "admin" | "reader";

export type Priority = "P1" | "P2" | "P3" | "P4";
