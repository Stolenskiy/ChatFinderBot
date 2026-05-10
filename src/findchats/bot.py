from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import count

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .config import settings
from .discovery import TelegramChatDiscovery
from .models import SearchHit

LOGGER = logging.getLogger(__name__)
SEARCH_SEQUENCE = count(1)


@dataclass(slots=True)
class PaginatedSearchState:
    city: str
    search_id: int
    mode: str
    hits: list[SearchHit]
    next_page: int = 2
    created_at: datetime | None = None
    last_accessed_at: datetime | None = None


def build_dispatcher(discovery: TelegramChatDiscovery) -> Dispatcher:
    dispatcher = Dispatcher()
    search_semaphore = asyncio.Semaphore(1)
    background_tasks: set[asyncio.Task[None]] = set()
    pagination_state_by_user: dict[int, PaginatedSearchState] = {}
    page_state_ttl = timedelta(minutes=settings.page_state_ttl_minutes)

    @dispatcher.message(Command("start"))
    async def start(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        LOGGER.info("command_start user_id=%s chat_id=%s", user_id, message.chat.id)
        await message.answer(
            "Цей бот знаходить публічні Telegram-чати, пов'язані з містом.\n\n"
            "Команди:\n"
            "`/groups Київ` - знайти групи\n"
            "`/channels Київ` - знайти канали з linked groups\n"
            "`/nextpage` - наступна сторінка останнього пошуку\n"
            "`/help` - коротка довідка\n\n"
            "Також можна просто надіслати назву міста окремим повідомленням.",
            parse_mode="Markdown",
        )

    @dispatcher.message(Command("help"))
    async def help_command(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        LOGGER.info("command_help user_id=%s chat_id=%s", user_id, message.chat.id)
        await message.answer(
            "Як це працює:\n"
            "1. Бот приймає назву міста.\n"
            "2. Через MTProto client API шукає public groups/supergroups.\n"
            "3. Відкидає broadcast channels.\n"
            "4. Сортує результати за кількістю учасників.\n"
            "5. Пошук іде у фоні, результат прийде окремим повідомленням.\n\n"
            f"6. Перша сторінка містить до {settings.page_size} результатів, далі використовуй `/nextpage`.\n\n"
            "Приклади:\n"
            "`/groups Львів`\n"
            "`/channels Львів`\n"
            "`/groups Odesa`\n"
            "`/nextpage`",
            parse_mode="Markdown",
        )

    @dispatcher.message(Command("nextpage"))
    async def next_page(message: Message) -> None:
        user = message.from_user
        if user is None:
            await message.answer("Не вдалося визначити користувача для пагінації.")
            return

        _cleanup_expired_pagination_states(pagination_state_by_user, page_state_ttl)
        state = pagination_state_by_user.get(user.id)
        if state is None:
            LOGGER.info("command_nextpage_empty user_id=%s chat_id=%s", user.id, message.chat.id)
            await message.answer("Немає активного пошуку. Спочатку виконай `/groups Київ` або `/channels Київ`.", parse_mode="Markdown")
            return

        page_hits = _page_slice(state.hits, state.next_page)
        if not page_hits:
            LOGGER.info(
                "command_nextpage_no_more user_id=%s chat_id=%s search_id=%s city=%r requested_page=%s",
                user.id,
                message.chat.id,
                state.search_id,
                state.city,
                state.next_page,
            )
            await message.answer(
                f"Для пошуку <b>#{state.search_id}</b> по <b>{html.escape(state.city)}</b> більше сторінок немає.",
                parse_mode="HTML",
            )
            return

        LOGGER.info(
            "command_nextpage user_id=%s chat_id=%s search_id=%s city=%r page=%s page_hits=%s total_hits=%s",
            user.id,
            message.chat.id,
            state.search_id,
            state.city,
            state.next_page,
            len(page_hits),
            len(state.hits),
        )
        chunks = _render_hits(state.city, page_hits, state.search_id, state.next_page, len(state.hits), state.mode)
        for chunk in chunks:
            await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)
        state.next_page += 1
        state.last_accessed_at = _now_utc()

    @dispatcher.message(Command("groups"))
    async def groups(message: Message, command: CommandObject) -> None:
        city = (command.args or "").strip()
        if not city:
            await message.answer("Використання: `/groups Київ`", parse_mode="Markdown")
            return
        await _run_search(message, discovery, city, "groups", search_semaphore, background_tasks, pagination_state_by_user)

    @dispatcher.message(Command("channels"))
    async def channels(message: Message, command: CommandObject) -> None:
        city = (command.args or "").strip()
        if not city:
            await message.answer("Використання: `/channels Київ`", parse_mode="Markdown")
            return
        await _run_search(message, discovery, city, "channels", search_semaphore, background_tasks, pagination_state_by_user)

    @dispatcher.message(F.text & ~F.text.startswith("/"))
    async def search_from_text(message: Message) -> None:
        city = (message.text or "").strip()
        await _run_search(message, discovery, city, "groups", search_semaphore, background_tasks, pagination_state_by_user)

    @dispatcher.message(F.text.startswith("/"))
    async def unknown_command(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        LOGGER.info("command_unknown user_id=%s chat_id=%s text=%r", user_id, message.chat.id, message.text)
        await message.answer(_help_text("Невідома команда."), parse_mode="Markdown")

    return dispatcher


async def _run_search(message: Message, discovery: TelegramChatDiscovery, city: str) -> None:
    raise RuntimeError("This function should not be called directly anymore.")


def _schedule_search(
    message: Message,
    discovery: TelegramChatDiscovery,
    city: str,
    mode: str,
    semaphore: asyncio.Semaphore,
    background_tasks: set[asyncio.Task[None]],
    pagination_state_by_user: dict[int, PaginatedSearchState],
    page_state_ttl: timedelta,
) -> None:
    search_id = next(SEARCH_SEQUENCE)
    user_id = message.from_user.id if message.from_user else None
    _cleanup_expired_pagination_states(pagination_state_by_user, page_state_ttl)
    LOGGER.info("search_scheduled user_id=%s chat_id=%s search_id=%s city=%r mode=%s", user_id, message.chat.id, search_id, city, mode)

    async def runner() -> None:
        await message.answer(
            (
                f"Пошук <b>#{search_id}</b> для міста <b>{html.escape(city)}</b> запущено.\n"
                "Можеш продовжувати писати інші міста, а я надішлю результат окремим повідомленням, щойно закінчу пошук."
            ),
            parse_mode="HTML",
        )

        async with semaphore:
            try:
                LOGGER.info("search_started user_id=%s chat_id=%s search_id=%s city=%r", user_id, message.chat.id, search_id, city)
                hits = await (discovery.search_city(city) if mode == "groups" else discovery.search_city_channels(city))
            except Exception:  # pragma: no cover - protective boundary for bot UX
                LOGGER.exception("search_failed user_id=%s chat_id=%s search_id=%s city=%r mode=%s", user_id, message.chat.id, search_id, city, mode)
                await message.answer(
                    f"Пошук <b>#{search_id}</b> для <b>{html.escape(city)}</b> завершився помилкою.",
                    parse_mode="HTML",
                )
                return

        if not hits:
            if message.from_user is not None:
                pagination_state_by_user.pop(message.from_user.id, None)
            LOGGER.info("search_completed_empty user_id=%s chat_id=%s search_id=%s city=%r mode=%s", user_id, message.chat.id, search_id, city, mode)
            await message.answer(
                (
                    f"Пошук <b>#{search_id}</b> для <b>{html.escape(city)}</b> завершено.\n"
                    "Нічого релевантного не знайшов. Спробуй іншу форму назви міста або латиницю/кирилицю."
                ),
                parse_mode="HTML",
            )
            return

        if message.from_user is not None:
            timestamp = _now_utc()
            pagination_state_by_user[message.from_user.id] = PaginatedSearchState(
                city=city,
                search_id=search_id,
                mode=mode,
                hits=hits,
                created_at=timestamp,
                last_accessed_at=timestamp,
            )

        first_page_hits = _page_slice(hits, 1)
        LOGGER.info(
            "search_completed user_id=%s chat_id=%s search_id=%s city=%r mode=%s total_hits=%s first_page_hits=%s",
            user_id,
            message.chat.id,
            search_id,
            city,
            mode,
            len(hits),
            len(first_page_hits),
        )
        chunks = _render_hits(city, first_page_hits, search_id, 1, len(hits), mode)
        for chunk in chunks:
            await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)

    task = asyncio.create_task(runner())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


async def _run_search(
    message: Message,
    discovery: TelegramChatDiscovery,
    city: str,
    mode: str,
    semaphore: asyncio.Semaphore,
    background_tasks: set[asyncio.Task[None]],
    pagination_state_by_user: dict[int, PaginatedSearchState],
) -> None:
    _schedule_search(
        message,
        discovery,
        city,
        mode,
        semaphore,
        background_tasks,
        pagination_state_by_user,
        page_state_ttl=timedelta(minutes=settings.page_state_ttl_minutes),
    )


def _render_hits(city: str, hits: list[SearchHit], search_id: int, page: int, total_hits: int, mode: str) -> list[str]:
    total_pages = max(1, (total_hits + settings.page_size - 1) // settings.page_size)
    title = "Групи" if mode == "groups" else "Канали з linked groups"
    lines = [
        f"<b>{title} для пошуку #{search_id}:</b> {html.escape(city)}",
        f"<b>Page:</b> {page}/{total_pages}",
        f"<b>Total chats:</b> {total_hits}",
        "",
    ]
    base_index = (page - 1) * settings.page_size
    for index, hit in enumerate(hits, start=1):
        lines.extend(_render_single_hit(base_index + index, hit, mode))

    if page < total_pages:
        lines.append("Щоб отримати наступну сторінку, надішли `/nextpage`.")
        lines.append("")

    messages: list[str] = []
    current: list[str] = []
    current_length = 0
    for line in lines:
        projected = current_length + len(line) + 1
        if projected > 3500 and current:
            messages.append("\n".join(current))
            current = []
            current_length = 0
        current.append(line)
        current_length += len(line) + 1
    if current:
        messages.append("\n".join(current))
    return messages


def _page_slice(hits: list[SearchHit], page: int) -> list[SearchHit]:
    start = (page - 1) * settings.page_size
    end = start + settings.page_size
    return hits[start:end]


def _help_text(prefix: str | None = None) -> str:
    lines = []
    if prefix:
        lines.append(prefix)
        lines.append("")
    lines.extend(
        [
            "Доступні команди:",
            "`/groups Київ` - знайти групи",
            "`/channels Київ` - знайти канали з linked groups",
            "`/nextpage` - наступна сторінка останнього пошуку",
            "`/help` - коротка довідка",
            "",
            "Також можна просто надіслати назву міста окремим повідомленням.",
        ]
    )
    return "\n".join(lines)


def _cleanup_expired_pagination_states(
    pagination_state_by_user: dict[int, PaginatedSearchState],
    ttl: timedelta,
) -> None:
    now = _now_utc()
    expired_user_ids = [
        user_id
        for user_id, state in pagination_state_by_user.items()
        if (state.last_accessed_at or state.created_at or now) + ttl < now
    ]
    for user_id in expired_user_ids:
        pagination_state_by_user.pop(user_id, None)
    if expired_user_ids:
        LOGGER.info("pagination_state_cleanup removed_users=%s ttl_minutes=%s", len(expired_user_ids), int(ttl.total_seconds() // 60))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _render_single_hit(position: int, hit: SearchHit, mode: str) -> list[str]:
    if mode == "channels":
        return _render_channel_hit(position, hit)
    return _render_group_hit(position, hit)


def _render_group_hit(position: int, hit: SearchHit) -> list[str]:
    link_line = html.escape(hit.link) if hit.link else "немає прямого посилання"
    lines = [
        f"<b>{position}. {html.escape(hit.title)}</b>",
        f"Посилання на групу: {link_line}",
    ]
    if hit.members_count is not None:
        lines.append(f"Учасників: <code>{hit.members_count}</code>")
    lines.append("")
    return lines


def _render_channel_hit(position: int, hit: SearchHit) -> list[str]:
    channel_link = html.escape(hit.link) if hit.link else "немає прямого посилання"
    discussion_title = html.escape(hit.linked_chat_title or "not confirmed")
    status_raw = hit.channel_status or "unknown"
    status = html.escape({"confirmed": "підтверджено", "possible": "можливо", "unknown": "невідомо"}.get(status_raw, status_raw))
    lines = [
        f"<b>{position}. {html.escape(hit.title)}</b>",
        f"Статус: <code>{status}</code>",
        f"Посилання на канал: {channel_link}",
        f"Група обговорення: {discussion_title}",
    ]
    if hit.linked_chat_link:
        lines.append(f"Посилання на групу обговорення: {html.escape(hit.linked_chat_link)}")
    elif hit.channel_status == "possible":
        lines.append("Посилання на групу обговорення: не підтверджено")
    if hit.members_count is not None:
        lines.append(f"Учасників каналу: <code>{hit.members_count}</code>")
    lines.append("")
    return lines


async def run_bot(bot: Bot, dispatcher: Dispatcher) -> None:
    await dispatcher.start_polling(bot)
