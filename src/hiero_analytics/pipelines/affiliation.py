"""Build the organisation-diversity charts and tables for the org.

Reads the curated ``data/affiliations.yaml`` map and the org's governance config,
classifies every role-holder by employer (or independent / unknown), and writes a
set of org-scoped views per role tab (maintainers, committers) plus the
role-agnostic team views. Per role, suffixed ``_committers`` for the second tab:

- ``<role>_affiliations.csv`` — login, organisation, status (raw cross-reference)
- ``affiliation_distribution.csv`` / ``.png`` — distinct holders by organisation
- ``repo_affiliation_composition.csv`` / ``.png`` — per-repo employer mix
- ``repo_affiliation_diversity.csv`` and ``single_employer_repos_by_org.png``

Concentration (HHI, top-org share, coverage) is logged per role. Affiliation needs
no network beyond the governance config the other governance pipelines already
fetch, so this stays cheap and deterministic.
"""

from __future__ import annotations

import logging

from hiero_analytics.analysis.affiliation import (
    AFFILIATIONS_PATH,
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
    classify_role_holders,
    known_share_pct,
    load_affiliations,
    load_manual_logins,
    role_column,
    summarize_affiliation,
    top_n_with_other,
)
from hiero_analytics.analysis.contributor_heatmap import (
    build_activity_heatmap_dataframe,
    build_repo_activity_heatmap,
    build_team_activity_heatmap,
    grouped_heatmap_chart_data,
)
from hiero_analytics.config.analysis import AFFILIATION_MIN_KNOWN_SHARE_PCT
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.governance_config import (
    build_repo_role_lookup,
    build_team_membership,
    fetch_governance_config,
)
from hiero_analytics.domain.roles import highest_role_holders, highest_role_lookup
from hiero_analytics.export.save import plot_and_save, save_dataframe
from hiero_analytics.pipelines._shared import load_contributor_activity, shared_client
from hiero_analytics.plotting.bars import plot_bar, plot_stacked_bar
from hiero_analytics.plotting.heatmap import plot_heatmap
from hiero_analytics.plotting.pie import plot_pie

logger = logging.getLogger(__name__)

# The dashboard's role tabs, as (role, output-filename suffix). Maintainer keeps
# the bare filenames it has always had; every other role is suffixed, so adding a
# tab never renames an existing artifact.
ROLE_VARIANTS = [("maintainer", ""), ("committer", "_committers")]

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


def _pie_chart(
    distribution, label_col, value_col, center_label, title, output_path, *, top_n=6, donut=True, always_keep=()
):
    """Render a distribution as a pie/donut (top-N slices + 'Other'); skips empty frames."""
    folded = top_n_with_other(distribution, label_col, value_col, top_n=top_n, always_keep=always_keep)
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


def _distribution_chart(classified, data_dir, charts_dir, *, suffix, title, value_col):
    """Role-holders-by-organisation pie, including the unmapped as their own band."""
    distribution = build_affiliation_distribution(classified, value_col=value_col, include_unknown=True)
    save_dataframe(distribution, data_dir / f"affiliation_distribution{suffix}.csv")
    # A filled pie of the two largest employers + 'Other' — the concentration at a glance.
    # Unknown is pinned: it is usually too small to survive the fold, and the chart's
    # whole claim is that the unmapped are visible rather than quietly dropped.
    _pie_chart(
        distribution,
        "organisation",
        value_col,
        value_col,
        f"{title} — {known_share_pct(classified)}% have a known affiliation",
        charts_dir / f"affiliation_donut{suffix}.png",
        top_n=2,
        donut=False,
        always_keep=(UNKNOWN_LABEL,),
    )


def _repo_composition_chart(role_lookup, affiliations, data_dir, charts_dir, *, role, suffix, title):
    """Per-repo organisation-mix stacked bar for one role's holders."""
    composition, segments = build_repo_org_composition(role_lookup, affiliations, role=role)
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
            value_label=f"% of {role_column(role)}",
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


