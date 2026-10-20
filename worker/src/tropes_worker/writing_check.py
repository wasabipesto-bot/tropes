"""The post-check for generated prose: the tells listed in SPEC.md section 9."""

from __future__ import annotations

import re

RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"—|\s--\s"), "uses an em dash as a connector"),
    (re.compile(r"\bnot (just|merely|only)?\s*\w+[^.]{0,40}\bbut\b", re.I), "uses a 'not X but Y' contrast"),  # noqa: E501
    (
        re.compile(
            r"\b(added by hand|no reasoning|next scan|weak match|probably a miss|kept so you|calibration example|was approved|unverified|verified instance|this instance|the model|the scan|scored?\s+\d)\b",  # noqa: E501
            re.I,
        ),
        "talks about the process instead of the work",
    ),
    (
        re.compile(r"\b(testament to|tapestry|delve|underscores|a reminder that|speaks volumes|at its core,)\b", re.I),
        "inflated vocabulary",
    ),
    (re.compile(r"^\s*$"), "is empty"),
]


def complaints(text: str) -> list[str]:
    found = [msg for rx, msg in RULES if rx.search(text)]
    if text.count("||") % 2 == 1:
        found.append("has an unbalanced spoiler bar")
    if len(text.split()) > 90:
        found.append("runs past two sentences")
    return found
