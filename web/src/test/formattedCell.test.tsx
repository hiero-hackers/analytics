/**
 * Exercises every `ColumnFormat` value through the real `useDataTable` ->
 * `DataTable` -> `FormattedCell` pipeline, using a fixture with one column
 * per format. This is what keeps the TS union honest: if `ColumnFormat` ever
 * grows a value `FormattedCell` doesn't handle, or vice versa, this is where
 * that gap would show up as a wrong rendered cell rather than shipping quiet.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataTable } from "../components/DataTable";
import { useDataTable } from "../useDataTable";
import { ALL_FORMATS_DOC } from "./fixtures";

function Harness() {
  const table = useDataTable(ALL_FORMATS_DOC.columns, ALL_FORMATS_DOC.rows, "all-formats");
  return <DataTable table={table} />;
}

describe("FormattedCell", () => {
  it("renders every supported format correctly", () => {
    render(<Harness />);
    const row = screen.getAllByRole("row")[1]; // [0] is the header row

    expect(within(row).getByText("HIP-1200")).toBeInTheDocument();
    expect(within(row).getByText("2026-07-20")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "open ↗" })).toHaveAttribute("href", "https://example.test/pr/1");
    expect(within(row).getByText("merged")).toBeInTheDocument();
    expect(within(row).getByText("Final")).toBeInTheDocument();
    expect(within(row).getByText("✓")).toBeInTheDocument();
    expect(within(row).getByText("present")).toBeInTheDocument();
    expect(within(row).getByText("2,490")).toBeInTheDocument();
  });
});
