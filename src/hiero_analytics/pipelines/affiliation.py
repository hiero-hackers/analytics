"""Build the maintainer organisation-diversity chart and tables for the org.

Reads the curated ``data/affiliations.yaml`` map and the org's governance config,
classifies every maintainer by employer (or independent / unknown), and writes:

- ``maintainer_affiliations.csv`` — login, organisation, status (raw cross-reference)
- ``affiliation_distribution.csv`` — organisation, maintainers (the chart's data)
- ``affiliation_distribution.png`` — distinct maintainers by organisation

Concentration (HHI, top-org share, coverage) is logged. Affiliation needs no
network beyond the governance config the other governance pipelines already fetch,
so this stays cheap and deterministic.
"""

from __future__ import annotations

import logging

from hiero_analytics.analysis.affiliation import (
    INDEPENDENT,
    OTHER_LABEL,
    UNKNOWN_LABEL,
    build_affiliation_distribution,
    build_org_activity_heatmap,
    build_repo_affiliation_diversity,
    build_repo_org_composition,
    build_single_employer_repo_counts,
    build_single_employer_team_counts,
    build_team_affiliation_diversity,
    build_team_org_composition,
    classify_maintainers,
    load_affiliations,
    load_manual_logins,
    summarize_affiliation,
    top_n_with_other,
)
from hiero_analytics.analysis.contributor_heatmap import (
    build_activity_heatmap_dataframe,
    build_repo_activity_heatmap,
    build_team_activity_heatmap,
    grouped_heatmap_chart_data,
)
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.governance_config import (
    build_repo_role_lookup,
    build_team_membership,
    fetch_governance_config,
)
from hiero_analytics.export.save import plot_and_save, save_dataframe
from hiero_analytics.pipelines._shared import load_contributor_activity, shared_client
from hiero_analytics.plotting.bars import plot_bar, plot_stacked_bar
from hiero_analytics.plotting.heatmap import plot_heatmap
from hiero_analytics.plotting.pie import plot_pie

logger = logging.getLogger(__name__)

# Neutral greys for the non-employer segments of the per-repo composition; named
# employers cycle through the categorical palette.
_SEGMENT_FIXED = {INDEPENDENT: "#94A3B8", OTHER_LABEL: "#CBD5E1", UNKNOWN_LABEL: "#E5E7EB"}
_SEGMENT_PALETTE = ["#F97316", "#0EA5E9", "#14B8A6", "#8B5CF6", "#EF4444", "#F59E0B", "#EC4899"]


def _composition_colors(segments: list[str]) -> dict[str, str]:
    """Fixed greys for non-employer segments; palette colours for the employers."""
    colors: dict[str, str] = {}
    cycle = 0
    for segment in segments:
        if segment in _SEGMENT_FIXED:
            colors[segment] = _SEGMENT_FIXED[segment]
        else:
            colors[segment] = _SEGMENT_PALETTE[cycle % len(_SEGMENT_PALETTE)]
            cycle += 1
    return colors


def _percent_rows(df, value_cols):
    """Copy of ``df`` with each row's ``value_cols`` rescaled to sum to 100 (percent)."""
    out = df.copy()
    totals = out[value_cols].sum(axis=1)
    totals = totals.where(totals != 0, 1)
    for col in value_cols:
        out[col] = out[col] / totals * 100
    return out


def _plot_grouped_heatmap(df, label_col, ylabel, filename, title, data_dir, charts_dir):
    """Save a grouped activity-heatmap CSV and render its top-N rows; returns row count."""
    save_dataframe(df, data_dir / f"{filename}.csv")
    chart = grouped_heatmap_chart_data(df, label_col)
    if chart is None:
        return 0
    values, row_labels, col_labels = chart
    plot_heatmap(
        values,
        row_labels=row_labels,
        col_labels=col_labels,
        output_path=charts_dir / f"{filename}.png",
        title=title,
        xlabel="Month",
        ylabel=ylabel,
        value_label="Weighted monthly activity score",
    )
    return len(row_labels)


def _pie_chart(distribution, label_col, value_col, center_label, title, output_path, *, top_n=6, donut=True):
    """Render a distribution as a pie/donut (top-N slices + 'Other'); skips empty frames."""
    folded = top_n_with_other(distribution, label_col, value_col, top_n=top_n)
    if folded.empty:
        return
    plot_pie(
        folded,
        label_col=label_col,
        value_col=value_col,
        title=title,
        output_path=output_path,
        center_label=center_label if donut else None,
        donut=donut,
    )


