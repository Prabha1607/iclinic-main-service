"""Common string-processing utilities for LLM response handling.

Provides helpers that strip markdown/code-fence formatting from LLM output
and normalise text identifiers for comparison.
"""
import re

def clear_markdown(text: str) -> str:
    """Strip markdown and code-fence artefacts from an LLM response string.

    Removes triple-backtick code fences (including optional language tags),
    then trims any leading prose before the first JSON delimiter (``{`` or
    ``[``) and any trailing content after the last closing delimiter.

    Args:
        text: Raw LLM response string that may contain markdown formatting.

    Returns:
        Cleaned string suitable for JSON parsing.
    """
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
    """Normalise a text identifier to snake_case for consistent comparisons.

    Strips surrounding whitespace, lowercases the string, and replaces spaces
    and hyphens with underscores.

    Args:
        text: Raw identifier string.

    Returns:
        Normalised snake_case string.
    """
    return text.strip().lower().replace(" ", "_").replace("-", "_")
