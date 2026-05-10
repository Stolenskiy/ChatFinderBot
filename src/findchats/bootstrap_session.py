from __future__ import annotations

import asyncio
import getpass

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from .config import settings


async def bootstrap_session() -> None:
    client = TelegramClient(settings.telegram_session_name, settings.telegram_api_id, settings.telegram_api_hash)
    await client.connect()

    if await client.is_user_authorized():
        print(f"Session '{settings.telegram_session_name}' is already authorized.")
        await client.disconnect()
        return

    phone = input("Enter phone number in international format (example +380...): ").strip()
    await client.send_code_request(phone)
    code = input("Enter the code from Telegram: ").strip()

    try:
        await client.sign_in(phone=phone, code=code)
    except SessionPasswordNeededError:
        password = getpass.getpass("Enter your Telegram 2FA password: ")
        await client.sign_in(password=password)

    print(f"Session '{settings.telegram_session_name}' saved successfully.")
    await client.disconnect()


def main() -> None:
    asyncio.run(bootstrap_session())


if __name__ == "__main__":
    main()
