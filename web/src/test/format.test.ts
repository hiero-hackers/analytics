/** Timestamps are labelled UTC wherever they appear, so they must be in UTC. */

import { describe, expect, it } from "vitest";
import { stamp } from "../format";

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
