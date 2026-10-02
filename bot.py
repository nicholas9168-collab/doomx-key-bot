import os
import sqlite3
from datetime import datetime, timezone
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL = "@DoomxOffical"

# FadeHost Environment Variables me apna Telegram numeric ID daalna:
# ADMIN_IDS = 123456789
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

DB = "bot.db"

MENU = ReplyKeyboardMarkup(
    [
        ["🎁 Generate Key", "🔗 My Link"],
        ["👥 Referrals", "🔑 My Keys"],
        ["📥 Download APK"],
        ["🔄 Refresh", "ℹ️ How it works"]
    ],
    resize_keyboard=True
)


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        username TEXT,
        points INTEGER DEFAULT 0,
        referred_by INTEGER,
        verified INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS keys(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game TEXT NOT NULL,
        duration TEXT NOT NULL,
        key_value TEXT NOT NULL UNIQUE,
        price INTEGER DEFAULT 5,
        status TEXT DEFAULT 'AVAILABLE',
        sold_to INTEGER,
        sold_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS referrals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer INTEGER,
        referred INTEGER UNIQUE,
        points INTEGER DEFAULT 1,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings(
        name TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    con.commit()
    con.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def get_user(uid):
    con = db()
    u = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    con.close()
    return u


def create_user(user, referrer=None):
    con = db()
    existing = con.execute(
        "SELECT id FROM users WHERE id=?", (user.id,)
    ).fetchone()

    if not existing:
        con.execute("""
        INSERT INTO users
        (id, username, referred_by, created_at)
        VALUES (?, ?, ?, ?)
        """, (
            user.id,
            user.username or "",
            referrer,
            now()
        ))
        con.commit()

    con.close()


def is_admin(uid):
    return uid in ADMIN_IDS


async def is_member(bot, uid):
    try:
        member = await bot.get_chat_member(CHANNEL, uid)
        return member.status in (
            "member", "administrator", "creator"
        ) or (
            member.status == "restricted" and
            getattr(member, "is_member", False)
        )
    except Exception:
        return False


async def verify_user(update, context):
    uid = update.effective_user.id

    if not await is_member(context.bot, uid):
        keyboard = [
            [InlineKeyboardButton(
                "📢 Join Channel",
                url="https://t.me/DoomxOffical"
            )],
            [InlineKeyboardButton(
                "✅ Verify",
                callback_data="verify"
            )]
        ]

        text = (
            "🔒 <b>Channel Join Required</b>\n\n"
            "Bot use karne ke liye pehle hamara channel join karo.\n\n"
            "1️⃣ Join Channel\n"
            "2️⃣ Phir ✅ Verify dabao"
        )

        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        return False

    con = db()
    con.execute(
        "UPDATE users SET verified=1 WHERE id=?",
        (uid,)
    )

    # Referral reward
    row = con.execute(
        "SELECT referred_by FROM users WHERE id=?",
        (uid,)
    ).fetchone()

    if row and row["referred_by"]:
        already = con.execute(
            "SELECT id FROM referrals WHERE referred=?",
            (uid,)
        ).fetchone()

        if not already and row["referred_by"] != uid:
            con.execute(
                "UPDATE users SET points=points+1 WHERE id=?",
                (row["referred_by"],)
            )

            con.execute("""
            INSERT INTO referrals
            (referrer, referred, points, created_at)
            VALUES (?, ?, 1, ?)
            """, (
                row["referred_by"], uid, now()
            ))

    con.commit()
    con.close()
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    referrer = None

    if context.args:
        try:
            referrer = int(context.args[0])
            if referrer == user.id:
                referrer = None
        except:
            referrer = None

    create_user(user, referrer)

    if not await verify_user(update, context):
        return

    await update.message.reply_text(
        "🔥 <b>Welcome to DoomX Key System</b>\n\n"
        "Neeche menu se option choose karo.",
        parse_mode="HTML",
        reply_markup=MENU
    )


async def verify_callback(update, context):
    q = update.callback_query
    uid = q.from_user.id

    if await is_member(context.bot, uid):
        await q.answer("✅ Verified!")

        con = db()
        con.execute(
            "UPDATE users SET verified=1 WHERE id=?",
            (uid,)
        )

        row = con.execute(
            "SELECT referred_by FROM users WHERE id=?",
            (uid,)
        ).fetchone()

        if row and row["referred_by"]:
            already = con.execute(
                "SELECT id FROM referrals WHERE referred=?",
                (uid,)
            ).fetchone()

            if not already and row["referred_by"] != uid:
                con.execute(
                    "UPDATE users SET points=points+1 WHERE id=?",
                    (row["referred_by"],)
                )

                con.execute("""
                INSERT INTO referrals
                (referrer, referred, points, created_at)
                VALUES (?, ?, 1, ?)
                """, (row["referred_by"], uid, now()))

        con.commit()
        con.close()

        await q.edit_message_text(
            "✅ <b>Verified successfully!</b>\n\n"
            "Ab bot ke saare features use kar sakte ho.",
            parse_mode="HTML"
        )

        await context.bot.send_message(
            uid,
            "🏠 <b>Main Menu</b>",
            parse_mode="HTML",
            reply_markup=MENU
        )
    else:
        await q.answer(
            "❌ Pehle channel join karo!",
            show_alert=True
        )


async def generate_key(update, context):
    uid = update.effective_user.id

    if not await verify_user(update, context):
        return

    con = db()
    products = con.execute("""
        SELECT game, duration, price, COUNT(*) AS stock
        FROM keys
        WHERE status='AVAILABLE'
        GROUP BY game, duration, price
        ORDER BY game, duration
    """).fetchall()
    con.close()

    if not products:
        await update.message.reply_text(
            "❌ Abhi koi key stock mein nahi hai.",
            reply_markup=MENU
        )
        return

    buttons = []

    for p in products:
        buttons.append([
            InlineKeyboardButton(
                f"{p['game']} · {p['duration']} ({p['price']}p) [{p['stock']}]",
                callback_data=f"buy|{p['game']}|{p['duration']}|{p['price']}"
            )
        ])

    await update.message.reply_text(
        "🎁 <b>Choose Key</b>\n\n"
        "Apni required key select karo:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def buy_key(update, context):
    q = update.callback_query
    uid = q.from_user.id

    await q.answer()

    if not await is_member(context.bot, uid):
        await q.edit_message_text(
            "❌ Pehle channel join karke verify karo."
        )
        return

    try:
        _, game, duration, price = q.data.split("|", 3)
        price = int(price)
    except:
        await q.edit_message_text("❌ Invalid request.")
        return

    con = db()

    user = con.execute(
        "SELECT points,banned FROM users WHERE id=?",
        (uid,)
    ).fetchone()

    if not user or user["banned"]:
        con.close()
        await q.edit_message_text("🚫 You are banned.")
        return

    if user["points"] < price:
        con.close()
        await q.edit_message_text(
            f"❌ Not enough points.\n\n"
            f"Required: {price} points\n"
            f"Your balance: {user['points']} points"
        )
        return

    # Atomic reservation: same key cannot be sold twice.
    con.execute("BEGIN IMMEDIATE")

    key = con.execute("""
        SELECT * FROM keys
        WHERE game=?
        AND duration=?
        AND price=?
        AND status='AVAILABLE'
        ORDER BY id
        LIMIT 1
    """, (game, duration, price)).fetchone()

    if not key:
        con.rollback()
        con.close()
        await q.edit_message_text(
            "❌ Out of stock."
        )
        return

    cur = con.execute("""
        UPDATE keys
        SET status='SOLD',
            sold_to=?,
            sold_at=?
        WHERE id=?
        AND status='AVAILABLE'
    """, (uid, now(), key["id"]))

    if cur.rowcount != 1:
        con.rollback()
        con.close()
        await q.edit_message_text(
            "❌ Key unavailable. Please try again."
        )
        return

    con.execute(
        "UPDATE users SET points=points-? WHERE id=?",
        (price, uid)
    )

    con.commit()

    balance = con.execute(
        "SELECT points FROM users WHERE id=?",
        (uid,)
    ).fetchone()["points"]

    con.close()

    await q.edit_message_text(
        "🎉 <b>KEY GENERATED</b>\n\n"
        f"🎮 Game: <code>{game}</code>\n"
        f"⏱ Duration: <code>{duration}</code>\n\n"
        f"🔑 Key:\n<code>{key['key_value']}</code>\n\n"
        f"💰 Used: {price} points\n"
        f"💳 Remaining: {balance} points\n\n"
        "⚠️ This key has been marked SOLD.",
        parse_mode="HTML"
    )


async def my_link(update, context):
    if not await verify_user(update, context):
        return

    me = await context.bot.get_me()
    uid = update.effective_user.id

    link = f"https://t.me/{me.username}?start={uid}"

    await update.message.reply_text(
        "🔗 <b>Your Referral Link</b>\n\n"
        f"<code>{link}</code>\n\n"
        "Is link ko friends ke saath share karo.",
        parse_mode="HTML",
        reply_markup=MENU
    )


async def referrals(update, context):
    if not await verify_user(update, context):
        return

    uid = update.effective_user.id

    con = db()

    user = con.execute(
        "SELECT points FROM users WHERE id=?",
        (uid,)
    ).fetchone()

    count = con.execute(
        "SELECT COUNT(*) AS c FROM referrals WHERE referrer=?",
        (uid,)
    ).fetchone()["c"]

    con.close()

    await update.message.reply_text(
        "👥 <b>Referrals</b>\n\n"
        f"👤 Counted: {count}\n"
        f"💰 Spendable Points: {user['points']}\n\n"
        "🎁 Har verified referral par 1 point.",
        parse_mode="HTML",
        reply_markup=MENU
    )


async def my_keys(update, context):
    if not await verify_user(update, context):
        return

    uid = update.effective_user.id

    con = db()
    keys = con.execute("""
        SELECT game,duration,key_value,sold_at
        FROM keys
        WHERE sold_to=?
        ORDER BY sold_at DESC
        LIMIT 20
    """, (uid,)).fetchall()
    con.close()

    if not keys:
        await update.message.reply_text(
            "🔑 <b>My Keys</b>\n\n"
            "Abhi koi key nahi hai.",
            parse_mode="HTML",
            reply_markup=MENU
        )
        return

    text = "🔑 <b>My Keys</b>\n\n"

    for k in keys:
        text += (
            f"🎮 {k['game']} · {k['duration']}\n"
            f"🔐 <code>{k['key_value']}</code>\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=MENU
    )


async def refresh(update, context):
    if not await verify_user(update, context):
        return

    uid = update.effective_user.id

    con = db()
    p = con.execute(
        "SELECT points FROM users WHERE id=?",
        (uid,)
    ).fetchone()["points"]
    con.close()

    await update.message.reply_text(
        f"🔄 <b>Balance Refreshed</b>\n\n"
        f"💰 Points: <b>{p}</b>",
        parse_mode="HTML",
        reply_markup=MENU
    )


async def how_it_works(update, context):
    await update.message.reply_text(
        "ℹ️ <b>How it works</b>\n\n"
        "1️⃣ Channel join karo\n"
        "2️⃣ Verify karo\n"
        "3️⃣ Referral link share karo\n"
        "4️⃣ Points collect karo\n"
        "5️⃣ Generate Key se key lo\n\n"
        "🔒 Sold key dobara kisi user ko nahi milegi.",
        parse_mode="HTML",
        reply_markup=MENU
    )


async def download_apk(update, context):
    await update.message.reply_text(
        "📥 <b>Download APK</b>\n\n"
        "APK link admin panel/settings se add kiya ja sakta hai.",
        parse_mode="HTML",
        reply_markup=MENU
    )


# ---------------- ADMIN ----------------

async def admin(update, context):
    uid = update.effective_user.id

    if not is_admin(uid):
        await update.message.reply_text("🚫 Admin only.")
        return

    buttons = [
        [
            InlineKeyboardButton("➕ Add Key", callback_data="admin_add"),
            InlineKeyboardButton("📦 Stock", callback_data="admin_stock")
        ],
        [
            InlineKeyboardButton("👥 Users", callback_data="admin_users"),
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban"),
            InlineKeyboardButton("✅ Unban", callback_data="admin_unban")
        ]
    ]

    await update.message.reply_text(
        "🔴 <b>DOOMX ADMIN PANEL</b>\n\n"
        "Admin command help ke liye /adminhelp use karo.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_help(update, context):
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "🔴 <b>ADMIN COMMANDS</b>\n\n"
        "<code>/addkey GAME DURATION PRICE KEY</code>\n"
        "Example:\n"
        "<code>/addkey eightballpool 1-Day 5 ABC-123</code>\n\n"
        "<code>/bulk GAME DURATION PRICE</code>\n"
        "Phir next messages mein keys bhejo, end mein /done\n\n"
        "<code>/points USER_ID AMOUNT</code>\n"
        "<code>/ban USER_ID</code>\n"
        "<code>/unban USER_ID</code>\n"
        "<code>/stock</code>\n"
        "<code>/users</code>\n"
        "<code>/stats</code>",
        parse_mode="HTML"
    )


async def add_key(update, context):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 4:
        await update.message.reply_text(
            "Usage:\n/addkey GAME DURATION PRICE KEY"
        )
        return

    game = context.args[0]
    duration = context.args[1]
    price = int(context.args[2])
    key_value = " ".join(context.args[3:])

    con = db()

    try:
        con.execute("""
            INSERT INTO keys
            (game,duration,key_value,price)
            VALUES (?,?,?,?)
        """, (game, duration, key_value, price))

        con.commit()
        await update.message.reply_text(
            "✅ Key stock mein add ho gayi."
        )
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "❌ Ye key already database mein hai."
        )
    finally:
        con.close()


async def stock(update, context):
    if not is_admin(update.effective_user.id):
        return

    con = db()
    rows = con.execute("""
        SELECT game,duration,price,COUNT(*) AS stock
        FROM keys
        WHERE status='AVAILABLE'
        GROUP BY game,duration,price
    """).fetchall()
    con.close()

    if not rows:
        await update.message.reply_text("📦 Stock empty.")
        return

    text = "📦 <b>AVAILABLE STOCK</b>\n\n"

    for r in rows:
        text += (
            f"🎮 {r['game']} · {r['duration']}\n"
            f"💰 Price: {r['price']}p\n"
            f"📦 Stock: {r['stock']}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


async def users(update, context):
    if not is_admin(update.effective_user.id):
        return

    con = db()
    total = con.execute(
        "SELECT COUNT(*) c FROM users"
    ).fetchone()["c"]
    verified = con.execute(
        "SELECT COUNT(*) c FROM users WHERE verified=1"
    ).fetchone()["c"]
    banned = con.execute(
        "SELECT COUNT(*) c FROM users WHERE banned=1"
    ).fetchone()["c"]
    con.close()

    await update.message.reply_text(
        f"👥 <b>USERS</b>\n\n"
        f"Total: {total}\n"
        f"Verified: {verified}\n"
        f"Banned: {banned}",
        parse_mode="HTML"
    )


async def stats(update, context):
    if not is_admin(update.effective_user.id):
        return

    con = db()

    users_count = con.execute(
        "SELECT COUNT(*) c FROM users"
    ).fetchone()["c"]

    available = con.execute(
        "SELECT COUNT(*) c FROM keys WHERE status='AVAILABLE'"
    ).fetchone()["c"]

    sold = con.execute(
        "SELECT COUNT(*) c FROM keys WHERE status='SOLD'"
    ).fetchone()["c"]

    referrals_count = con.execute(
        "SELECT COUNT(*) c FROM referrals"
    ).fetchone()["c"]

    con.close()

    await update.message.reply_text(
        f"📊 <b>STATISTICS</b>\n\n"
        f"👥 Users: {users_count}\n"
        f"📦 Available Keys: {available}\n"
        f"🔐 Sold Keys: {sold}\n"
        f"👥 Referrals: {referrals_count}",
        parse_mode="HTML"
    )


async def points(update, context):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "/points USER_ID AMOUNT"
        )
        return

    uid = int(context.args[0])
    amount = int(context.args[1])

    con = db()
    cur = con.execute(
        "UPDATE users SET points=points+? WHERE id=?",
        (amount, uid)
    )
    con.commit()
    con.close()

    if cur.rowcount:
        await update.message.reply_text(
            f"✅ {amount} points updated for {uid}"
        )
    else:
        await update.message.reply_text(
            "❌ User not found."
        )


async def ban(update, context):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) != 1:
        await update.message.reply_text("/ban USER_ID")
        return

    uid = int(context.args[0])

    con = db()
    con.execute(
        "UPDATE users SET banned=1 WHERE id=?",
        (uid,)
    )
    con.commit()
    con.close()

    await update.message.reply_text("🚫 User banned.")


async def unban(update, context):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) != 1:
        await update.message.reply_text("/unban USER_ID")
        return

    uid = int(context.args[0])

    con = db()
    con.execute(
        "UPDATE users SET banned=0 WHERE id=?",
        (uid,)
    )
    con.commit()
    con.close()

    await update.message.reply_text("✅ User unbanned.")


