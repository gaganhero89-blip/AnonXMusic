# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import asyncio
import signal
import importlib
import os
from contextlib import suppress

from aiohttp import web

from anony import (anon, app, config, db, logger,
                   stop, thumb, userbot, yt)
from anony.plugins import all_modules


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KEEP-ALIVE SERVER
#  Render Web Service ke liye port open karna zaroori hai
#  Bina iske Render process kill kar deta hai
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def keep_alive():
    async def handle(request):
        return web.Response(
            text="<h2>Adam Music Bot is alive!</h2>",
            content_type="text/html"
        )

    async def health(request):
        return web.json_response({"status": "ok", "bot": "Adam Music Bot"})

    webapp = web.Application()
    webapp.router.add_get("/", handle)
    webapp.router.add_get("/health", health)

    runner = web.AppRunner(webapp)
    await runner.setup()

    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"[KeepAlive] Server started on port {port}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  IDLE — Wait for stop signal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def idle():
    loop       = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def main():
    # ── Keep-alive PEHLE start karo ──────────────────────
    # Render port scan karta hai deploy ke turant baad
    # Agar port late mile to "No open ports" error aata hai
    await keep_alive()

    # ── Bot startup (original same) ──────────────────────
    await db.connect()
    await app.boot()
    await userbot.boot()
    await anon.boot()
    await thumb.start()

    for module in all_modules:
        importlib.import_module(f"anony.plugins.{module}")
    logger.info(f"Loaded {len(all_modules)} modules.")

    if config.COOKIES_URL:
        await yt.save_cookies(config.COOKIES_URL)

    sudoers = await db.get_sudoers()
    app.sudoers.update(sudoers)
    app.bl_users.update(await db.get_blacklisted())
    logger.info(f"Loaded {len(app.sudoers)} sudo users.")

    await idle()
    await stop()


if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt:
        pass
      
