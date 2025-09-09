# bot.py
"""
Telegram ID Bot (python-telegram-bot v13.15)
Features:
 - /start, /myid, /whoami, /ping
 - Forwarded message -> UR ID / FORWARDED ID
 - Copy my ID button
 - SQLite storage for users/chats/meta/admins/broadcasts
 - Owner (set) + admins (managed by owner)
 - Admin commands: /stats, /listusers, /export, /ban, /unban, /kick
 - Owner-only: /broadcast, /addadmin, /removeadmin, /listadmins
Usage:
 - Provide your token via environment variable TG_BOT_TOKEN
 - Run: python bot.py
"""

import os
import logging
import html
import sqlite3
import time
import threading
import csv
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ParseMode,
    BotCommand,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    CallbackContext,
)

# ---------- CONFIG ----------
TOKEN = os.environ.get("TG_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Please set TG_BOT_TOKEN environment variable before running the bot.")

# Your owner id (you gave this earlier)
OWNER_ID: Optional[int] = 8116152355
OWNER_USERNAME = ""  # optional: your @username without @

DB_FILE = "botdata.db"
BROADCAST_DELAY_SEC = 0.12  # delay between broadcast messages

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- DB ----------
def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            lang_code TEXT,
            last_seen INTEGER
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            type TEXT,
            last_seen INTEGER
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER,
            from_user INTEGER,
            text TEXT,
            sent_count INTEGER
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            ts INTEGER
        )"""
    )
    conn.commit()
    return conn

DB = init_db()
DB_LOCK = threading.Lock()

def db_set_meta(key: str, value: str):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
        DB.commit()

def db_get_meta(key: str) -> Optional[str]:
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

def save_user(user):
    if not user:
        return
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, lang_code, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
            (
                user.id,
                user.username or "",
                user.first_name or "",
                user.last_name or "",
                getattr(user, "language_code", "") or "",
                int(time.time()),
            ),
        )
        DB.commit()

def save_chat(chat):
    if not chat:
        return
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO chats (chat_id, title, type, last_seen) VALUES (?, ?, ?, ?)",
            (chat.id, getattr(chat, "title", "") or getattr(chat, "username", "") or "", chat.type, int(time.time())),
        )
        DB.commit()

def add_admin(user_id: int, added_by: Optional[int] = None):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("INSERT OR REPLACE INTO admins (user_id, added_by, ts) VALUES (?, ?, ?)", (user_id, added_by or 0, int(time.time())))
        DB.commit()

def remove_admin(user_id: int):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        DB.commit()

def list_admins():
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("SELECT user_id, added_by, ts FROM admins")
        rows = cur.fetchall()
    return rows

def is_admin(user_id: int) -> bool:
    if OWNER_ID and user_id == OWNER_ID:
        return True
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return cur.fetchone() is not None

def get_stats():
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM chats")
        chats = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM broadcasts")
        broadcasts = cur.fetchone()[0]
    return {"users": users, "chats": chats, "broadcasts": broadcasts}

# ensure owner in admins table
if OWNER_ID:
    add_admin(OWNER_ID, added_by=0)

# ---------- Helpers ----------
def esc(text: str) -> str:
    return html.escape(str(text))

# ---------- Handlers ----------
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    if not user:
        return
    save_user(user)
    if OWNER_ID and user.id == OWNER_ID:
        add_admin(user.id, added_by=0)

    name = esc(user.first_name or user.username or "there")
    text = (
        f"👋 Hello <b>{name}</b>!\n\n"
        "🔹 <b>IDFinderBot</b> — your quick tool to get IDs on Telegram.\n\n"
        "✨ <b>Commands</b>\n"
        "• /myid — Show your User ID & Chat ID\n"
        "• /whoami — Full details about you\n"
        "• /ping — Test bot response\n"
        "• /stats — Bot statistics (Admins)\n"
        "• /broadcast — Send to all users (Owner)\n\n"
        "📌 Forward any message here to reveal:\n"
        "▫️ <b>UR ID</b>\n▫️ <b>FORWARDED ID</b>\n\n"
        "⚡ Fast • 📱 Simple • 🎨 Clean"
    )

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📋 Copy My ID", callback_data="copy_id"),
                InlineKeyboardButton("🆔 Get My ID", callback_data="cmd_myid"),
            ],
            [InlineKeyboardButton("ℹ️ Help", callback_data="cmd_help")],
        ]
    )

    update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

def myid_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return
    save_user(user)
    save_chat(chat)
    text = (
        f"🆔 <b>Your ID</b>\n"
        f"<code>{user.id}</code>\n\n"
        f"💬 <b>Chat ID</b>\n<code>{chat.id if chat else 'Unknown'}</code>\n"
        f"Type: {esc(chat.type if chat else 'Unknown')}"
    )
    update.message.reply_text(text, parse_mode=ParseMode.HTML)

def whoami(update: Update, context: CallbackContext):
    user = update.effective_user
    if not user:
        return
    save_user(user)
    uname = f"@{user.username}" if user.username else "-"
    full_name = (user.first_name or "") + ((" " + user.last_name) if user.last_name else "")
    text = (
        f"👤 <b>Your Profile</b>\n\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
        f"📛 <b>Name:</b> {esc(full_name or '-')}\n"
        f"🔗 <b>Username:</b> {esc(uname)}\n"
    )
    if getattr(user, "language_code", None):
        text += f"🌐 <b>Language:</b> {esc(user.language_code)}\n"
    update.message.reply_text(text, parse_mode=ParseMode.HTML)

def ping(update: Update, context: CallbackContext):
    start_ts = time.time()
    sent = update.message.reply_text("🏓 Pinging...")
    end_ts = time.time()
    latency_ms = int((end_ts - start_ts) * 1000)
    sent.edit_text(f"🏓 <b>Pong!</b>\nLatency: <code>{latency_ms} ms</code>", parse_mode=ParseMode.HTML)

def forwarded_handler(update: Update, context: CallbackContext):
    msg = update.message
    if not msg:
        return
    save_user(msg.from_user)
    save_chat(update.effective_chat)

    sender_user_id = msg.from_user.id if msg.from_user else "Unknown"

    if msg.forward_from:
        f = msg.forward_from
        f_id = f.id
        f_name = f"{f.first_name or ''} {f.last_name or ''}".strip() or f.username or "User"
        text = (
            f"✅ <b>UR ID</b>\n<code>{sender_user_id}</code>\n\n"
            f"🔁 <b>FORWARDED ID</b>\n<code>{f_id}</code>\n\n"
            f"Name: {esc(f_name)}"
        )
        msg.reply_text(text, parse_mode=ParseMode.HTML)
        return

    if msg.forward_from_chat:
        fc = msg.forward_from_chat
        chat_id = fc.id
        chat_title = getattr(fc, "title", None) or getattr(fc, "username", None) or "Chat"
        kind = getattr(fc, "type", "chat")
        text = (
            f"✅ <b>UR ID</b>\n<code>{sender_user_id}</code>\n\n"
            f"🔁 <b>FORWARDED ID</b>\n<code>{chat_id}</code>\n\n"
            f"Forwarded from {esc(kind)}: {esc(chat_title)}"
        )
        msg.reply_text(text, parse_mode=ParseMode.HTML)
        return

    if msg.forward_sender_name:
        text = (
            f"✅ <b>UR ID</b>\n<code>{sender_user_id}</code>\n\n"
            "🔁 <b>FORWARDED ID</b>\n<code>Not available</code>\n\n"
            f"Forwarded sender name: {esc(msg.forward_sender_name)}"
        )
        msg.reply_text(text, parse_mode=ParseMode.HTML)
        return

    msg.reply_text("Forward a message to me and I’ll show you the IDs.")

def callback_query_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    user = query.from_user
    if data == "copy_id":
        query.answer(text=f"Your ID: {user.id}", show_alert=True)
        save_user(user)
        return
    if data == "cmd_myid":
        text = f"🆔 <b>Your ID</b>\n<code>{user.id}</code>"
        query.edit_message_text(text, parse_mode=ParseMode.HTML)
        save_user(user)
        return
    if data == "cmd_help":
        text = (
            "ℹ️ <b>Help</b>\n\n"
            "/myid - Show your ID & chat ID\n"
            "/whoami - Your full info\n"
            "/ping - latency\n"
            "/stats - admin stats\n"
            "/broadcast - owner only\n"
            "Forward a message to get UR ID and FORWARDED ID"
        )
        query.edit_message_text(text, parse_mode=ParseMode.HTML)
        return
    query.answer()

def new_members(update: Update, context: CallbackContext):
    msg = update.message
    if not msg or not msg.new_chat_members:
        return
    save_chat(update.effective_chat)
    for member in msg.new_chat_members:
        if member.is_bot:
            continue
        save_user(member)
        name = esc(member.full_name or member.first_name or "there")
        welcome_text = (
            f"🎉 <b>Welcome {name}!</b>\n\n"
            f"Glad to have you in <b>{esc(update.effective_chat.title or 'this group')}</b>.\n"
            "Use <code>/myid</code> to find your Telegram ID."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📋 Copy My ID", callback_data="copy_id")]])
        msg.reply_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------- Admin & Owner commands ----------
def require_owner(func):
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user = update.effective_user
        if not user or user.id != OWNER_ID:
            update.message.reply_text("You are not authorized to use this command. Owner only.")
            return
        return func(update, context, *args, **kwargs)
    return wrapper

def require_admin(func):
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user = update.effective_user
        if not user or not is_admin(user.id):
            update.message.reply_text("You are not an admin.")
            return
        return func(update, context, *args, **kwargs)
    return wrapper

@require_admin
def stats_cmd(update: Update, context: CallbackContext):
    s = get_stats()
    text = (
        f"📊 <b>Bot stats</b>\n\n"
        f"👥 Tracked users: <code>{s['users']}</code>\n"
        f"💬 Tracked chats: <code>{s['chats']}</code>\n"
        f"📣 Broadcasts: <code>{s['broadcasts']}</code>"
    )
    update.message.reply_text(text, parse_mode=ParseMode.HTML)

@require_admin
def listusers_cmd(update: Update, context: CallbackContext):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("SELECT user_id, username, first_name, last_name, last_seen FROM users ORDER BY last_seen DESC LIMIT 200")
        rows = cur.fetchall()
    lines = ["👥 <b>Recent known users</b>\n"]
    for r in rows:
        uid, username, first, last, last_seen = r
        uname = f"@{username}" if username else "-"
        name = (first or "") + ((" " + last) if last else "")
        ts = time.strftime("%Y-%m-%d", time.localtime(last_seen)) if last_seen else "-"
        lines.append(f"{uid} — {esc(name or '-') } — {uname} — {ts}")
    update.message.reply_text("\n".join(lines[:2000]), parse_mode=ParseMode.HTML)

@require_admin
def export_cmd(update: Update, context: CallbackContext):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("SELECT user_id, username, first_name, last_name, lang_code, last_seen FROM users")
        rows = cur.fetchall()
    fname = "users_export.csv"
    with open(fname, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id","username","first_name","last_name","lang_code","last_seen"])
        w.writerows(rows)
    update.message.reply_text(f"Exported {len(rows)} users to {fname}")

# Moderation: ban, unban, kick (admins only)
@require_admin
def ban_cmd(update: Update, context: CallbackContext):
    if not update.message.chat.type in ["group", "supergroup"]:
        update.message.reply_text("This command must be used in a group (reply to a user's message).")
        return
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to the user's message you want to ban.")
        return
    target = update.message.reply_to_message.from_user
    try:
        context.bot.kick_chat_member(chat_id=update.message.chat.id, user_id=target.id)
        update.message.reply_text(f"User {target.id} has been banned.")
    except Exception as e:
        update.message.reply_text(f"Failed to ban: {e}")

@require_admin
def unban_cmd(update: Update, context: CallbackContext):
    target_id = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            target_id = int(context.args[0])
        except:
            update.message.reply_text("Usage: /unban <user_id> or reply to a user's message.")
            return
    else:
        update.message.reply_text("Usage: /unban <user_id> or reply to a user's message.")
        return
    try:
        context.bot.unban_chat_member(chat_id=update.message.chat.id, user_id=target_id)
        update.message.reply_text(f"User {target_id} has been unbanned.")
    except Exception as e:
        update.message.reply_text(f"Failed to unban: {e}")

@require_admin
def kick_cmd(update: Update, context: CallbackContext):
    if not update.message.chat.type in ["group", "supergroup"]:
        update.message.reply_text("This command must be used in a group (reply to a user's message).")
        return
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to the user's message you want to kick.")
        return
    target = update.message.reply_to_message.from_user
    try:
        context.bot.kick_chat_member(chat_id=update.message.chat.id, user_id=target.id)
        context.bot.unban_chat_member(chat_id=update.message.chat.id, user_id=target.id)
        update.message.reply_text(f"User {target.id} has been kicked.")
    except Exception as e:
        update.message.reply_text(f"Failed to kick: {e}")

# Owner commands to manage admins
@require_owner
def addadmin_cmd(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /addadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
    except:
        update.message.reply_text("Invalid user id.")
        return
    add_admin(uid, added_by=update.effective_user.id)
    update.message.reply_text(f"Added admin: {uid}")

@require_owner
def removeadmin_cmd(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /removeadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
    except:
        update.message.reply_text("Invalid user id.")
        return
    remove_admin(uid)
    update.message.reply_text(f"Removed admin: {uid}")

@require_owner
def listadmins_cmd(update: Update, context: CallbackContext):
    rows = list_admins()
    if not rows:
        update.message.reply_text("No admins.")
        return
    lines = ["👮 <b>Admins</b>\n"]
    for (uid, added_by, ts) in rows:
        lines.append(f"{uid} — added_by: {added_by} — {time.strftime('%Y-%m-%d', time.localtime(ts))}")
    update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

# Broadcast (owner-only)
@require_owner
def broadcast_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    if not user:
        return
    args = context.args
    if update.message.reply_to_message and (update.message.reply_to_message.text or update.message.reply_to_message.caption):
        btext = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
    elif args:
        btext = " ".join(args)
    else:
        update.message.reply_text("Usage: /broadcast your message here\nOr reply to a message with /broadcast.")
        return

    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("INSERT INTO broadcasts (ts, from_user, text, sent_count) VALUES (?, ?, ?, ?)", (int(time.time()), user.id, btext[:4000], 0))
        bid = cur.lastrowid
        DB.commit()

    update.message.reply_text(f"Broadcast started — id {bid}. Sending to users...")

    threading.Thread(target=_do_broadcast, args=(bid, btext, user.id), daemon=True).start()

def _do_broadcast(bid: int, text: str, from_user: int):
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("SELECT user_id FROM users")
        rows = cur.fetchall()
    total = len(rows)
    sent = 0
    bot = UPDATER.bot
    for (user_id,) in rows:
        try:
            bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML)
            sent += 1
        except Exception as e:
            logger.warning("Broadcast to %s failed: %s", user_id, e)
        time.sleep(BROADCAST_DELAY_SEC)
    with DB_LOCK:
        cur = DB.cursor()
        cur.execute("UPDATE broadcasts SET sent_count = ? WHERE id = ?", (sent, bid))
        DB.commit()
    logger.info("Broadcast %s finished: sent %s/%s", bid, sent, total)

# ---------- Error handler ----------
def error_handler(update: object, context: CallbackContext):
    logger.error("Exception while handling an update:", exc_info=context.error)

# ---------- Main ----------
def main():
    global UPDATER
    UPDATER = Updater(token=TOKEN, use_context=True)
    dp = UPDATER.dispatcher

    # Basic commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("myid", myid_cmd))
    dp.add_handler(CommandHandler("whoami", whoami))
    dp.add_handler(CommandHandler("ping", ping))

    # Admin/Owner commands
    dp.add_handler(CommandHandler("stats", stats_cmd))
    dp.add_handl
