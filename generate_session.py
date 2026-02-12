#!/usr/bin/env python3
"""
One-time helper to generate a Telethon StringSession.

Run locally:
    pip install telethon
    python3 generate_session.py

Enter your phone number, then the code Telegram sends you.
The script prints a session string. Save it as a GitHub secret.
"""
import asyncio

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    api_id = input("Enter your Telegram API ID: ").strip()
    api_hash = input("Enter your Telegram API Hash: ").strip()

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.start()

    session_string = client.session.save()
    print("\n" + "=" * 50)
    print("Your session string (save as TELEGRAM_SESSION secret):")
    print("=" * 50)
    print(session_string)
    print("=" * 50)
    print("\nSTORE AS GITHUB SECRETS (never commit to code):")
    print("  TELEGRAM_SESSION  = the string above")
    print("  TELEGRAM_API_ID   = your API ID")
    print("  TELEGRAM_API_HASH = your API hash")
    print("\nSECURITY WARNING: This session string grants full access to")
    print("your Telegram account. Treat it like a password. If compromised,")
    print("revoke it at: Telegram Settings > Devices > Terminate session.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
