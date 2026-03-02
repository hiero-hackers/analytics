def count_good_first_issues(issues: list[dict]) -> int:
    count = 0
    for issue in issues:
        labels = [
            label["name"].lower()
            for label in issue.get("labels", [])
        ]
        if "good first issue" in labels:
            count += 1
    return count