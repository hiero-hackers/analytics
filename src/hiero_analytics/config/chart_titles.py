def label_yearly(label: str) -> str:
    return f"{label} per Year"


def label_total_by_repo(label: str) -> str:
    return f"{label} by Repository"


def pipeline(label_a: str, label_b: str) -> str:
    return f"{label_a} → {label_b} Pipeline"