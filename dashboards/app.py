"""Streamlit dashboard for Hiero analytics outputs.

Run with:
    streamlit run dashboards/app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from typing import Literal

from data_loader import has_dashboard_outputs, load_dashboard_data


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Hiero Analytics Dashboard",
    page_icon="📊",
    layout="wide",
)


@st.cache_data(ttl=300, show_spinner="Loading dashboard data...")
def _load_data(fallback_scope: Literal["repo", "org"]) -> dict[str, pd.DataFrame]:
    return load_dashboard_data(fallback_scope=fallback_scope)


def _empty(df: pd.DataFrame) -> bool:
    return df is None or df.empty


def _to_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    clean = df.copy()
    for col in columns:
        if col in clean.columns:
            clean[col] = pd.to_numeric(clean[col], errors="coerce")
    return clean


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("📊 Hiero Analytics Dashboard")

fallback_scope: Literal["repo", "org"] = "repo"

if not has_dashboard_outputs():
    fallback_scope = st.sidebar.radio(
        "Live fallback scope",
        options=["repo", "org"],
        index=0,
        help="Choose repository-only fallback for speed, or org-wide fallback for broader coverage.",
    )
    st.sidebar.info(
        f"No dashboard CSV files found.  "
        f"Fetching live GitHub API fallback data (**{fallback_scope}**)."
    )

page = st.sidebar.radio(
    "View",
    [
        "Onboarding Pipeline",
        "Issue Difficulty",
        "Repository Breakdown",
    ],
)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
data = _load_data(fallback_scope)

st.caption(f"Refresh dashboard to reload and check for new CSV files.")

if all(df.empty for df in data.values()):
    st.error(
        "No dashboard CSV files were found and live API fallback could not be loaded. "
        "Check network access and GitHub credentials."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

if page == "Onboarding Pipeline":
    st.header("🌱 Onboarding Pipeline")
    st.markdown(
        "Cumulative **Good First Issues (GFI)** and **Good First Issue Candidates (GFIC)** "
        "tracked by year, measuring the health of the contributor onboarding funnel."
    )

    pipeline = _to_numeric(data["gfi_pipeline"], ["gfi", "gfic", "year"])
    yearly = _to_numeric(data["gfi_yearly"], ["count", "year"])
    yearly_contrib = _to_numeric(data["gfic_yearly"], ["count", "year"])

    if _empty(pipeline):
        st.info("No pipeline data available in analytics/outputs/data.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total GFI", int(pipeline["gfi"].fillna(0).sum()))
        c2.metric("Total GFIC", int(pipeline["gfic"].fillna(0).sum()))
        c3.metric("Latest Year", int(pipeline["year"].max()))

        fig = px.line(
            pipeline,
            x="year",
            y=["gfi", "gfic"],
            markers=True,
            title="GFI and GFIC by Year",
            labels={"value": "Count", "year": "Year", "variable": "Series"},
        )
        st.plotly_chart(fig, width="stretch")

        if not _empty(yearly) and not _empty(yearly_contrib):
            merged = yearly.merge(
                yearly_contrib, on="year", how="outer", suffixes=("_gfi", "_gfic")
            ).fillna(0)
            fig = px.bar(
                merged,
                x="year",
                y=["count_gfi", "count_gfic"],
                barmode="group",
                title="Yearly GFI vs GFIC",
                labels={"value": "Count", "year": "Year", "variable": "Series"},
            )
            st.plotly_chart(fig, width="stretch")

        st.subheader("Raw Data")
        st.dataframe(pipeline, width="stretch")

elif page == "Issue Difficulty":
    st.header("🏷️ Issue Difficulty (Last 30 Days)")
    st.markdown(
        "Open issues from the Hiero organisation classified by difficulty label: "
        "**Good First Issue**, **Beginner**, **Intermediate**, **Advanced**, or **Unknown**."
    )

    dist = _to_numeric(data["difficulty_distribution"], ["count"])
    by_repo = _to_numeric(data["difficulty_by_repo"], [
        "Unknown", "Good First Issue", "Beginner", "Intermediate", "Advanced",
    ])

    if _empty(dist):
        st.info("No difficulty distribution data found.")
    else:
        col1, col2 = st.columns([2, 1])

        with col1:
            fig = px.bar(
                dist.sort_values("count", ascending=False),
                x="difficulty",
                y="count",
                color="difficulty",
                title="30-Day Issue Difficulty Distribution",
                labels={"count": "Issues", "difficulty": "Difficulty"},
            )
            st.plotly_chart(fig, width="stretch")

        with col2:
            fig = px.pie(
                dist,
                names="difficulty",
                values="count",
                title="Share by Difficulty",
            )
            st.plotly_chart(fig, width="stretch")

        if not _empty(by_repo):
            categories = ["Unknown", "Good First Issue", "Beginner", "Intermediate", "Advanced"]
            melted = by_repo.melt(
                id_vars="repo", value_vars=categories,
                var_name="difficulty", value_name="count",
            )
            melted = melted[melted["count"] > 0]
            top_repos = (
                melted.groupby("repo", as_index=False)["count"]
                .sum()
                .sort_values("count", ascending=False)
                .head(12)
            )
            fig = px.bar(
                melted[melted["repo"].isin(top_repos["repo"])],
                x="repo",
                y="count",
                color="difficulty",
                title="Difficulty Mix by Repository (Top 12 by volume)",
            )
            fig.update_layout(xaxis_tickangle=-35)
            st.plotly_chart(fig, width="stretch")

        st.subheader("Raw Data")
        st.dataframe(dist, width="stretch")

elif page == "Repository Breakdown":
    st.header("📦 Repository Breakdown")
    st.markdown(
        "Good First Issues and onboarding candidates broken down by repository, "
        "highlighting which repos have the most entry points for new contributors."
    )

    total = _to_numeric(data["gfi_total_by_repo"], ["count"])
    onboarding = _to_numeric(data["onboarding_repo_pipeline"], ["gfi", "gfic"])

    if _empty(total):
        st.info("No repo summary data found.")
    else:
        top_repos = total.sort_values("count", ascending=False).head(15)
        fig = px.bar(
            top_repos,
            x="repo",
            y="count",
            title="Top Repositories by Good First Issues",
            labels={"count": "GFI Count", "repo": "Repository"},
        )
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, width="stretch")

        if not _empty(onboarding):
            onboarding = onboarding.assign(
                total=onboarding["gfi"].fillna(0) + onboarding["gfic"].fillna(0)
            )
            onboarding_top = onboarding.sort_values("total", ascending=False).head(15)
            fig = px.bar(
                onboarding_top,
                x="repo",
                y=["gfi", "gfic"],
                barmode="group",
                title="GFI vs GFIC by Repository",
                labels={"value": "Count", "variable": "Series"},
            )
            fig.update_layout(xaxis_tickangle=-35)
            st.plotly_chart(fig, width="stretch")

        st.subheader("Raw Data")
        st.dataframe(total.sort_values("count", ascending=False), width="stretch")