/**
 * The contributor activity heatmap: a live-rendered slide inside the
 * "Activity heatmaps" slideshow, fed by API data instead of always being a
 * PNG (#333). Covers the live render, PNG fallback when the view fails, and
 * that it never renders twice (once live, once as a redundant standalone
 * card). The "no view produced for this org" case — the manifest simply
 * omitting the view — is covered at the Python layer
 * (tests/export/test_activity_views.py::test_view_is_absent_without_data);
 * this file exercises the frontend mechanism that consumes that omission,
 * via the "By team" slide, which never declares live_view_id at all.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { HEATMAP_DOC, stubApi } from "./fixtures";

beforeEach(() => {
  vi.unstubAllGlobals();
  Element.prototype.scrollIntoView = vi.fn();
});

const openContributors = async () => {
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Contributors" }));
  await screen.findByText("Activity heatmaps");
};

const activityHeatmapCard = () => screen.getByText("Activity heatmaps").closest(".card") as HTMLElement;

describe("Contributor activity heatmap — live slide", () => {
  it("renders live, inline as the slideshow's first slide, when the view loads", async () => {
    stubApi();
    await openContributors();
    const card = activityHeatmapCard();

    expect(within(card).getByRole("table")).toBeInTheDocument();
    expect(within(card).getByRole("rowheader", { name: "dana" })).toBeInTheDocument();
    expect(within(card).queryByRole("img", { name: "By contributor" })).not.toBeInTheDocument();
  });

  it("does not also render as its own standalone card — no duplicate", async () => {
    stubApi();
    await openContributors();

    // "Contributor activity heatmap" is the view's own title, only shown if
    // ViewCards rendered it standalone. The slideshow's card is titled
    // "Activity heatmaps"; the live slide's caption is "By contributor".
    expect(screen.queryByText("Contributor activity heatmap")).not.toBeInTheDocument();
  });

  it("falls back to the PNG when the view fetch fails, without breaking the slide", async () => {
    stubApi({
      "hiero-ledger/contributor-activity-heatmap.json": () => Promise.resolve(new Response("nope", { status: 500 })),
    });
    await openContributors();
    const card = activityHeatmapCard();

    expect(within(card).queryByRole("table")).not.toBeInTheDocument();
    expect(within(card).getByRole("img", { name: "By contributor" })).toBeInTheDocument();
  });

  it("shows the app's existing named-gap notice for the failed view, alongside the working PNG", async () => {
    stubApi({
      "hiero-ledger/contributor-activity-heatmap.json": () => Promise.resolve(new Response("nope", { status: 500 })),
    });
    await openContributors();

    // useViewDocs's own convention (a failed view is a named gap, not
    // silent) — this migration doesn't override that; it just also has a
    // PNG to show, checked in the test above.
    expect(await screen.findByText(/Could not load/)).toBeInTheDocument();
    expect(screen.getByText(/Contributor activity heatmap/)).toBeInTheDocument();
  });

  it("an ordinary slide with no live_view_id is unaffected by this change", async () => {
    stubApi();
    await openContributors();
    await userEvent.click(screen.getByRole("button", { name: /Next/ }));

    expect(await screen.findByRole("img", { name: "By team" })).toBeInTheDocument();
  });

  it("links to the static PNG from the live slide, since it's known to exist there", async () => {
    stubApi();
    await openContributors();
    const card = activityHeatmapCard();

    const link = within(card).getByRole("link", { name: "View as static image" });
    expect(link).toHaveAttribute("href", "/charts/org/hiero-ledger/contributor_activity_heatmap.png");
  });

  it("does not offer the static-image link on a failed slide — there is nothing live to link from", async () => {
    stubApi({
      "hiero-ledger/contributor-activity-heatmap.json": () => Promise.resolve(new Response("nope", { status: 500 })),
    });
    await openContributors();
    const card = activityHeatmapCard();

    expect(within(card).queryByRole("link", { name: "View as static image" })).not.toBeInTheDocument();
  });

  it("exposes the exact cell value for screen readers and hover on the live slide", async () => {
    stubApi();
    await openContributors();
    const card = activityHeatmapCard();

    const cell = within(card).getByTitle(`dana, ${HEATMAP_DOC.columns[0]}: ${HEATMAP_DOC.values[0][0]}`);
    expect(within(cell).getByText(String(HEATMAP_DOC.values[0][0]))).toBeInTheDocument();
  });
});
