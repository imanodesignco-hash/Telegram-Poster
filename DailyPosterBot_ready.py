
import asyncio
import json
import logging
import os
import time
from pathlib import Path

from telegram import Bot
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, ContextTypes

# تنظیمات
INTERVAL_SECONDS = 5 * 60
RUN_DAYS = 60
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@drkasramoradi")

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "poster_state.json"

MESSAGES = [
    """رفقا ربات هنوز فعاله و داره پرداختی هارو‌ میزنه 🤩

⏳اگه هنوز 400 دلار ازش نگرفتید دست دست نکنید چون بعید میدونم دیگه از این موقعیت ها پیش بیاد 400 دلار یعنی 108 میلیون تومنا 🌟🌟

""",

    """
🟥🟦🟥🟦🟥🟦🟥🟦🟥🟦🟥🟦

✅ شاید درکش برای خیلی ها سخت باشه اما از ۵ صبح تا ۱۰ شب بری سرکار تهش خیلی پول دربیاری روزی ۱ میلیون اما با یک ترفند دلاری کوچیک راحت میشه روزانه بالای 100 میلیونم دراورد زیر کولر و کنار بخاری بدون زحمت و رنج و ازار دیدن💵💰💲💲💲

🌟 #فوری این ۴۰۰ دلار رایگان به ارزش 108,000,000 تومان  رایگان 💵
بدون نیاز به هیچ دانش خاصی !

#قطعی #تضمینی #رایگان""",

    """
🔅مهم نیست الان تو چه جایگاهی هستی مهم اینه چه جایگاهی رو میخوای و لایقشی😉

❗️هیچ وقت جا نزن فرصت همیشه زیاده 
مثل همین ویدیو آموزش رایگان که سنجاق کردم میتونی 400 دلار به دست بیاری📌"""
]

# جلوگیری از نمایش توکن در گزارش‌ها
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger("DailyPosterBot")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(
                STATE_FILE.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read state file.")

    return {
        "started_at": time.time(),
        "next_index": 0,
        "last_message_id": None,
    }


def save_state(state):
    temp_file = STATE_FILE.with_suffix(".tmp")

    temp_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    temp_file.replace(STATE_FILE)


async def check_channel_access(bot):
    me = await bot.get_me()
    chat = await bot.get_chat(CHANNEL_ID)

    member = await bot.get_chat_member(chat.id, me.id)

    if member.status != "administrator":
        raise RuntimeError(
            "Bot is not an administrator of the channel."
        )

    if not getattr(member, "can_post_messages", False):
        raise RuntimeError(
            "Bot does not have permission to post."
        )

    if not getattr(member, "can_delete_messages", False):
        raise RuntimeError(
            "Bot does not have permission to delete."
        )

    logger.info("Channel access verified.")


async def post_next_message(context: ContextTypes.DEFAULT_TYPE):
    state = context.application.bot_data["state"]

    if time.time() - state["started_at"] >= RUN_DAYS * 86400:
        logger.info("The 60-day period has ended.")

        if context.job:
            context.job.schedule_removal()

        return

    previous_id = state.get("last_message_id")

    if previous_id is not None:
        try:
            await context.bot.delete_message(
                chat_id=CHANNEL_ID,
                message_id=previous_id,
            )

            logger.info("Previous message deleted.")

        except BadRequest as exc:
            if "message to delete not found" not in str(exc).lower():
                logger.error("Could not delete previous message: %s", exc)
                return

        except TelegramError as exc:
            logger.error("Delete error: %s", exc)
            return

        state["last_message_id"] = None
        save_state(state)

    index = state["next_index"] % len(MESSAGES)

    try:
        sent = await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=MESSAGES[index],
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

    except TelegramError as exc:
        logger.error("Send error: %s", exc)
        return

    state["last_message_id"] = sent.message_id
    state["next_index"] = (index + 1) % len(MESSAGES)

    save_state(state)

    logger.info(
        "Message %d of %d published.",
        index + 1,
        len(MESSAGES),
    )


async def post_init(application: Application):
    if not os.environ.get("BOT_TOKEN"):
        raise RuntimeError("BOT_TOKEN is missing.")

    if not CHANNEL_ID:
        raise RuntimeError("CHANNEL_ID is missing.")

    await check_channel_access(application.bot)

    state = load_state()
    application.bot_data["state"] = state

    remaining = (
        RUN_DAYS * 86400 -
        (time.time() - state["started_at"])
    )

    if remaining <= 0:
        logger.info("The 60-day period has already ended.")
        return

    application.job_queue.run_repeating(
        post_next_message,
        interval=INTERVAL_SECONDS,
        first=0,
        name="channel_poster",
    )

    logger.info(
        "Bot started. Posting every 5 minutes for 60 days."
    )


def main():
    token = os.environ.get("BOT_TOKEN")

    if not token:
        raise RuntimeError("BOT_TOKEN is missing.")

    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # اصلاح خطای Event Loop در Python 3.14
    asyncio.set_event_loop(asyncio.new_event_loop())

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
