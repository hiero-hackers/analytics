/**
 * Guards for data that leaves React's escaping: spreadsheet formulas in CSV
 * downloads, and link schemes the browser would execute.
 */

import { describe, expect, it } from "vitest";
import { csvSafe, safeUrl } from "../safety";

describe("csvSafe", () => {
  it.each(["=1+1", "+1", "-1+1", "@SUM(A1)", "\tcmd", "\rcmd", "\ncmd"])(
    "neutralises the formula trigger %j",
    (value) => {
      expect(csvSafe(value)).toBe(`'${value}`);
    },
  );

  it("neutralises an attacker-chosen PR title", () => {
    // Anyone can open a PR in a public repo and name it whatever they like;
    // that title reaches the evidence table and its CSV download verbatim.
    expect(csvSafe('=HYPERLINK("https://evil.test","click")')).toBe(
      '\'=HYPERLINK("https://evil.test","click")',
    );
  });

  it("leaves ordinary values and the empty-cell placeholder alone", () => {
    expect(csvSafe("feat: add HIP-1200 support")).toBe("feat: add HIP-1200 support");
    expect(csvSafe("-")).toBe("-");
    expect(csvSafe(42)).toBe("42");
    expect(csvSafe(null)).toBe("");
  });
});

describe("safeUrl", () => {
  it("allows the schemes real evidence links use", () => {
    expect(safeUrl("https://github.com/hiero-ledger/repo/pull/1")).toBe(
      "https://github.com/hiero-ledger/repo/pull/1",
    );
    expect(safeUrl("http://example.test")).toBe("http://example.test");
    expect(safeUrl("mailto:someone@example.test")).toBe("mailto:someone@example.test");
  });

  it("rejects schemes that would execute in the page", () => {
    expect(safeUrl("javascript:alert(1)")).toBeNull();
    expect(safeUrl("JaVaScRiPt:alert(1)")).toBeNull();
    expect(safeUrl("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(safeUrl("  javascript:alert(1)  ")).toBeNull();
  });

  it("rejects empty and unparseable values", () => {
    expect(safeUrl("")).toBeNull();
    expect(safeUrl("   ")).toBeNull();
  });
});
