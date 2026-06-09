"""Text normalization helpers for customer-facing language boundaries."""

from __future__ import annotations

import unicodedata

__all__ = ["searchable_text"]


def searchable_text(value: str) -> str:
    """Return lowercase, accent-insensitive text for matching and search.

    Customer messages and Brazilian catalog text often include accents, while
    operators or fixtures may omit them. Policy and lightweight catalog search
    should treat `devolução` and `devolucao` as the same signal without changing
    the original text used for prompts, audit records, or customer replies.
    """

    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(without_accents.casefold().split())
