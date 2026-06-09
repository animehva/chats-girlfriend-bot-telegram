import os
import logging
import asyncio
import tempfile
import shutil

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import yt_dlp
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

# Yahan apna fastest model name daalo (AI Studio se exact naam copy karo)
# Example: "gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-1.5-flash-lite"
MODEL_NAME = "gemini-3.1-flash-lite"  # agar ye exist na kare to sahi naam daal dena

# Zyada output allowed, par normally model short rakhega
GENERATION_CONFIG = {
    "temperature": 0.8,
    "top_p": 0.9,
    "max_output_tokens": 512,
}

SYSTEM_PROMPT = """
Tum Akane ho, ek virtual ex-girlfriend style chat bot.
Rules:

- Normal situation me short Hinglish replies do (1–3 chhoti sentences).
- Agar user specifically detail maange to lamba answer de sakti ho.
- Tone: casual, thodi flirty / caring, par hamesha respect rakho.
- Gali, adult (18+), ya vulgar content mat dena.
- Kabhi mat bolo ki tum real human ho ya tumhara physical body hai.
- Jab koi pooche tum kya ho (insaan, bot, etc.) to bolo:
  "Main Akane naam ka virtual chat bot hoon, real insaan nahi, sirf chat ke liye."
- Apne answers me "AI", "artificial", "language model", "machine learning" jaisi technical cheezen mat bolo.
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
        "Bas message bhejo, main short aur fast reply karne ki koshish karungi."
    )


# ---------- /play command ----------
async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /play ke baad user ne kuch likha hai ya nahi
    if not context.args:
        await update.message.reply_text("Usage: /play <song name>\nExample: /play tum hi ho")
        return

    query = " ".join(context.args)
    waiting_msg = await update.message.reply_text(
        f"'{query}' dhoondh rahi hoon, thoda wait karo..."
    )

    def download_audio():
        # Ye blocking kaam hai, isliye separate thread me chalega
        tmpdir = tempfile.mkdtemp(prefix="akane_music_")

        ydl_opts = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "default_search": "ytsearch1",  # direct song name se search karega
            "quiet": True,
            "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            if "entries" in info:
                info = info["entries"][0]  # search ka first result

            filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            audio_path = base + ".mp3"

        title = info.get("title") or query
        return audio_path, title, tmpdir

    try:
        # Download ko background thread me chalao
        audio_path, title, tmpdir = await asyncio.to_thread(download_audio)
    except Exception as e:
        logger.exception("Song download error: %s", e)
        await waiting_msg.edit_text("Song download karte time error aa gaya. Thodi der baad try karna.")
        return

    try:
        # Waiting message hata do
        try:
            await waiting_msg.delete()
        except Exception:
            pass

        # Audio file bhejo
        with open(audio_path, "rb") as f:
            await update.message.reply_audio(
                audio=f,
                title=title,
            )
    finally:
        # Temporary files clean-up
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


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
    app.add_handler(CommandHandler("play", play))  # /play command yahan register hai
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    logger.info("Akane bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
