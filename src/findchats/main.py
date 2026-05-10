from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from telethon import TelegramClient

from .bot import build_dispatcher, run_bot
from .config import settings
from .discovery import TelegramChatDiscovery
from .logging_setup import setup_logging


LOGGER = logging.getLogger(__name__)


async def app() -> None:
    log_file = setup_logging(settings.bot_log_level, settings.bot_log_dir)
    LOGGER.info("bot_startup_initiated log_file=%s", log_file)

    bot = Bot(token=settings.bot_token)
    mtproto_client = TelegramClient(
        settings.telegram_session_name,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )

    await mtproto_client.connect()
    if not await mtproto_client.is_user_authorized():
        await mtproto_client.disconnect()
        LOGGER.error("mtproto_session_not_authorized session_name=%s", settings.telegram_session_name)
        raise RuntimeError(
            "MTProto session is not authorized. Run 'python -m findchats.bootstrap_session' first."
        )

    discovery = TelegramChatDiscovery(
        client=mtproto_client,
        search_limit_per_query=settings.search_limit_per_query,
        result_limit=settings.result_limit,
    )
    dispatcher = build_dispatcher(discovery)
    LOGGER.info(
        "bot_initialized session_name=%s search_limit_per_query=%s result_limit=%s",
        settings.telegram_session_name,
        settings.search_limit_per_query,
        settings.result_limit,
    )

    try:
        await run_bot(bot, dispatcher)
    finally:
        LOGGER.info("bot_shutdown_started")
        await bot.session.close()
        await mtproto_client.disconnect()
        LOGGER.info("bot_shutdown_completed")


def main() -> None:
    asyncio.run(app())


if __name__ == "__main__":
    main()
