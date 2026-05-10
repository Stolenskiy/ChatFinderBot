from __future__ import annotations

from unidecode import unidecode


KEYWORDS = [
    "chat",
    "group",
    "community",
    "forum",
    "чат",
    "группа",
    "група",
    "новости",
    "новини",
    "работа",
    "робота",
    "объявления",
    "оголошення",
    "барахолка",
    "market",
]


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


def generate_city_variants(city: str) -> list[str]:
    base = city.strip()
    transliterated = unidecode(base).strip()
    variants = [
        base,
        base.lower(),
        base.title(),
        transliterated,
        transliterated.lower(),
        transliterated.title(),
    ]

    query_variants = list(variants)
    for variant in variants:
        for keyword in KEYWORDS:
            query_variants.append(f"{variant} {keyword}")

    return _unique_keep_order(query_variants)


def normalized_needles(city: str) -> list[str]:
    variants = generate_city_variants(city)
    return _unique_keep_order([variant.casefold() for variant in variants])
