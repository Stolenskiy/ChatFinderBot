from __future__ import annotations

import logging
from collections.abc import Iterable

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel, Chat

from .analytics import KeywordAnalyticsCollector
from .city_variants import SearchQueryVariant, generate_search_queries, normalized_needles
from .models import SearchHit

LOGGER = logging.getLogger(__name__)


class TelegramChatDiscovery:
    def __init__(self, client: TelegramClient, search_limit_per_query: int, analytics: KeywordAnalyticsCollector) -> None:
        self._client = client
        self._search_limit_per_query = search_limit_per_query
        self._analytics = analytics

    async def search_city(self, city: str) -> list[SearchHit]:
        return await self._search(city, include_groups=True, include_channels=False)

    async def search_city_channels(self, city: str) -> list[SearchHit]:
        return await self._search(city, include_groups=False, include_channels=True)

    async def _search(self, city: str, include_groups: bool, include_channels: bool) -> list[SearchHit]:
        queries = generate_search_queries(city)
        needles = normalized_needles(city)
        hits_by_chat_id: dict[int, SearchHit] = {}
        LOGGER.info(
            "search_city_started city=%r query_count=%s include_groups=%s include_channels=%s",
            city,
            len(queries),
            include_groups,
            include_channels,
        )

        for index, query_variant in enumerate(queries, start=1):
            try:
                found = await self._client(SearchRequest(q=query_variant.query, limit=self._search_limit_per_query))
            except RPCError as error:
                LOGGER.warning("SearchRequest failed for query '%s': %s", query_variant.query, error)
                continue

            LOGGER.info("search_query_completed city=%r query=%r chat_count=%s", city, query_variant.query, len(found.chats))

            query_accepted_hit_count = 0
            query_duplicate_hit_count = 0
            query_new_unique_hit_count = 0

            for entity in found.chats:
                hit = await self._build_hit(entity, needles, include_groups=include_groups, include_channels=include_channels)
                if hit is None:
                    continue

                query_accepted_hit_count += 1

                existing = hits_by_chat_id.get(hit.chat_id)
                if existing is None or hit.relevance_score > existing.relevance_score:
                    if existing is None:
                        query_new_unique_hit_count += 1
                    else:
                        query_duplicate_hit_count += 1
                    hits_by_chat_id[hit.chat_id] = hit
                elif existing is not None:
                    query_duplicate_hit_count += 1
                    existing.matched_by = sorted(set(existing.matched_by + hit.matched_by))

            self._analytics.record_query_event(
                {
                    "city": city,
                    "mode": "groups" if include_groups else "channels",
                    "query": query_variant.query,
                    "query_index": index,
                    "base_variant": query_variant.base_variant,
                    "keyword": query_variant.keyword,
                    "query_kind": query_variant.kind,
                    "raw_chat_count": len(found.chats),
                    "accepted_hit_count": query_accepted_hit_count,
                    "new_unique_hit_count": query_new_unique_hit_count,
                    "duplicate_hit_count": query_duplicate_hit_count,
                }
            )

        ranked_hits = sorted(
            hits_by_chat_id.values(),
            key=lambda item: (item.members_count or 0, item.relevance_score, item.title.casefold()),
            reverse=True,
        )
        LOGGER.info(
            "search_city_completed city=%r returned_hits=%s include_groups=%s include_channels=%s",
            city,
            len(ranked_hits),
            include_groups,
            include_channels,
        )
        return ranked_hits

    async def _build_hit(
        self,
        entity: Channel | Chat,
        needles: Iterable[str],
        *,
        include_groups: bool,
        include_channels: bool,
    ) -> SearchHit | None:
        if isinstance(entity, Channel):
            if entity.broadcast:
                if include_channels:
                    return await self._build_channel_hit(entity, needles)
                if include_groups:
                    return await self._resolve_linked_discussion_hit(entity, needles)
                return None

            if not include_groups:
                return None

            hit = SearchHit(
                chat_id=entity.id,
                title=entity.title,
                chat_type="supergroup",
                username=getattr(entity, "username", None),
                link=self._build_link(username=getattr(entity, "username", None), invite_link=None),
                description=None,
                is_forum=bool(getattr(entity, "forum", False)),
                members_count=getattr(entity, "participants_count", None),
            )
            hit.relevance_score, hit.matched_by = self._score_hit(hit, needles)
            return hit if hit.relevance_score > 0 else None

        if isinstance(entity, Chat):
            if not include_groups:
                return None
            hit = SearchHit(
                chat_id=entity.id,
                title=entity.title,
                chat_type="group",
                link=None,
                description=None,
                members_count=getattr(entity, "participants_count", None),
            )
            hit.relevance_score, hit.matched_by = self._score_hit(hit, needles)
            return hit if hit.relevance_score > 0 else None

        return None

    async def _resolve_linked_discussion_hit(self, entity: Channel, needles: Iterable[str]) -> SearchHit | None:
        full = await self._safe_get_full_channel(entity)
        linked_entity = self._extract_linked_entity(full)
        if linked_entity is None:
            return None

        linked_hit = await self._build_hit(linked_entity, needles, include_groups=True, include_channels=False)
        if linked_hit is None:
            return None

        linked_hit.matched_by = sorted(set(linked_hit.matched_by + ["linked_discussion_from_channel"]))
        return linked_hit

    async def _build_channel_hit(self, entity: Channel, needles: Iterable[str]) -> SearchHit | None:
        full = await self._safe_get_full_channel(entity)
        if full is None:
            hit = SearchHit(
                chat_id=entity.id,
                title=entity.title,
                chat_type="channel_possible_discussion",
                username=getattr(entity, "username", None),
                link=self._build_link(username=getattr(entity, "username", None), invite_link=None),
                members_count=getattr(entity, "participants_count", None),
                channel_status="possible",
            )
            hit.relevance_score, hit.matched_by = self._score_hit(hit, needles)
            if hit.relevance_score > 0:
                hit.matched_by = sorted(set(hit.matched_by + ["full_info_unavailable"]))
                return hit
            return None

        linked_entity = self._extract_linked_entity(full)
        if linked_entity is None:
            return None

        discussion_title = getattr(linked_entity, "title", None)
        discussion_username = getattr(linked_entity, "username", None)
        discussion_link = self._build_link(username=discussion_username, invite_link=None)
        hit = SearchHit(
            chat_id=entity.id,
            title=entity.title,
            chat_type="channel_with_discussion",
            username=getattr(entity, "username", None),
            link=self._build_link(username=getattr(entity, "username", None), invite_link=None),
            members_count=getattr(entity, "participants_count", None),
            linked_chat_title=discussion_title,
            linked_chat_link=discussion_link,
            channel_status="confirmed",
        )
        hit.relevance_score, hit.matched_by = self._score_hit(hit, needles)
        if hit.relevance_score == 0 and discussion_title:
            discussion_probe = SearchHit(
                chat_id=0,
                title=discussion_title,
                chat_type="group",
                username=discussion_username,
            )
            hit.relevance_score, hit.matched_by = self._score_hit(discussion_probe, needles)
        if hit.relevance_score > 0:
            hit.matched_by = sorted(set(hit.matched_by + ["has_linked_discussion"]))
            return hit
        return None

    async def _safe_get_full_channel(self, entity: Channel):
        try:
            return await self._client(GetFullChannelRequest(channel=entity))
        except RPCError as error:
            LOGGER.debug("GetFullChannelRequest failed for %s: %s", entity.id, error)
            return None

    def _score_hit(self, hit: SearchHit, needles: Iterable[str]) -> tuple[float, list[str]]:
        title = (hit.title or "").casefold()
        description = (hit.description or "").casefold()
        username = (hit.username or "").casefold()

        score = 0.0
        matched_by: list[str] = []

        for needle in needles:
            if not needle:
                continue
            if title == needle:
                score = max(score, 1.0)
                matched_by.append("title_exact")
            elif needle in title:
                score = max(score, 0.85)
                matched_by.append("title_contains")

            if username and needle in username:
                score = max(score, 0.70)
                matched_by.append("username_contains")

            if description and needle in description:
                score = max(score, 0.55)
                matched_by.append("description_contains")

        if hit.link:
            score += 0.05
            matched_by.append("has_link")

        return min(score, 1.0), sorted(set(matched_by))

    @staticmethod
    def _extract_linked_entity(full) -> Channel | Chat | None:
        full_chat = getattr(full, "full_chat", None)
        linked_chat_id = getattr(full_chat, "linked_chat_id", None)
        if not isinstance(linked_chat_id, int):
            return None

        for candidate in getattr(full, "chats", []) or []:
            if getattr(candidate, "id", None) == linked_chat_id:
                return candidate
        return None

    @staticmethod
    def _build_link(username: str | None, invite_link: str | None) -> str | None:
        if username:
            return f"https://t.me/{username}"
        if invite_link:
            return invite_link
        return None
