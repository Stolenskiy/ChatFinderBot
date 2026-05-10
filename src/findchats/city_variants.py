from __future__ import annotations

from dataclasses import dataclass

from unidecode import unidecode


KEYWORDS = [
    "chat",
    "group",
    "community",
    "forum",
    "группа",
    "група",
    "city",
    "events",
    "новости",
    "jobs",
    "job",
    "work",
    "работа",
    "робота",
    "объявления",
    "барахолка",
    "market",
    "people",
    "life",
    "help",
]

@dataclass(frozen=True, slots=True)
class SearchQueryVariant:
    query: str
    base_variant: str
    keyword: str | None
    kind: str


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _base_city_variants(city: str) -> list[str]:
    base = city.strip()
    transliterated = unidecode(base).strip()
    return _unique_keep_order(
        [
            base,
            base.lower(),
            base.title(),
            transliterated,
            transliterated.lower(),
            transliterated.title(),
        ]
    )


def generate_city_variants(city: str) -> list[str]:
    return [variant.query for variant in generate_search_queries(city)]


def generate_search_queries(city: str) -> list[SearchQueryVariant]:
    variants = _base_city_variants(city)
    items: list[SearchQueryVariant] = []
    seen_queries: set[str] = set()

    def add(query: str, base_variant: str, keyword: str | None, kind: str) -> None:
        normalized = query.strip()
        if not normalized:
            return
        key = normalized.casefold()
        if key in seen_queries:
            return
        seen_queries.add(key)
        items.append(SearchQueryVariant(query=normalized, base_variant=base_variant, keyword=keyword, kind=kind))

    for variant in variants:
        add(variant, variant, None, "base")

    for variant in variants:
        for keyword in KEYWORDS:
            add(f"{variant} {keyword}", variant, keyword, "keyword")

    return items


def normalized_needles(city: str) -> list[str]:
    variants = _base_city_variants(city)
    return _unique_keep_order([variant.casefold() for variant in variants])