def _distribution_chart(login_set, affiliations, data_dir, charts_dir, *, suffix, title):
    """Maintainers-by-organisation donut for a population (all or the active subset)."""
    distribution = build_affiliation_distribution(classify_maintainers(login_set, affiliations))
    save_dataframe(distribution, data_dir / f"affiliation_distribution{suffix}.csv")
    # A filled pie of the two largest employers + 'Other' — the concentration at a glance.
    _pie_chart(
        distribution,
        "organisation",
        "maintainers",
        "maintainers",
        title,
        charts_dir / f"affiliation_donut{suffix}.png",
        top_n=2,
        donut=False,
    )


def _repo_composition_chart(role_lookup, affiliations, data_dir, charts_dir, *, suffix, title):
    """Per-repo organisation-mix stacked bar for a (possibly active-filtered) role lookup."""
    composition, segments = build_repo_org_composition(role_lookup, affiliations)
    if segments:
        save_dataframe(composition, data_dir / f"repo_affiliation_composition{suffix}.csv")
        plot_and_save(
            _percent_rows(composition, segments),
            plot_stacked_bar,
            output_path=charts_dir / f"repo_affiliation_composition{suffix}.png",
            x_col="repo",
            stack_cols=segments,
            labels=segments,
            colors=_composition_colors(segments),
            title=title,
            force_horizontal=False,
            rotate_x=90,
            annotate_totals=False,
            sort_categorical=False,
            value_label="% of maintainers",
            reference_value=50,
            reference_label="majority (50%)",
        )


def _team_composition_chart(team_membership, affiliations, data_dir, charts_dir, *, suffix, title):
    """Per-team organisation-mix stacked bar for a (possibly active-filtered) membership."""
    composition, segments = build_team_org_composition(team_membership, affiliations)
    if segments:
        save_dataframe(composition, data_dir / f"team_affiliation_composition{suffix}.csv")
        plot_and_save(
            _percent_rows(composition, segments),
            plot_stacked_bar,
            output_path=charts_dir / f"team_affiliation_composition{suffix}.png",
            x_col="team",
            stack_cols=segments,
            labels=segments,
            colors=_composition_colors(segments),
            title=title,
            force_horizontal=False,
            rotate_x=90,
            annotate_totals=False,
            sort_categorical=False,
            value_label="% of members",
            reference_value=50,
            reference_label="majority (50%)",
        )


def _single_employer_chart(team_membership, affiliations, charts_dir, *, suffix, title):
    """Single-employer teams by controlling org, as a bar (possibly active-filtered)."""
    diversity = build_team_affiliation_diversity(team_membership, affiliations)
    plot_and_save(
        build_single_employer_team_counts(diversity),
        plot_bar,
        output_path=charts_dir / f"single_employer_teams_by_org{suffix}.png",
        x_col="organisation",
        y_col="teams",
        title=title,
    )


def _single_employer_repo_chart(role_lookup, affiliations, charts_dir, *, suffix, title):
    """Single-employer repositories by controlling org, as a bar (possibly active-filtered)."""
    diversity = build_repo_affiliation_diversity(role_lookup, affiliations)
    plot_and_save(
        build_single_employer_repo_counts(diversity),
        plot_bar,
        output_path=charts_dir / f"single_employer_repos_by_org{suffix}.png",
        x_col="organisation",
        y_col="repos",
        title=title,
    )


def _write_activity_heatmaps(records, role_lookup, team_membership, affiliations, org_data_dir, org_charts_dir, *, org):
    """Activity heatmaps at three aggregation levels — by organisation, team, and repository.

    Reuses the contributor heatmap's weighting/windowing/bot-exclusion.
    """
    contributor_heatmap = build_activity_heatmap_dataframe(records, role_lookup)
    n_org = _plot_grouped_heatmap(
        build_org_activity_heatmap(contributor_heatmap, affiliations),
        "organisation",
        "Organisation",
        "org_activity_heatmap",
        f"{org} — organisation activity heatmap (weighted monthly activity)",
        org_data_dir,
        org_charts_dir,
    )
    _plot_grouped_heatmap(
        build_team_activity_heatmap(contributor_heatmap, team_membership),
        "team",
        "Team",
        "team_activity_heatmap",
        f"{org} — team activity heatmap (weighted monthly activity)",
        org_data_dir,
        org_charts_dir,
    )
    _plot_grouped_heatmap(
        build_repo_activity_heatmap(records),
        "repo",
        "Repository",
        "repo_activity_heatmap",
        f"{org} — repository activity heatmap (weighted monthly activity)",
        org_data_dir,
        org_charts_dir,
    )
    logger.info("Activity heatmaps: %d organisations, plus team and repository views", n_org)


