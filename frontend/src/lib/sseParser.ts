/**
 * Market Intelligence Lab — Robust W3C Server-Sent Events Protocol Parser
 * Workstream 5.3 — Handles fragmented TCP packets, multi-line data buffering, and EOF flushing.
 */

export interface ServerSentEvent {
  id?: string;
  event: string;
  data: string;
}

export type EventCallback = (event: ServerSentEvent) => void;

export class RobustSSEParser {
  private buffer = "";

  /**
   * Consumes an incoming raw text chunk, normalizes CRLF, 
   * parses complete event frames, and retains residual data.
   */
  public feed(chunk: string, onEvent: EventCallback) {
    // Normalize CRLF to LF
    this.buffer += chunk.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    let boundaryIndex: number;
    while ((boundaryIndex = this.buffer.indexOf("\n\n")) !== -1) {
      const rawFrame = this.buffer.slice(0, boundaryIndex);
      this.buffer = this.buffer.slice(boundaryIndex + 2);

      if (rawFrame.trim().length === 0) {
        continue; // Keep-alive frame
      }

      const parsed = this.parseFrame(rawFrame);
      if (parsed) {
        onEvent(parsed);
      }
    }
  }

  /**
   * Flushes any residual text at stream EOF.
   */
  public flush(onEvent: EventCallback) {
    if (this.buffer.trim().length > 0) {
      const parsed = this.parseFrame(this.buffer);
      if (parsed) {
        onEvent(parsed);
      }
      this.buffer = "";
    }
  }

  private parseFrame(raw: string): ServerSentEvent | null {
    const lines = raw.split("\n");
    let id: string | undefined;
    let event = "message";
    const dataLines: string[] = [];

    for (const line of lines) {
      if (line.startsWith(":")) {
        continue; // SSE comment / ping / keep-alive tick
      }

      const colonIdx = line.indexOf(":");
      if (colonIdx === -1) {
        // Field with no value
        if (line === "data") dataLines.push("");
        continue;
      }

      const field = line.slice(0, colonIdx);
      let value = line.slice(colonIdx + 1);
      if (value.startsWith(" ")) {
        value = value.slice(1);
      }

      if (field === "event") {
        event = value;
      } else if (field === "data") {
        dataLines.push(value);
      } else if (field === "id") {
        id = value;
      }
    }

    if (dataLines.length === 0 && !id && event === "message") {
      return null;
    }

    return {
      id,
      event,
      data: dataLines.join("\n"), // W3C Spec: join multi-line data with newline
    };
  }
}
