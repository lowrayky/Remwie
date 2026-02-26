from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, ContextTypes
)
import sqlite3
from datetime import datetime, timedelta
import os

TOKEN = os.getenv("BOT_TOKEN")

# интервалы ПОСЛЕДОВАТЕЛЬНЫЕ
INTERVALS = [1, 3, 7, 14, 30]

conn = sqlite3.connect("items.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT,
    stage INTEGER,
    next_date TEXT,
    created_at TEXT
)
""")
conn.commit()


def calc_next_date(stage: int):
    days = INTERVALS[min(stage, len(INTERVALS) - 1)]
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


# ---------- COMMANDS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Я бот для интервального повторения ЛЮБОЙ информации.\n\n"
        "📌 Отправь мне текст — я сохраню его для повторения.\n"
        "📅 /today — что повторять сегодня"
    )


async def save_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text

    cursor.execute(
        "INSERT INTO items (content, stage, next_date, created_at) VALUES (?, ?, ?, ?)",
        (
            content,
            0,
            calc_next_date(0),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    conn.commit()

    await update.message.reply_text(
        "✅ Сохранено для повторения.\n"
        "Я пришлю этот текст снова по интервалам."
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        "SELECT id, content FROM items WHERE next_date <= ?",
        (today_str,)
    )
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("🎉 Сегодня повторений нет")
        return

    for item_id, content in rows:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Помню", callback_data=f"remember_{item_id}"),
                InlineKeyboardButton("❌ Не помню", callback_data=f"forgot_{item_id}")
            ]
        ])

        # ❗ отправляем ТЕКСТ КАК ЕСТЬ
        await update.message.reply_text(
            content,
            reply_markup=keyboard
        )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, item_id = query.data.split("_")
    item_id = int(item_id)

    cursor.execute(
        "SELECT stage FROM items WHERE id = ?",
        (item_id,)
    )
    stage = cursor.fetchone()[0]

    if action == "remember":
        stage += 1
    else:
        stage = 0

    cursor.execute(
        "UPDATE items SET stage = ?, next_date = ? WHERE id = ?",
        (stage, calc_next_date(stage), item_id)
    )
    conn.commit()

    await query.edit_message_text(
        "📌 Ответ принят.\n"
        "Следующее повторение запланировано."
    )


# ---------- APP ----------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("today", today))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(CommandHandler("save", save_text))

# любое сообщение → сохранить
app.add_handler(CommandHandler(None, save_text))

app.run_polling()