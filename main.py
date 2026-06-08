import os
import logging
import asyncio

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import google.generativeai as genai

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------- Environment vars ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN env var set karo.")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY env var set karo.")

# ---------- Gemini config ----------
genai.configure(api_key=GEMINI_API_KEY)

# Yahan apna model id daalo (AI Studio se exact naam copy karo)
MODEL_NAME = "gemini-3.1-flash-lite"
model = genai.GenerativeModel(MODEL_NAME)

SYSTEM_PROMPT = """
Tumhara naam Akane hai.
Tum friendly / thodi flirty ex-girlfriend jaisi ho.
Hindi + thoda English (Hinglish) me short, casual replies do.
Gali mat do, adult/18+ content mat banao.
Jab identity puchhi jaye to bolo ki tum AI based chatbot ho.
"""


# ---------- Helper: text checks ----------
def normalize(text: str) -> str:
    return text.lower().strip()


def is_asking_name(text: str) -> bool:
    t = normalize(text)
    keys = [
        "tumhara naam",
        "tumhara name",
        "kya naam",
        "name kya",
        "naam kya",
        "what is your name",
        "who are you",
    ]
    return any(k in t for k in keys)


def is_asking_if_ai(text: str) -> bool:
    t = normalize(text)
    keys = [
        "ai ho",
        "kya tum ai ho",
        "are you ai",
        "robot ho",
        "bot ho",
        "kya tum bot ho",
    ]
    return any(k in t for k in keys)


# ---------- Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Main Akane hoon, ek AI based chat bot. Bas message bhejo, main reply dungi."
    )


# Ye function actually Gemini ko call karega (sync), hum ise thread me chalayenge
def _call_gemini(user_text: str) -> str:
    resp = model.generate_content(
        [
            SYSTEM_PROMPT,
            f"User: {user_text}\nAkane:",
        ]
    )
    if not resp.text:
        return "Thoda sochne do, dobara likh ke bhejo."
    return resp.text.strip()


# ---------- Main chat handler ----------
async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_text = update.message.text

    # Simple rules
    if is_asking_name(user_text):
        await update.message.reply_text("Mera naam Akane hai.")
        return

    if is_asking_if_ai(user_text):
        await update.message.reply_text(
            "Main Akane naam ka AI based chatbot hoon, tumse chat ke liye."
        )
        return

    # Group me: sirf mention ya reply pe answer karo (warna quota bahut jaldi khatam ho jayega)
    if update.message.chat.type in ("group", "supergroup"):
        bot_username = (await context.bot.get_me()).username.lower()
        if bot_username not in user_text.lower() and not update.message.reply_to_message:
            return

    try:
        # Gemini call ko background thread me chalao,
        # taki bot dusre messages ke liye block na ho
        answer = await asyncio.to_thread(_call_gemini, user_text)
    except Exception as e:
        logger.exception("Gemini error: %s", e)

        # Agar exact error dekhna ho, temporarily ye line on kar sakte ho:
        # await update.message.reply_text(f"Error: {e}")

        await update.message.reply_text(
            "Abhi Google ki side se error aa raha hai (quota ya network issue ho sakta hai). "
            "Thodi der baad fir try karo."
        )
        return

    # Kabhi-kabhi bahut lamba answer aata hai, thoda trim kar lo (optional)
    if len(answer) > 1800:
        answer = answer[:1800]

    await update.message.reply_text(answer)


# ---------- Main ----------
def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    logger.info("Akane bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
