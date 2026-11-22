/** One dispatched server-sent event: the `event:` name (default `message`), the `id:` and the joined `data:` lines. */
export interface ServerSentFrame {
  id: string | null;
  event: string;
  data: string;
}

export interface ParsedServerSentEvents {
  frames: ServerSentFrame[];
  /** Text of a frame that has not ended yet; prepend it to the next chunk. */
  remainder: string;
}

function parseFrameBlock(block: string): ServerSentFrame | null {
  let id: string | null = null;
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) {
      continue; // blank, or a comment such as the `: keep-alive` heartbeat
    }
    const separatorIndex = line.indexOf(":");
    const fieldName = separatorIndex === -1 ? line : line.slice(0, separatorIndex);
    const rawValue = separatorIndex === -1 ? "" : line.slice(separatorIndex + 1);
    const fieldValue = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;
    if (fieldName === "event") {
      eventName = fieldValue;
    } else if (fieldName === "data") {
      dataLines.push(fieldValue);
    } else if (fieldName === "id") {
      id = fieldValue;
    }
  }
  // Like a browser, dispatch only frames that carry data; a block of comments is not an event.
  return dataLines.length > 0 ? { id, event: eventName, data: dataLines.join("\n") } : null;
}

/**
 * Splits streamed text into server-sent-event frames (https://html.spec.whatwg.org/multipage/server-sent-events.html). Pure: feed it the
 * buffered text plus the new chunk and keep the returned `remainder`. Accepts `\n`, `\r\n` and `\r` line endings, also when a chunk ends between
 * the `\r` and the `\n`.
 */
export function parseServerSentEvents(bufferedText: string): ParsedServerSentEvents {
  const endsWithCarriageReturn = bufferedText.endsWith("\r");
  const completeText = (endsWithCarriageReturn ? bufferedText.slice(0, -1) : bufferedText).replace(/\r\n?/g, "\n");
  const blocks = completeText.split("\n\n");
  const unfinishedBlock = blocks.pop() ?? "";
  const frames = blocks.flatMap((block) => parseFrameBlock(block) ?? []);
  return { frames, remainder: endsWithCarriageReturn ? `${unfinishedBlock}\r` : unfinishedBlock };
}
