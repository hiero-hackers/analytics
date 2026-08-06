/** Timestamps are labelled UTC wherever they appear, so they must be in UTC. */

import { describe, expect, it } from "vitest";
import { dateStamp, stamp } from "../format";

describe("stamp", () => {
  it("keeps a UTC timestamp as-is", () => {
    expect(stamp("2026-07-25T10:00:00+00:00")).toBe("2026-07-25 10:00");
    expect(stamp("2026-07-25T10:00:00Z")).toBe("2026-07-25 10:00");
  });

  it("converts an offset-bearing timestamp to UTC instead of truncating it", () => {
    // Truncating would read "10:00" and label it UTC — four hours wrong.
    expect(stamp("2026-07-25T10:00:00-04:00")).toBe("2026-07-25 14:00");
    expect(stamp("2026-07-25T23:30:00+05:30")).toBe("2026-07-25 18:00");
  });

  it("assumes UTC for a naive timestamp rather than the viewer's local zone", () => {
    expect(stamp("2026-07-25T10:00:00")).toBe("2026-07-25 10:00");
    expect(stamp("2026-07-26T13:55:36.470051")).toBe("2026-07-26 13:55");
  });

  it("shows an unparseable value raw rather than throwing", () => {
    expect(stamp("not-a-date")).toBe("not-a-date");
  });
});

describe("dateStamp", () => {
  it("returns just the UTC date", () => {
    expect(dateStamp("2026-07-25T10:00:00+00:00")).toBe("2026-07-25");
    expect(dateStamp("2026-07-25 23:20:25+00:00")).toBe("2026-07-25");
  });

  it("converts across the day boundary instead of truncating", () => {
    // Truncating would report the 26th for an instant on the 25th UTC.
    expect(dateStamp("2026-07-26T01:20:25+03:00")).toBe("2026-07-25");
    expect(dateStamp("2026-07-25T22:30:00-04:00")).toBe("2026-07-26");
  });

  it("assumes UTC for a naive timestamp and degrades raw when unparseable", () => {
    expect(dateStamp("2026-07-25T10:00:00")).toBe("2026-07-25");
    expect(dateStamp("not-a-date")).toBe("not-a-date");
  });
});
