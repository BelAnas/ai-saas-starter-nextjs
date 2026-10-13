import { describe, expect, it } from "vitest";
import { niceMax } from "./format";
import { createSseParser, type SseEvent } from "./sse";

function collect(chunks: string[]): SseEvent[] {
  const events: SseEvent[] = [];
  const parser = createSseParser((e) => events.push(e));
  chunks.forEach((c) => parser.push(c));
  return events;
}

describe("createSseParser", () => {
  it("parses complete events", () => {
    expect(collect(['event: delta\ndata: {"text":"Hi"}\n\nevent: done\ndata: {}\n\n'])).toEqual([
      { event: "delta", data: '{"text":"Hi"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("joins an event that arrives in several network chunks", () => {
    const whole = 'event: delta\ndata: {"text":"Hello world"}\n\n';
    // Cut at every possible position: the result must not depend on where the network split it.
    for (let cut = 1; cut < whole.length; cut++) {
      expect(collect([whole.slice(0, cut), whole.slice(cut)])).toEqual([
        { event: "delta", data: '{"text":"Hello world"}' },
      ]);
    }
  });

  it("emits nothing until the blank line that ends an event", () => {
    expect(collect(['event: delta\ndata: {"text":"Hi"}\n'])).toEqual([]);
  });

  it("ignores comments, accepts CRLF and defaults the event name", () => {
    expect(collect([": keep-alive\n\n", "data: a\r\ndata: b\r\n\r\n"])).toEqual([{ event: "message", data: "a\nb" }]);
  });
});

describe("niceMax", () => {
  it("rounds the axis top up to 1, 2 or 5 times a power of ten", () => {
    expect([0, 1, 7, 12, 43, 180, 0.03].map(niceMax)).toEqual([1, 1, 10, 20, 50, 200, 0.05]);
  });
});