def _repo_diversity_views(role_lookup, affiliations, data_dir, charts_dir, *, role, suffix, title):
    """Per-repo diversity table plus its single-employer-repos-by-org companion chart."""
    diversity = build_repo_affiliation_diversity(role_lookup, affiliations, role=role)
    save_dataframe(diversity, data_dir / f"repo_affiliation_diversity{suffix}.csv")
    plot_and_save(
        build_single_employer_repo_counts(diversity, count_col=role_column(role)),
        plot_bar,
        output_path=charts_dir / f"single_employer_repos_by_org{suffix}.png",
        x_col="organisation",
        y_col="repos",
        title=title,
    )
    if not diversity.empty:
        logger.info(
            "Repo diversity (%s): %d of %d repos are single-employer (one org holds every seat)",
            role,
            int((diversity["distinct_orgs"] <= 1).sum()),
            len(diversity),
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


def _write_role_views(role, suffix, role_lookup, affiliations, manual_logins, data_dir, charts_dir, *, org):
    """Every org-scoped view for one governance role: reference table, donut, mixes."""
    holders = highest_role_holders(role_lookup, role)
    plural = role_column(role)
    logger.info("Resolved %d distinct %s from governance config", len(holders), plural)

    classified = classify_role_holders(holders, affiliations)
    # Flag how each affiliation was decided: a hand-correction (marked '# manual' in
    # the YAML) vs the automated resolver.
    classified["method"] = [
        "manual" if str(login).lower() in manual_logins else "automated" for login in classified["login"]
    ]
    save_dataframe(classified, data_dir / f"{role}_affiliations.csv")

    summary = summarize_affiliation(classified)
    known_share = known_share_pct(classified)
    logger.info(
        "Affiliation coverage (%s): %d affiliated, %d independent, %d unknown of %d (%d%% known)",
        role,
        summary.affiliated,
        summary.independent,
        summary.unknown,
        summary.total,
        known_share,
    )
    if holders and known_share < AFFILIATION_MIN_KNOWN_SHARE_PCT:
        logger.warning(
            "Affiliation curation for %s has decayed to %d%% known (floor %d%%): the %s diversity charts "
            "now describe a minority of the population — resolve unknowns in %s",
            role,
            known_share,
            AFFILIATION_MIN_KNOWN_SHARE_PCT,
            role,
            AFFILIATIONS_PATH,
        )
    logger.info(
        "Concentration (%s): HHI %d across %d employers; largest is %s at %d%%",
        role,
        summary.hhi,
        summary.distinct_orgs,
        summary.top_org,
        summary.top_share_pct,
    )

    # Per-repo views read the same disjoint population as the donut: a seat counts
    # here only when the holder has nothing more senior anywhere else.
    role_repos = highest_role_lookup(role_lookup, role)
    _distribution_chart(
        classified,
        data_dir,
        charts_dir,
        suffix=suffix,
        title=f"{org} — {role} organisation diversity (distinct {plural} by employer)",
        value_col=plural,
    )
    _repo_composition_chart(
        role_repos,
        affiliations,
        data_dir,
        charts_dir,
        role=role,
        suffix=suffix,
        title=f"{org} — {role} organisation mix by repository",
    )
    _repo_diversity_views(
        role_repos,
        affiliations,
        data_dir,
        charts_dir,
        role=role,
        suffix=suffix,
        title=f"{org} — repositories with a single {role} employer, by controlling organisation",
    )


def main(org: str = ORG) -> None:
    """Build the organisation-diversity outputs for ``org``."""
    org_data_dir, org_charts_dir = ensure_org_dirs(org)

    config = fetch_governance_config(org)
    role_lookup = build_repo_role_lookup(config)
    team_membership = build_team_membership(config)
    affiliations = load_affiliations()
    manual_logins = load_manual_logins()

    # One set of org-scoped views per role tab. Roles are resolved at each
    # person's *highest* role anywhere, so the populations are disjoint and agree
    # with the dashboard's role metric tiles — a committer here has write access
    # and no maintainer seat, which is what makes the two tabs comparable.
    for role, suffix in ROLE_VARIANTS:
        _write_role_views(
            role,
            suffix,
            role_lookup,
            affiliations,
            manual_logins,
            org_data_dir,
            org_charts_dir,
            org=org,
        )

    # Team views are role-agnostic (membership, not permissions), so they stay single-variant.
    _single_employer_chart(
        team_membership,
        affiliations,
        org_charts_dir,
        suffix="",
        title=f"{org} — single-employer governance teams, by controlling organisation",
    )
    _team_composition_chart(
        team_membership,
        affiliations,
        org_data_dir,
        org_charts_dir,
        suffix="",
        title=f"{org} — organisation mix by governance team (teams with 4+ resolved members)",
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
