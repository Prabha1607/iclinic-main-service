def clear_markdown(raw: str) -> str:
    if raw.startswith("```"):
        return "\n".join(line for line in raw.splitlines() if "```" not in line).strip()
    return raw.strip()

def normalise(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("-", "_")