def _write_activity_views(
    role_lookup,
    team_membership,
    affiliations,
    org_data_dir,
    org_charts_dir,
    *,
    org: str = ORG,
):
    """Activity-driven views: the per-org/team/repo activity heatmaps.

    Nothing else here is windowed: the diversity tables and charts are
    deliberately not time-filterable (diversity is a roster property, and
    windowing it mostly re-measures activity, which the activity views already
    show). Loads the (cached) org activity dataset once; skips quietly if no
    activity data is available.
    """
    client = shared_client()
    records = load_contributor_activity(client, org)
    if not records:
        logger.info("No activity data available; skipping activity heatmaps")
        return

    _write_activity_heatmaps(records, role_lookup, team_membership, affiliations, org_data_dir, org_charts_dir, org=org)


def main(org: str = ORG) -> None:
    """Build the maintainer organisation-diversity outputs for ``org``."""
    org_data_dir, org_charts_dir = ensure_org_dirs(org)

    config = fetch_governance_config(org)
    role_lookup = build_repo_role_lookup(config)
    team_membership = build_team_membership(config)
    maintainers = {user for holders in role_lookup.values() for user, role in holders.items() if role == "maintainer"}
    logger.info("Resolved %d distinct maintainers from governance config", len(maintainers))

    affiliations = load_affiliations()
    manual_logins = load_manual_logins()
    classified = classify_maintainers(maintainers, affiliations)
    # Flag how each affiliation was decided: a hand-correction (marked '# manual' in
    # the YAML) vs the automated resolver.
    classified["method"] = [
        "manual" if str(login).lower() in manual_logins else "automated" for login in classified["login"]
    ]
    save_dataframe(classified, org_data_dir / "maintainer_affiliations.csv")

    summary = summarize_affiliation(classified)
    logger.info(
        "Affiliation coverage: %d affiliated, %d independent, %d unknown of %d maintainers",
        summary["affiliated"],
        summary["independent"],
        summary["unknown"],
        summary["maintainers"],
    )
    logger.info(
        "Concentration: HHI %d across %d employers; largest is %s at %d%%",
        summary["hhi"],
        summary["distinct_orgs"],
        summary["top_org"],
        summary["top_share_pct"],
    )

    # All-population charts (the "All" tab in the dashboard).
    _distribution_chart(
        maintainers,
        affiliations,
        org_data_dir,
        org_charts_dir,
        suffix="",
        title=f"{org} — maintainer organisation diversity (distinct maintainers by employer)",
    )
    _repo_composition_chart(
        role_lookup,
        affiliations,
        org_data_dir,
        org_charts_dir,
        suffix="",
        title=f"{org} — maintainer organisation mix by repository",
    )
    _single_employer_chart(
        team_membership,
        affiliations,
        org_charts_dir,
        suffix="",
        title=f"{org} — single-employer governance teams, by controlling organisation",
    )
    _single_employer_repo_chart(
        role_lookup,
        affiliations,
        org_charts_dir,
        suffix="",
        title=f"{org} — single-employer repositories, by controlling organisation",
    )
    _team_composition_chart(
        team_membership,
        affiliations,
        org_data_dir,
        org_charts_dir,
        suffix="",
        title=f"{org} — organisation mix by governance team (teams with 4+ resolved members)",
    )

    # Per-repo and per-team diversity tables (with their headline counts logged).
    repo_diversity = build_repo_affiliation_diversity(role_lookup, affiliations)
    save_dataframe(repo_diversity, org_data_dir / "repo_affiliation_diversity.csv")
    if not repo_diversity.empty:
        logger.info(
            "Repo diversity: %d of %d repos are single-employer (one org holds all maintainer seats)",
            int((repo_diversity["distinct_orgs"] <= 1).sum()),
            len(repo_diversity),
        )
    team_diversity = build_team_affiliation_diversity(team_membership, affiliations)
    save_dataframe(team_diversity, org_data_dir / "team_affiliation_diversity.csv")
    if not team_diversity.empty:
        logger.info(
            "Team diversity: %d of %d teams are single-employer among resolved members (capture risk)",
            int(team_diversity["single_employer"].sum()),
            len(team_diversity),
        )

    # Activity-driven views: the org/team/repo activity heatmaps.
    _write_activity_views(
        role_lookup,
        team_membership,
        affiliations,
        org_data_dir,
        org_charts_dir,
        org=org,
    )

    logger.info("Organisation-diversity analytics complete")
