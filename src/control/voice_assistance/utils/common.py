import re

def clear_markdown(text: str) -> str:
    # Strip code fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip("`").strip()
    # Find the first { or [ — discard any prose before it
    match = re.search(r"[{\[]", text)
    if match:
        text = text[match.start():]
    # Find the last } or ] — discard anything after it
    match = re.search(r"[}\]](?=[^}\]]*$)", text)
    if match:
        text = text[:match.end()]
    return text.strip()

def normalise(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("-", "_")
