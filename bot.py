from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, ContextTypes
)
import sqlite3
from datetime import datetime, timedelta

import os
import pytz
from dotenv import load_dotenv

TOKEN = os.getenv("8345831233:AAGRb6TIC8Ve3oR1oXksALQEXfjtgVSbQek")

load_dotenv()

INTERVALS = [1, 3, 7, 14, 30]
MSK = pytz.timezone("Europe/Moscow")

conn = sqlite3.connect("items.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT,
    stage INTEGER,
    next_date TEXT,
    created_at TEXT,
    shown_today INTEGER DEFAULT 0
)
""")
conn.commit()

# Добавляем колонку если её нет (для существующих БД)
try:
    cursor.execute("ALTER TABLE items ADD COLUMN shown_today INTEGER DEFAULT 0")
    conn.commit()
except:
    pass


def now_msk():
    return datetime.now(MSK)


def today_msk():
    return now_msk().strftime("%Y-%m-%d")


def calc_next_date(stage: int):
    days = INTERVALS[min(stage, len(INTERVALS) - 1)]
    return (now_msk() + timedelta(days=days)).strftime("%Y-%m-%d")


# ---------- COMMANDS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Я бот для интервального повторения ЛЮБОЙ информации.\n\n"
        "📌 /add <текст> — добавить информацию для повторения\n"
        "📅 /today — что повторять сегодня\n"
        "📋 /list — список всей внесённой информации\n"
        "🗑 /delete <номер> — удалить информацию по номеру из /list"
    )


async def add_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = " ".join(context.args) if context.args else None

    if not content:
        await update.message.reply_text("✏️ Укажи текст после команды.\nПример: /add Столица Франции — Париж")
        return

    cursor.execute(
        "INSERT INTO items (content, stage, next_date, created_at, shown_today) VALUES (?, ?, ?, ?, ?)",
        (
            content,
            0,
            calc_next_date(0),
            now_msk().strftime("%Y-%m-%d %H:%M:%S"),
            0
        )
    )
    conn.commit()

    await update.message.reply_text(
        "✅ Сохранено для повторения.\n"
        "Первое повторение — завтра."
    )


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_str = today_msk()

    # Берём только те, что ещё не показывались сегодня
    cursor.execute(
        "SELECT id, content FROM items WHERE next_date <= ? AND shown_today = 0",
        (today_str,)
    )
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("🎉 Сегодня повторений нет!")
        return

    # Помечаем все как показанные сегодня (отсчёт начался)
    ids = [row[0] for row in rows]
    cursor.execute(
        f"UPDATE items SET shown_today = 1 WHERE id IN ({','.join('?' * len(ids))})",
        ids
    )
    conn.commit()

    await update.message.reply_text(f"📚 Сегодня нужно повторить {len(rows)} элемент(ов):")

    for item_id, content in rows:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Помню", callback_data=f"remember_{item_id}"),
                InlineKeyboardButton("❌ Не помню", callback_data=f"forgot_{item_id}")
            ]
        ])
        await update.message.reply_text(content, reply_markup=keyboard)


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, content, stage, next_date FROM items ORDER BY id ASC")
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("📭 Список пуст. Добавь что-нибудь через /add")
        return

    lines = ["📋 *Все записи:*\n"]
    for i, (item_id, content, stage, next_date) in enumerate(rows, start=1):
        interval_info = f"интервал {stage+1}/{len(INTERVALS)}, следующее: {next_date}"
        # Обрезаем длинный текст для читаемости
        short = content if len(content) <= 80 else content[:77] + "..."
        lines.append(f"{i}\\) `[{item_id}]` {short}\n    _{interval_info}_")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="MarkdownV2"
    )


async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Укажи номер записи.\nПример: /delete 3\n\nНомер можно узнать в /list — это число в квадратных скобках [ID].")
        return

    item_id = int(context.args[0])

    cursor.execute("SELECT content FROM items WHERE id = ?", (item_id,))
    row = cursor.fetchone()

    if not row:
        await update.message.reply_text(f"❌ Запись с ID {item_id} не найдена. Проверь номер через /list")
        return

    cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()

    short = row[0] if len(row[0]) <= 60 else row[0][:57] + "..."
    await update.message.reply_text(f"🗑 Удалено: «{short}»")


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, item_id = query.data.split("_")
    item_id = int(item_id)

    cursor.execute("SELECT stage FROM items WHERE id = ?", (item_id,))
    result = cursor.fetchone()

    if not result:
        await query.edit_message_text("⚠️ Запись уже удалена.")
        return

    stage = result[0]

    if action == "remember":
        new_stage = stage + 1
        # Последний интервал пройден — удаляем запись
        if new_stage >= len(INTERVALS):
            cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
            conn.commit()
            await query.edit_message_text(
                "🏆 Отлично! Ты полностью выучил эту информацию — она удалена из списка."
            )
            return
        else:
            cursor.execute(
                "UPDATE items SET stage = ?, next_date = ?, shown_today = 0 WHERE id = ?",
                (new_stage, calc_next_date(new_stage), item_id)
            )
    else:
        # Забыл — сбрасываем на начало
        cursor.execute(
            "UPDATE items SET stage = 0, next_date = ?, shown_today = 0 WHERE id = ?",
            (calc_next_date(0), item_id)
        )

    conn.commit()

    await query.edit_message_text("📌 Ответ принят. Следующее повторение запланировано.")


# Сброс флага shown_today в полночь по МСК
async def reset_shown_today(context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("UPDATE items SET shown_today = 0")
    conn.commit()


# ---------- APP ----------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_text))
app.add_handler(CommandHandler("today", today_cmd))
app.add_handler(CommandHandler("list", list_cmd))
app.add_handler(CommandHandler("delete", delete_cmd))
app.add_handler(CallbackQueryHandler(button))

# Сброс shown_today каждую ночь в 00:00 МСК
app.job_queue.run_daily(
    reset_shown_today,
    time=datetime.strptime("00:00", "%H:%M").replace(tzinfo=MSK).timetz()
)

app.run_polling()