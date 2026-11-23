import os
import asyncio
import sqlite3
import logging

from collections import defaultdict, deque
from contextlib import closing

import yt_dlp

from pyrogram import Client, filters, idle, enums
from pyrogram.errors import FloodWait, RPCError
from pytgcalls import PyTgCalls, filters as call_filters
from pytgcalls.types import MediaStream, StreamEnded


# ==========================================
# VENATORA CONFIGURATION
# ==========================================

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
SESSION = os.environ["SESSION"]

ADMIN_IDS = [6363076072]

BOT_NAME = "VENATORA MUSIC BOT"
TAGLINE = "PLAY • ENJOY • VIBE"

DB_PATH = os.getenv("DB_PATH", "venatora.db")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VENATORA")


# ==========================================
# CLIENTS
# ==========================================

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


# ==========================================
# DATABASE
# ==========================================

def init_db():
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                chat_type TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()


def register_chat(chat_id, chat_type):
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.execute(
            """
            INSERT OR IGNORE INTO chats (chat_id, chat_type)
            VALUES (?, ?)
            """,
            (chat_id, chat_type)
        )
        db.commit()


def get_registered_chats():
    with closing(sqlite3.connect(DB_PATH)) as db:
        return db.execute(
            "SELECT chat_id FROM chats"
        ).fetchall()


# ==========================================
# AUTOMATIC CHAT REGISTRATION
# ==========================================

@app.on_message(
    filters.private | filters.group,
    group=-1
)
async def track_chats(_, message):

    if message.chat.type == enums.ChatType.PRIVATE:
        chat_type = "private"

    else:
        chat_type = "group"

    register_chat(message.chat.id, chat_type)


# ==========================================
# MUSIC DATA
# ==========================================

queues = defaultdict(deque)
current = {}
volumes = defaultdict(lambda: 100)
playing_locks = defaultdict(asyncio.Lock)


# ==========================================
# YOUTUBE HELPERS
# ==========================================

def get_audio(query):

    opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True
    }

    q = query if query.startswith("http") else "ytsearch1:" + query

    with yt_dlp.YoutubeDL(opts) as ydl:

        info = ydl.extract_info(q, download=False)

        if "entries" in info:
            info = info["entries"][0]

        return {
            "url": info["webpage_url"],
            "title": info["title"],
            "duration": info.get("duration") or 0
        }


async def prepare_song(query):
    return await asyncio.to_thread(get_audio, query)


def get_stream_url(page_url):

    opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True
    }

    with yt_dlp.YoutubeDL(opts) as ydl:

        data = ydl.extract_info(page_url, download=False)

        return (
            data["url"],
            data["title"],
            data.get("duration") or 0
        )


# ==========================================
# PLAY SONG
# ==========================================

async def play_song(chat_id, song):

    stream_url, title, duration = await asyncio.to_thread
