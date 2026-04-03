import os
import re
import time
import random
import asyncio
import logging
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired

# ============ কনফিগারেশন ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    logging.error("BOT_TOKEN environment variable not set!")
MAX_RETRY = 3
PHONE, CODE = range(2)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
user_data_store = {}

# ============ হিউম্যান বিহেভিয়ার ============
def human_delay(min_sec=1, max_sec=3):
    time.sleep(random.uniform(min_sec, max_sec))

def random_user_agent():
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    ]
    return random.choice(agents)

def generate_username():
    prefixes = ["dev", "life", "art", "travel", "food", "tech"]
    suffixes = ["lover", "fan", "official", "hub", "daily"]
    return f"{random.choice(prefixes)}_{random.choice(suffixes)}_{random.randint(10,999)}"

def generate_password():
    import string
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(random.choice(chars) for _ in range(12))

def generate_full_name():
    first = ["John", "Jane", "Alex", "Maria", "David", "Sarah"]
    last = ["Smith", "Johnson", "Williams", "Brown", "Jones"]
    return f"{random.choice(first)} {random.choice(last)}"

def generate_bio():
    bios = ["✨ Living my best life | 🌍 Traveler", "💻 Tech enthusiast | 🎵 Music lover", "🚀 Dreamer | 🌟 Believer"]
    return random.choice(bios)

# ============ টেলিগ্রাম হ্যান্ডলার ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id] = {
        "state": PHONE,
        "retry_count": 0,
        "cl": None,
        "username": generate_username(),
        "full_name": generate_full_name(),
        "bio": generate_bio()
    }
    msg = (f"🤖 *Instagram অ্যাকাউন্ট ক্রিয়েটর*\n\n"
           f"🔹 জেনারেটেড ইউজারনেম: `{user_data_store[user_id]['username']}`\n"
           f"🔹 নাম: {user_data_store[user_id]['full_name']}\n"
           f"🔹 বায়ো: {user_data_store[user_id]['bio']}\n\n"
           f"📱 এখন আপনার ফোন নম্বর দিন (+8801712345678)")
    await update.message.reply_text(msg, parse_mode="Markdown")
    return PHONE

async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    phone = update.message.text.strip()
    if not re.match(r'^\+[1-9]\d{1,14}$', phone):
        await update.message.reply_text("❌ ভুল ফরম্যাট! +8801712345678 দিন।")
        return PHONE
    
    password = generate_password()
    user_data_store[user_id]["phone"] = phone
    user_data_store[user_id]["password"] = password
    user_data_store[user_id]["state"] = CODE
    
    await update.message.reply_text(f"✅ ফোন: `{phone}`\n🔑 পাসওয়ার্ড: `{password}`\n📨 এখন ভেরিফিকেশন কোড দিন।", parse_mode="Markdown")
    
    cl = Client()
    cl.set_user_agent(random_user_agent())
    user_data_store[user_id]["cl"] = cl
    try:
        await asyncio.to_thread(cl.request_verify_code, phone)
        await update.message.reply_text("📲 ভেরিফিকেশন কোড পাঠানো হয়েছে! (15-20 সেকেন্ড)")
    except Exception as e:
        logger.error(f"কোড পাঠাতে ব্যর্থ: {e}")
        await update.message.reply_text(f"⚠️ কোড পাঠাতে সমস্যা: {str(e)[:100]}\n`/resend` চেষ্টা করুন।")
    return CODE

async def resend_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_store:
        await update.message.reply_text("প্রথমে /start দিন")
        return
    data = user_data_store[user_id]
    phone = data.get("phone")
    if not phone:
        await update.message.reply_text("ফোন নম্বর নেই")
        return
    try:
        await asyncio.to_thread(data["cl"].request_verify_code, phone)
        await update.message.reply_text("✅ নতুন কোড পাঠানো হয়েছে")
    except Exception as e:
        await update.message.reply_text(f"❌ ব্যর্থ: {str(e)[:100]}")

async def code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = update.message.text.strip()
    data = user_data_store.get(user_id)
    if not data or not data.get("cl"):
        await update.message.reply_text("সেশন নেই, /start দিন")
        return ConversationHandler.END
    
    await update.message.reply_text("🔄 অ্যাকাউন্ট তৈরি হচ্ছে... (30-40 সেকেন্ড)")
    try:
        await asyncio.to_thread(data["cl"].login, data["phone"], data["password"], verification_code=code)
        await asyncio.to_thread(data["cl"].account_edit, full_name=data["full_name"], biography=data["bio"], username=data["username"])
        
        await update.message.reply_text("🔐 2FA সক্রিয় করা হচ্ছে...")
        twofa = await asyncio.to_thread(data["cl"].account_enable_two_factor)
        secret = twofa.get("secret_key", "N/A")
        backup = twofa.get("backup_codes", [])
        
        success = (f"✅ *অ্যাকাউন্ট তৈরি!*\n\n"
                   f"👤 ইউজারনেম: `{data['username']}`\n"
                   f"🔑 পাসওয়ার্ড: `{data['password']}`\n"
                   f"📞 ফোন: `{data['phone']}`\n\n"
                   f"🔐 *2FA সিক্রেট কী:* `{secret}`\n"
                   f"🔹 ব্যাকআপ কোড: `{', '.join(backup[:3])}`")
        await update.message.reply_text(success, parse_mode="Markdown")
        
        await asyncio.to_thread(data["cl"].logout)
        del user_data_store[user_id]
    except Exception as e:
        logger.error(f"অ্যাকাউন্ট তৈরি ব্যর্থ: {e}")
        await update.message.reply_text(f"❌ ব্যর্থ: {str(e)[:200]}\nআবার /start চেষ্টা করুন।")
        return CODE
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in user_data_store:
        del user_data_store[uid]
    await update.message.reply_text("প্রক্রিয়া বাতিল। /start দিন।")
    return ConversationHandler.END

# ============ Flask ওয়েব সার্ভার (Railway-এর জন্য) ============
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Instagram Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

# ============ মেইন ফাংশন ============
def main():
    # ওয়েব সার্ভার চালু করুন আলাদা থ্রেডে
    web_thread = Thread(target=run_web, daemon=True)
    web_thread.start()
    logger.info("Flask web server started on port " + os.environ.get("PORT", "8080"))
    
    # টেলিগ্রাম বট চালু করুন
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set. Exiting.")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_handler)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("resend", resend_code))
    logger.info("Telegram bot started polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
