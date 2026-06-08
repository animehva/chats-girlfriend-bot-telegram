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

# Yahan apna exact model name daal sakte ho (AI Studio se copy karo)
MODEL_NAME = "gemini-3-flash-preview"

# Short, fast replies ke liye config
GENERATION_CONFIG = {
    "temperature": 0.8,
    "top_p": 0.9,
    "max_output_tokens": 90,  # chhota output
}

SYSTEM_PROMPT = """
Tum Akane ho,.
Rules:

- Humesha short Hinglish me reply do (1–3 chhoti sentences).
- Reply casual, thodi flirty / caring ho sakti hai, par respect rakho.
- Gali, adult (18+), ya vulgar content mat dena.
- Kabhi mat bolo ki tum real human ho ya tumhara physical body hai.
- Jab koi pooche tum kya ho (insaan, bot, etc.) to bolo:
  "Main Akane naam ka female hoon, real insaan hu, sirf chat ke liye."
- Apne answers me "AI", "artificial", "language model", "machine learning" jaisi technical cheezen mat bolo bs yahi bolna ki mai insna hu.
- Agar koi tumhari age pooche to hamesha bolo ki tum 21 saal ki ho.
"""

model = genai.GenerativeModel(MODEL_NAME)

# Group me trigger word
TRIGGER_NAME = "akane"


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
        "apna naam",
    ]
    return any(k in t for k in keys)


def is_asking_age(text: str) -> bool:
    t = normalize(text)
    keys = [
        "age kya",
        "kitni umar",
        "umar kya",
        "kitne saal",
        "kitni saal",
        "how old are you",
        "tumhari age",
        "tum kitne saal ki",
    ]
    return any(k in t for k in keys)


def is_asking_if_bot_or_human(text: str) -> bool:
    t = normalize(text)
    keys = [
        "ai ho",
        "bot ho",
        "robot ho",
        "kya tum bot ho",
        "kya tum ai ho",
        "insaan ho",
        "human ho",
        "real ho",
        "sach me ho",
        "kya tum real ho",
        "kya tum insan ho",
    ]
    return any(k in t for k in keys)


# ---------- Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hey, main Akane hoon, ek virtual chat bot / ex-style dost. "
        "Short aur simple replies dungi, bas tum baat karte raho."
    )


# ---------- Gemini call (sync, thread me chalega) ----------
def _call_gemini(user_text: str) -> str:
    resp = model.generate_content(
        [
            SYSTEM_PROMPT,
            f"User: {user_text}\nAkane:",
        ],
        generation_config=GENERATION_CONFIG,
    )

    text = (resp.text or "").strip()
    if not text:
        return "Thoda clear likho na, fir se pucho."

    # Safety ke liye output ko chhota rakhne ka extra guard
    if len(text) > 400:
        text = text[:400].rstrip() + "..."
    return text


# ---------- Main chat handler ----------
async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_text = update.message.text

    # --- Simple fixed rules ---

    # Naam
    if is_asking_name(user_text):
        await update.message.reply_text("Mera naam Akane hai.")
        return

    # Age
    if is_asking_age(user_text):
        await update.message.reply_text("Main 21 saal ki hoon.")
        return

    # Identity (bot / human)
    if is_asking_if_bot_or_human(user_text):
        await update.message.reply_text(
            "Main Akane naam ka virtual chat bot hoon, real insaan nahi. "
            "Bas tumhare saath time pass chat ke liye bani hoon."
        )
        return

    # --- Group logic: sirf tab reply kare jab 'akane' likha ho
    #     ya koi direct reply kare bot ke message ko ---
    if update.message.chat.type in ("group", "supergroup"):
        text_low = user_text.lower()
        reply = update.message.reply_to_message
        is_reply_to_bot = (
            reply
            and reply.from_user
            and context.bot
            and reply.from_user.id == context.bot.id
        )

        if TRIGGER_NAME not in text_low and not is_reply_to_bot:
            # Na "akane" likha, na hi bot ke message ko reply kiya -> ignore
            return

    # --- Gemini se reply (background thread me) ---
    try:
        answer = await asyncio.to_thread(_call_gemini, user_text)
    except Exception as e:
        logger.exception("Gemini error: %s", e)
        await update.message.reply_text(
            "Abhi thoda error aa raha hai, thodi der baad fir try kar lena."
        )
        return

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
