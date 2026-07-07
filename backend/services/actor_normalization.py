"""Shared actor and country normalization helpers for GDELT queries."""

from __future__ import annotations

import re


ACTOR_ALIASES = {
    "U.S.": "UNITED STATES",
    "US": "UNITED STATES",
    "USA": "UNITED STATES",
    "U.S.A.": "UNITED STATES",
    "AMERICA": "UNITED STATES",
    "UNITED STATES OF AMERICA": "UNITED STATES",
    "CAN": "CANADA",
    "CA": "CANADA",
    "MEX": "MEXICO",
    "MX": "MEXICO",
}

ACTOR_COUNTRY_CODE = {
    "CA": "CAN",
    "CANADA": "CAN",
    "CAN": "CAN",
    "US": "USA",
    "U.S.": "USA",
    "USA": "USA",
    "U.S.A.": "USA",
    "UNITED STATES": "USA",
    "UNITED STATES OF AMERICA": "USA",
    "AMERICA": "USA",
    "MX": "MEX",
    "MEX": "MEX",
    "MEXICO": "MEX",
}

COUNTRY_NAME_TO_CODE = {
    "CANADA": "CA",
    "CA": "CA",
    "CAN": "CA",
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "USA": "US",
    "U.S.": "US",
    "US": "US",
    "AMERICA": "US",
    "MEXICO": "MX",
    "MEX": "MX",
    "MX": "MX",
}


def normalize_actor_name(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"\s+", " ", value.strip().upper())
    normalized = normalized.replace("UNITED STATES GOVERNMENT", "UNITED STATES")
    return ACTOR_ALIASES.get(normalized, normalized)


def actor_alias_terms(value: str | None) -> list[str]:
    normalized = normalize_actor_name(value)
    if not normalized:
        return []
    aliases = {normalized}
    for alias, canonical in ACTOR_ALIASES.items():
        if canonical == normalized:
            aliases.add(alias)
    return sorted(aliases)


def actor_country_code(value: str | None) -> str | None:
    if not value:
        return None
    return ACTOR_COUNTRY_CODE.get(value.strip().upper())


def action_geo_country_code(value: str | None) -> str | None:
    if not value:
        return None
    return COUNTRY_NAME_TO_CODE.get(value.strip().upper())
