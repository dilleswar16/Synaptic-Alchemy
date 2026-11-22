/** Maximum heights of the scrolling blocks inside a tool card and its drawers, so no block pushes the conversation off the screen. */
export const toolBlockMaximumHeights = {
  /** A query or the inputs as JSON. */
  code: "200px",
  /** The query a running call has written. */
  progressQuery: "160px",
  /** The sample rows of a query result. */
  sampleRows: "240px",
  /** The full stored output in its drawer. */
  fullOutput: "60vh",
  /** The text the model saw, in its drawer. */
  modelView: "40vh",
} as const;
