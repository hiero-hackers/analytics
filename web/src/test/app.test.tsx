/**
 * App-level behaviour against the fixture manifest: macro tabs, per-macro org
 * tabs, metric tiles, glossary, section groups, and the table chrome
 * (sorting, filtering, period tabs, the action link).
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { stubApi } from "./fixtures";

beforeEach(() => {
  vi.unstubAllGlobals();
  stubApi();
});

const openGovernance = async () => {
  render(<App />);
  await screen.findByRole("button", { name: "Governance" });
  await userEvent.click(screen.getByRole("button", { name: "Governance" }));
  return await screen.findByText("Role holders");
};

describe("App shell", () => {
  it("renders a macro tab per manifest macro and switches between them", async () => {
    render(<App />);

    expect(await screen.findByRole("button", { name: "Governance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Contributors" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Governance" }));
    expect(await screen.findByText("Role holders")).toBeInTheDocument();
    expect(screen.getByText("Maintainer pipeline")).toBeInTheDocument();
  });

  it("shows org tabs only on macros where more than one org has content", async () => {
    render(<App />);

    // Contributors: both orgs -> org tab bar present.
    await userEvent.click(await screen.findByRole("button", { name: "Contributors" }));
    expect(await screen.findByRole("button", { name: "hiero-hackers" })).toBeInTheDocument();

    // Governance: only hiero-ledger -> no org tab bar.
    await userEvent.click(screen.getByRole("button", { name: "Governance" }));
    await screen.findByText("Role holders");
    expect(screen.queryByRole("button", { name: "hiero-hackers" })).not.toBeInTheDocument();
  });

  it("switching org swaps the rendered rows", async () => {
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Contributors" }));
    expect(await screen.findByText("alice")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "hiero-hackers" }));
    expect(await screen.findByText("erin")).toBeInTheDocument();
    expect(screen.queryByText("alice")).not.toBeInTheDocument();
  });

  it("renders metric tiles, the glossary, group headers, and both footers", async () => {
    await openGovernance();

    expect(screen.getByText("maintainers")).toBeInTheDocument();
    expect(screen.getByText("103")).toBeInTheDocument();
    expect(screen.getByText("How to read this — what each column means")).toBeInTheDocument();
    // Each group appears twice: once in the jump bar, once as its header.
    expect(screen.getByRole("link", { name: "Charts" })).toHaveAttribute("href", "#grp-Charts");
    expect(screen.getAllByText("Charts")).toHaveLength(2);
    expect(screen.getAllByText("Roles & teams")).toHaveLength(2);
    expect(screen.getByText(/Work in progress/)).toBeInTheDocument();
    expect(screen.getByText(/data 2026-07-25 21:00 UTC · code abc1234/)).toBeInTheDocument();
  });
});

describe("Section tables", () => {
  it("sorts by a clicked column header", async () => {
    await openGovernance();
    const table = screen.getByRole("table");

    // Numeric columns sort descending first (TanStack default), then toggle.
    await userEvent.click(within(table).getByText("count"));
    let users = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[0].textContent);
    expect(users).toEqual(["alice", "bob", "carol"]);

    await userEvent.click(within(table).getByText(/count/));
    users = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[0].textContent);
    expect(users).toEqual(["carol", "bob", "alice"]);
  });

  it("filters rows and shows the shown-of-total badge", async () => {
    await openGovernance();

    await userEvent.type(screen.getByPlaceholderText("Filter…"), "ali");
    expect(screen.getByText("1 of 3")).toBeInTheDocument();
    expect(screen.queryByText("bob")).not.toBeInTheDocument();
  });

  it("period tabs swap the row set", async () => {
    await openGovernance();
    expect(screen.getByText("bob")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "30 days" }));
    expect(screen.queryByText("bob")).not.toBeInTheDocument();
    expect(screen.getByText("alice")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "All time" }));
    expect(screen.getByText("bob")).toBeInTheDocument();
  });

  it("renders date formats, the freshness badge, and the action link", async () => {
    await openGovernance();

    expect(screen.getByText("2026-07-20")).toBeInTheDocument(); // date format trims time
    expect(screen.getByText(/data as of 2026-07-25 10:00/)).toBeInTheDocument();
    const action = screen.getByRole("link", { name: "Suggest a correction" });
    expect(action).toHaveAttribute("href", "https://example.test/correct");
  });
});

describe("Charts", () => {
  it("renders variant tabs and opens the lightbox with note and methodology", async () => {
    await openGovernance();

    expect(screen.getByRole("button", { name: "By year" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "By month" })).toBeInTheDocument();

    await userEvent.click(screen.getByAltText("Unique active contributors by role"));
    const lightbox = await screen.findByRole("dialog");
    expect(within(lightbox).getByText("How to read this chart.")).toBeInTheDocument();
    expect(within(lightbox).getByText("Step-by-step methodology")).toBeInTheDocument();
    expect(within(lightbox).getByText("Step two.")).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("Per-tab explainers", () => {
  it("each tab shows its own explainer and no other tab's", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "Governance" });

    await userEvent.click(screen.getByRole("button", { name: "Governance" }));
    await screen.findByText("Role holders");
    expect(screen.getByText("How to read this — what each column means")).toBeInTheDocument();
    expect(screen.queryByText("How to read this tab — what the numbers mean")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "HIPs" }));
    await screen.findByText("Implementation coverage matrix");
    expect(screen.getByText("How to read this tab — what the numbers mean")).toBeInTheDocument();
    expect(screen.queryByText("How to read this — what each column means")).not.toBeInTheDocument();
  });
});

describe("Cell formats", () => {
  it("renders a presence column as a labelled chip, not a bare tick", async () => {
    const { FormattedCell } = await import("../components/FormattedCell");
    const { container } = render(
      <>
        <FormattedCell value={true} format="presence" />
        <FormattedCell value={false} format="presence" />
      </>,
    );

    expect(container.textContent).toBe("presentmissing");
    expect(container.querySelector(".chip-merged")).toBeInTheDocument();
    expect(container.querySelector(".chip-none")).toBeInTheDocument();
  });
});

describe("KPI tiles", () => {
  it("expands an annotated tile into its note and derivation steps", async () => {
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Governance" }));
    await screen.findByText("Role holders");

    // A tile with an annotation is a button; one without stays inert.
    const tile = screen.getByRole("button", { name: /maintainers 103/ });
    await userEvent.click(tile);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("People whose highest role anywhere is maintainer.")).toBeInTheDocument();
    expect(within(dialog).getByText("Step-by-step methodology")).toBeInTheDocument();
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(3);

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /quiet teams 2/ })).not.toBeInTheDocument();
  });
});

describe("Resilience", () => {
  it("renders what loaded and names what did not, instead of blanking the tab", async () => {
    // The tab's only table 404s; its charts and tiles must survive it.
    vi.unstubAllGlobals();
    const { MANIFEST } = await import("./fixtures");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).endsWith("manifest.json")) return new Response(JSON.stringify(MANIFEST));
        if (String(url).endsWith("roles.json")) return new Response("gone", { status: 404 });
        return new Response("{}", { status: 200 });
      }),
    );

    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Governance" }));

    // The failure is named rather than silent or fatal…
    expect(await screen.findByText(/Could not load/)).toBeInTheDocument();
    expect(screen.getByText(/Role holders/)).toBeInTheDocument();
    // …while the rest of the tab still renders.
    expect(screen.getByText("Maintainer pipeline")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /maintainers 103/ })).toBeInTheDocument();
  });
});
