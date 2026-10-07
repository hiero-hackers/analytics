# The register, by example

One paragraph three ways, then a model slot and a model Sources entry. The
numbers are from the 2026-10-06 manifest; the point is the shape.

## Before: the dashboard dump

> The `maintainer-pipeline` series counts each person once per bucket, under
> the highest governance role they hold in any repository, with bots
> excluded. Buckets must not be added across periods to get unique people.
> The number of active people rose in every tier between 2024 and 2025. The
> Governance tiles count 104 maintainers, 130 committers and 7 triage holders
> (241 permission holders). Of the 104 maintainers, 80 had tracked activity
> in 2026 to 6 October (derived by comparing the tile with the yearly
> bucket). The quiet permission-holders tile reports 98 role holders with no
> tracked activity for 180 days or more, and the `gonedark` table, `365d`
> period, lists 81 people with none in a year.
>
> Source: Governance tiles "maintainers", "committers", "triage"; chart
> `maintainer-pipeline`, All time variant (`maintainer_pipeline_yearly`);
> section `gonedark`, `365d` period (81 rows; all-time 14). JSON:
> `BASE/hiero-ledger/charts/maintainer_pipeline_yearly.json` ...

What is wrong: four identifiers, a counting rule explained in the body, a
derivation flagged in the body, eleven numbers in one paragraph, a Source
line a TAC reader cannot use.

## After: the filed-review register

> More people were active in the project in 2025 than in any earlier year.
> [Seventy-five maintainers](https://hiero-hackers.github.io/analytics/#tab=Governance&org=hiero-ledger&widget=maintainer-pipeline)
> contributed during 2025, up from 57 in 2024, and the committer and general
> contributor tiers grew with them [3]. The bench of people who hold a role
> is wider than the bench that uses it: of the
> [104 maintainers](https://hiero-hackers.github.io/analytics/#tab=Governance&org=hiero-ledger&widget=roles)
> on the governance rolls, 80 were active in 2026 to 6 October, and 81 role
> holders of all kinds had no tracked activity in the trailing year [4].
> Counts are GitHub accounts, not people.

Three sentences, five numbers, two links, two source numbers, one caveat
that changes the reading. The counting rule, the all-time versus 365-day
distinction and the derivation live in the appendices.

## A slot

> \> [MAINTAINER INPUT] What is being done about maintainer and contributor
> diversity.
> \>
> \> Evidence in this draft: Maintainer Diversity (employer shares, the
> single-employer repositories), Figure 1 (active contributors by role),
> Figure 3 (maintainers by employer).

## A Sources entry

```
[3] Chart maintainer-pipeline, All time variant (maintainer_pipeline_yearly); data as of 2026-10-06. JSON: BASE/hiero-ledger/charts/maintainer_pipeline_yearly.json. Dashboard: https://hiero-hackers.github.io/analytics/#tab=Governance&org=hiero-ledger&widget=maintainer-pipeline
[4] Section gonedark, 365d period table (81 rows; 14 all time); data as of 2026-10-06. JSON: BASE/hiero-ledger/gonedark.json. Dashboard: https://hiero-hackers.github.io/analytics/#tab=Governance&org=hiero-ledger&widget=gonedark
```

## A Data notes entry

```
- Role holders versus active: the Governance tiles count 104 maintainers,
  130 committers and 7 triage, each person once at their highest role; the
  active-by-role series (maintainer_pipeline_yearly) counts distinct people
  active per year on the same rule, so 80 of 104 maintainers active in 2026
  is a derivation across the two. Buckets are never summed across periods.
- gonedark 365d table: 81 rows; the all-time table has 14. The 365d table
  is the one cited (annual period).
```
