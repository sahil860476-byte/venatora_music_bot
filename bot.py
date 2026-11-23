import os
import asyncio
import logging
from collections import defaultdict, deque

import yt_dlp
from pyrogram import Client, filters, idle
from pytgcalls import PyTgCalls, filters as call_filters
from pytgcalls.types import StreamEnded

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
SESSION = os.environ["SESSION"]

ADMIN_IDS = {6363076072}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VENATORA")

app = Client(
    "venatora_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user = Client(
    "venatora_user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION
)

call = PyTgCalls(user)

queues = defaultdict(deque)
current = {}
volumes = defaultdict(lambda: 100)
locks = defaultdict(asyncio.Lock)


def get_audio(query):
    options = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            query if query.startswith("http") else "ytsearch1:" + query,
            download=False
        )

        if "entries" in info:
            info = next(
                (x for x in info["entries"] if x),
                None
            )

        if not info:
            raise ValueError("Song nahi mila.")

        return {
            "url": info["webpage_url"],
            "title": info["title"],
            "duration": info.get("duration") or 0
        }


def get_stream_url(url):
    options = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        data = ydl.extract_info(url, download=False)

        return data["url"], data["title"]


async def prepare_song(query):
    return await asyncio.to_thread(get_audio, query)


async def start_song(chat_id, song):
    stream_url, title = await asyncio.to_thread(
        get_stream_url,
        song["url"]
    )

    await call.play(chat_id, stream_url)

    current[chat_id] = song

    return title


async def next_song(chat_id):
    async with locks[chat_id]:

        while queues[chat_id]:
            song = queues[chat_id].popleft()

            try:
                title = await start_song(chat_id, song)
                return title

            except Exception:
                logger.exception("Song playback failed")

        current.pop(chat_id, None)
        return None


@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply_text(
        "🎧 VENATORA MUSIC BOT\n\n"
        "PLAY • ENJOY • VIBE\n\n"
        "Commands:\n"
        "/play - Play song\n"
        "/pause - Pause music\n"
        "/resume - Resume music\n"
        "/skip - Next song\n"
        "/stop - Stop music\n"
        "/queue - Show queue\n"
        "/volume - Set volume"
    )


@app.on_message(filters.command("play") & filters.group)
async def play(_, message):

    if len(message.command) < 2:
        return await message.reply_text(
            "Usage: /play song name"
        )

    query = message.text.split(maxsplit=1)[1]

    status = await message.reply_text(
        "🔎 Searching song..."
    )

    try:
        song = await prepare_song(query)
        chat_id = message.chat.id

        if chat_id in current:
            queues[chat_id].append(song)

            await status.edit_text(
                f"➕ Added to queue:\n{song['title']}"
            )

        else:
            title = await start_song(chat_id, song)

            await status.edit_text(
                f"▶️ Now Playing:\n{title}"
            )

    except Exception as e:
        logger.exception("Play error")
        await status.edit_text(f"❌ Error: {e}")


@app.on_message(filters.command("pause") & filters.group)
async def pause(_, message):
    try:
        await call.pause(message.chat.id)
        await message.reply_text("⏸ Music paused.")

    except Exception as e:
        await message.reply_text(f"Error: {e}")


@app.on_message(filters.command("resume") & filters.group)
async def resume(_, message):
    try:
        await call.resume(message.chat.id)
        await message.reply_text("▶️ Music resumed.")

    except Exception as e:
        await message.reply_text(f"Error: {e}")


@app.on_message(filters.command("skip") & filters.group)
async def skip(_, message):

    chat_id = message.chat.id

    try:
        await call.leave_call(chat_id)
    except Exception:
        pass

    current.pop(chat_id, None)

    title = await next_song(chat_id)

    if title:
        await message.reply_text(
            f"⏭ Next song:\n{title}"
        )
    else:
        await message.reply_text(
            "Queue empty."
        )


@app.on_message(filters.command("stop") & filters.group)
async def stop(_, message):

    chat_id = message.chat.id

    try:
        await call.leave_call(chat_id)
    except Exception:
        pass

    current.pop(chat_id, None)
    queues[chat_id].clear()

    await message.reply_text(
        "⏹ Music stopped."
    )


@app.on_message(filters.command("queue") & filters.group)
async def queue(_, message):

    chat_id = message.chat.id

    text = "🎶 MUSIC QUEUE\n\n"

    if chat_id in current:
        text += f"▶️ Playing: {current[chat_id]['title']}\n\n"

    if queues[chat_id]:
        for i, song in enumerate(queues[chat_id], 1):
            text += f"{i}. {song['title']}\n"
    else:
        text += "Queue empty."

    await message.reply_text(text)


@app.on_message(filters.command("volume") & filters.group)
async def volume(_, message):

    chat_id = message.chat.id

    if len(message.command) < 2:
        return await message.reply_text(
            f"Current volume: {volumes[chat_id]}%"
        )

    try:
        value = int(message.command[1])

        if not 1 <= value <= 200:
            raise ValueError

        await call.change_volume_call(chat_id, value)

        volumes[chat_id] = value

        await message.reply_text(
            f"🔊 Volume: {value}%"
        )

    except ValueError:
        await message.reply_text(
            "Volume 1-200 ke beech rakho."
        )

    except Exception as e:
        await message.reply_text(f"Error: {e}")


@call.on_update(call_filters.stream_end())
async def stream_end_handler(_, update):

    chat_id = update.chat_id

    current.pop(chat_id, None)

    title = await next_song(chat_id)

    if title:
        await app.send_message(
            chat_id,
            f"▶️ Now Playing:\n{title}"
        )


async def main():

    await app.start()
    await user.start()
    await call.start()

    logger.info("VENATORA MUSIC BOT STARTED")

    await idle()

    await call.stop()
    await user.stop()
    await app.stop()


if __name__ == "__main__":
    app.run(main())