async def text_handler(update, context):
    uid = update.effective_user.id

    if get_user(uid) and get_user(uid)["banned"]:
        await update.message.reply_text("🚫 You are banned.")
        return

    text = update.message.text

    if text == "🎁 Generate Key":
        await generate_key(update, context)

    elif text == "🔗 My Link":
        await my_link(update, context)

    elif text == "👥 Referrals":
        await referrals(update, context)

    elif text == "🔑 My Keys":
        await my_keys(update, context)

    elif text == "🔄 Refresh":
        await refresh(update, context)

    elif text == "ℹ️ How it works":
        await how_it_works(update, context)

    elif text == "📥 Download APK":
        await download_apk(update, context)

    else:
        if not await verify_user(update, context):
            return

        await update.message.reply_text(
            "👇 Menu se option choose karo.",
            reply_markup=MENU
        )


async def admin_callback(update, context):
    q = update.callback_query

    if not is_admin(q.from_user.id):
        await q.answer("🚫 Admin only.", show_alert=True)
        return

    await q.answer()

    if q.data == "admin_stock":
        con = db()
        rows = con.execute("""
            SELECT game,duration,price,COUNT(*) AS stock
            FROM keys
            WHERE status='AVAILABLE'
            GROUP BY game,duration,price
        """).fetchall()
        con.close()

        if not rows:
            await q.edit_message_text("📦 Stock empty.")
            return

        text = "📦 <b>STOCK</b>\n\n"

        for r in rows:
            text += (
                f"{r['game']} · {r['duration']} "
                f"= {r['stock']} keys @ {r['price']}p\n"
            )

        await q.edit_message_text(
            text,
            parse_mode="HTML"
        )

    elif q.data == "admin_users":
        con = db()
        total = con.execute(
            "SELECT COUNT(*) c FROM users"
        ).fetchone()["c"]
        con.close()

        await q.edit_message_text(
            f"👥 Total users: {total}"
        )

    elif q.data == "admin_stats":
        con = db()

        users_count = con.execute(
            "SELECT COUNT(*) c FROM users"
        ).fetchone()["c"]

        available = con.execute(
            "SELECT COUNT(*) c FROM keys WHERE status='AVAILABLE'"
        ).fetchone()["c"]

        sold = con.execute(
            "SELECT COUNT(*) c FROM keys WHERE status='SOLD'"
        ).fetchone()["c"]

        con.close()

        await q.edit_message_text(
            f"📊 <b>STATS</b>\n\n"
            f"Users: {users_count}\n"
            f"Available: {available}\n"
            f"Sold: {sold}",
            parse_mode="HTML"
        )

    elif q.data == "admin_add":
        await q.edit_message_text(
            "➕ <b>ADD KEY</b>\n\n"
            "<code>/addkey GAME DURATION PRICE KEY</code>\n\n"
            "Example:\n"
            "<code>/addkey eightballpool 1-Day 5 ABC-123</code>",
            parse_mode="HTML"
        )

    elif q.data == "admin_ban":
        await q.edit_message_text(
            "🚫 Ban:\n<code>/ban USER_ID</code>",
            parse_mode="HTML"
        )

    elif q.data == "admin_unban":
        await q.edit_message_text(
            "✅ Unban:\n<code>/unban USER_ID</code>",
            parse_mode="HTML"
        )


async def id_command(update, context):
    await update.message.reply_text(
        f"🆔 Your Telegram ID:\n<code>{update.effective_user.id}</code>",
        parse_mode="HTML"
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN environment variable missing."
        )

    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("adminhelp", admin_help))
    app.add_handler(CommandHandler("addkey", add_key))
    app.add_handler(CommandHandler("stock", stock))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("id", id_command))

    app.add_handler(
        CallbackQueryHandler(
            verify_callback,
            pattern="^verify$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            buy_key,
            pattern="^buy\\|"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern="^admin_"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    print("DoomX bot started...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
