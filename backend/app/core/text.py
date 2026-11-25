def title_name(value: str) -> str:
    return " ".join(str(value or "").strip().split()).title()
