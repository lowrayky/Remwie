from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, ContextTypes
)
import sqlite3
from datetime import datetime, timedelta

TOKEN = "8345831233:AAFPqfWJ8qqeXVREp74YwpSywFL33yHbl8U"

INTERVALS = [1, 3, 7, 14, 30]

conn = sqlite3.connect("words.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT,
    translation TEXT,
    stage INTEGER,
    next_date TEXT
)
""")
conn.commit()


def next_date(stage):
    days = INTERVALS[min(stage, len(INTERVALS) - 1)]
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Я бот для интервального повторения слов.\n\n"
        "/add word translation\n"
        "/today — слова на сегодня"
    )


async def add_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Формат: /add avoid избегать")
        return

    word = context.args[0]
    translation = " ".join(context.args[1:])

    cursor.execute(
        "INSERT INTO words (word, translation, stage, next_date) VALUES (?, ?, ?, ?)",
        (word, translation, 0, next_date(0))
    )
    conn.commit()

    await update.message.reply_text(f"✅ Добавлено: {word} — {translation}")


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT id, word, translation FROM words WHERE next_date <= ?",
        (today_str,)
    )
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("🎉 Сегодня повторений нет")
        return

    for word_id, word, translation in rows:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Помню", callback_data=f"remember_{word_id}"),
                InlineKeyboardButton("❌ Не помню", callback_data=f"forgot_{word_id}")
            ]
        ])

        await update.message.reply_text(
            f"🔁 Повторение:\n\n{word} — ?",
            reply_markup=keyboard
        )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, word_id = query.data.split("_")
    word_id = int(word_id)

    cursor.execute(
        "SELECT stage, word, translation FROM words WHERE id = ?",
        (word_id,)
    )
    stage, word, translation = cursor.fetchone()

    if action == "remember":
        stage += 1
    else:
        stage = 0

    cursor.execute(
        "UPDATE words SET stage = ?, next_date = ? WHERE id = ?",
        (stage, next_date(stage), word_id)
    )
    conn.commit()

    await query.edit_message_text(
        f"{'✅' if action=='remember' else '❌'} "
        f"{word} — {translation}\n"
        f"Следующее повторение запланировано."
    )


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_word))
app.add_handler(CommandHandler("today", today))
app.add_handler(CallbackQueryHandler(button))

app.run_polling()
