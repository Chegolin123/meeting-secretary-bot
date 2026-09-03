"""Точка входа: python -m secretary.bot."""

import asyncio

from secretary.bot.main import main

if __name__ == "__main__":
    asyncio.run(main())