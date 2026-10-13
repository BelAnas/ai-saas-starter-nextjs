// A small Server-Sent Events parser.
//
// The browser's EventSource can only send GET requests without a body, and a chat message is a
// POST. So the answer is read from `fetch` as a byte stream and the event format is parsed here.

export type SseEvent = { event: string; data: string };

export function createSseParser(onEvent: (event: SseEvent) => void) {
  let buffer = "";

  function parseBlock(block: string) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue; // a comment, used by servers as a keep-alive
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      let value = colon === -1 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (data.length > 0) onEvent({ event, data: data.join("\n") });
  }

  return {
    /** Feed the next piece of text. A network chunk can end in the middle of an event. */
    push(chunk: string) {
      buffer += chunk.replace(/\r\n/g, "\n");
      let end = buffer.indexOf("\n\n");
      while (end !== -1) {
        parseBlock(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
        end = buffer.indexOf("\n\n");
      }
    },
  };
}
