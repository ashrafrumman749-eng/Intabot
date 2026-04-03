import os
import re
import time
import random
import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler, ContextTypes
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, LoginRequired, PleaseWaitFewMinutes, ReloginRequired, TwoFactorRequired

# ============ কনফিগারেশন ============
BOT_TOKEN = "8634263479:AAHFrGiJZI4SzO6ur9aJcX0aC9_ExC5yWMs"  # এখানে আপনার বট টোকেন বসান
ADMIN_CHAT_ID = "5368102279"  # আপনার চ্যাট আইডি (ঐচ্ছিক)
MAX_RETRY = 3  # কোড রিসেন্ডের সর্বোচ্চ সংখ্যা

# স্টেট সংক্রান্ত কনস্ট্যান্ট
PHONE, PASSWORD, CODE, TWO_FACTOR = range(4)

# লগিং সেটআপ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ইউজার ডেটা স্টোর (সিম্পল ডিকশনারি - প্রোডাকশনে ডাটাবেস ব্যবহার করবেন)
user_data_store = {}

# ============ হিউম্যান বিহেভিয়ার হেল্পার ============
def human_delay(min_sec=2, max_sec=5):
    time.sleep(random.uniform(min_sec, max_sec))

def random_typing_speed():
    return random.uniform(0.2, 0.8)

def random_user_agent():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36",
    ]
    return random.choice(user_agents)

def generate_username():
    prefixes = ["dev", "life", "art", "travel", "food", "tech", "fashion", "music", "sports", "nature"]
    suffixes = ["lover", "fan", "official", "world", "hub", "daily", "zone", "lab", "studio", "space"]
    numbers = random.randint(10, 999)
    return f"{random.choice(prefixes)}_{random.choice(suffixes)}_{numbers}"

def generate_password():
    import string
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(random.choice(chars) for _ in range(12))

def generate_full_name():
    first_names = ["John", "Jane", "Alex", "Maria", "David", "Sarah", "Michael", "Emma", "Chris", "Lisa"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Martinez", "Wilson"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def generate_bio():
    bios = [
        "✨ Living my best life | 🌍 Traveler | 📸 Photography",
        "💻 Tech enthusiast | 🎵 Music lover | 🧘‍♀️ Fitness",
        "🚀 Dreamer | 🌟 Believer | 💪 Achiever",
        "🐶 Dog mom | ☕ Coffee addict | 📚 Bookworm",
        "🎨 Artist | ✨ Creative soul | 🌈 Spreading positivity"
    ]
    return random.choice(bios)

# ============ টেলিগ্রাম বট হ্যান্ডলার ============
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
    
    welcome_msg = (
        f"🤖 *Instagram অ্যাকাউন্ট ক্রিয়েটর বট*\n\n"
        f"আমি আপনার জন্য স্বয়ংক্রিয়ভাবে অ্যাকাউন্ট তৈরি করে দেব।\n\n"
        f"🔹 *জেনারেটেড ইউজারনেম:* `{user_data_store[user_id]['username']}`\n"
        f"🔹 *নাম:* {user_data_store[user_id]['full_name']}\n"
        f"🔹 *বায়ো:* {user_data_store[user_id]['bio']}\n\n"
        f"📱 *এখন আপনার ফোন নম্বর দিন (কান্ট্রি কোড সহ)*\n"
        f"উদাহরণ: `+8801712345678`"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")
    return PHONE

async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    phone = update.message.text.strip()
    
    if not re.match(r'^\+[1-9]\d{1,14}$', phone):
        await update.message.reply_text("❌ *ভুল ফরম্যাট!*\nকান্ট্রি কোড সহ নম্বর দিন। উদাহরণ: `+8801712345678`", parse_mode="Markdown")
        return PHONE
    
    password = generate_password()
    user_data_store[user_id]["phone"] = phone
    user_data_store[user_id]["password"] = password
    user_data_store[user_id]["state"] = CODE
    
    await update.message.reply_text(
        f"✅ *ফোন নম্বর সেভ হয়েছে:* `{phone}`\n\n"
        f"🔐 *আপনার পাসওয়ার্ড:* `{password}`\n\n"
        f"📨 *এবার ভেরিফিকেশন কোড দিন*\n"
        f"ইনস্টাগ্রাম আপনার ফোন নম্বরে একটি কোড পাঠাবে।\n"
        f"কোড না এলে `/resend` লিখুন।",
        parse_mode="Markdown"
    )
    
    cl = Client()
    cl.set_user_agent(random_user_agent())
    user_data_store[user_id]["cl"] = cl
    
    try:
        await asyncio.to_thread(cl.request_verify_code, phone)
        await update.message.reply_text("📲 *ভেরিফিকেশন কোড পাঠানো হয়েছে!* (১৫-২০ সেকেন্ড সময় লাগতে পারে)", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"কোড পাঠাতে ব্যর্থ: {e}")
        await update.message.reply_text(f"⚠️ *কোড পাঠাতে সমস্যা হয়েছে!*\n`/resend` দিয়ে আবার চেষ্টা করুন।\n\nত্রুটি: {str(e)[:100]}", parse_mode="Markdown")
    
    return CODE

async def resend_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        await update.message.reply_text("❌ *প্রথমে /start দিন*", parse_mode="Markdown")
        return
    
    user_data = user_data_store[user_id]
    if user_data["retry_count"] >= MAX_RETRY:
        await update.message.reply_text(f"⚠️ *আপনি সর্বোচ্চ {MAX_RETRY} বার চেষ্টা করেছেন!*\nআবার শুরু করতে `/start` দিন।", parse_mode="Markdown")
        return
    
    user_data["retry_count"] += 1
    phone = user_data.get("phone")
    
    if not phone:
        await update.message.reply_text("❌ *ফোন নম্বর পাওয়া যায়নি!*\nআবার `/start` দিন।", parse_mode="Markdown")
        return
    
    await update.message.reply_text(f"🔄 *কোড রিসেন্ড করার অনুরোধ করা হয়েছে...* (চেষ্টা {user_data['retry_count']}/{MAX_RETRY})", parse_mode="Markdown")
    human_delay(1, 3)
    
    try:
        cl = user_data["cl"]
        await asyncio.to_thread(cl.request_verify_code, phone)
        await update.message.reply_text("✅ *নতুন কোড পাঠানো হয়েছে!*", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ *আবার ব্যর্থ!* ত্রুটি: {str(e)[:100]}", parse_mode="Markdown")

async def code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = update.message.text.strip()
    
    if user_id not in user_data_store:
        await update.message.reply_text("❌ *সেশন শেষ!* `/start` দিয়ে শুরু করুন।", parse_mode="Markdown")
        return
    
    user_data = user_data_store[user_id]
    cl = user_data.get("cl")
    
    if not cl:
        await update.message.reply_text("❌ *ক্লায়েন্ট অবজেক্ট নেই!* আবার `/start` করুন।", parse_mode="Markdown")
        return
    
    await update.message.reply_text("🔄 *অ্যাকাউন্ট তৈরি হচ্ছে...* (৩০-৪০ সেকেন্ড সময় লাগতে পারে)", parse_mode="Markdown")
    human_delay(1, 2)
    
    try:
        await asyncio.to_thread(human_delay, 2, 4)
        user_id_insta = await asyncio.to_thread(
            cl.login, 
            user_data["phone"], 
            user_data["password"], 
            verification_code=code
        )
        
        await asyncio.to_thread(human_delay, 1, 2)
        await asyncio.to_thread(
            cl.account_edit,
            full_name=user_data["full_name"],
            biography=user_data["bio"],
            username=user_data["username"]
        )
        
        await update.message.reply_text("🔐 *টু-ফ্যাক্টর অথেনটিকেশন সক্রিয় করা হচ্ছে...*", parse_mode="Markdown")
        await asyncio.to_thread(human_delay, 2, 3)
        
        twofa_data = await asyncio.to_thread(cl.account_enable_two_factor)
        secret_key = twofa_data.get("secret_key", "N/A")
        backup_codes = twofa_data.get("backup_codes", [])
        
        user_data["twofa_secret"] = secret_key
        user_data["backup_codes"] = backup_codes
        
        success_msg = (
            f"✅ *অ্যাকাউন্ট সফলভাবে তৈরি হয়েছে!*\n\n"
            f"📱 *ইউজারনেম:* `{user_data['username']}`\n"
            f"🔑 *পাসওয়ার্ড:* `{user_data['password']}`\n"
            f"📞 *ফোন:* `{user_data['phone']}`\n\n"
            f"🔐 *2FA সিক্রেট কী:* `{secret_key}`\n"
            f"🔹 *ব্যাকআপ কোড:* `{', '.join(backup_codes[:3])}` (প্রথম ৩টি)\n\n"
            f"⚠️ *সতর্কতা:* এই কোডগুলো সংরক্ষণ করুন। সিক্রেট কী Google Authenticator অ্যাপে যোগ করবেন।"
        )
        await update.message.reply_text(success_msg, parse_mode="Markdown")
        
        await asyncio.to_thread(cl.logout)
        del user_data_store[user_id]
        
    except TwoFactorRequired:
        await update.message.reply_text("⚠️ *2FA প্রয়োজন!* কিন্তু আমরা এটি অটোমেটিক্যালি করেছি। চেষ্টা চালিয়ে যান।", parse_mode="Markdown")
        return TWO_FACTOR
    except ChallengeRequired:
        await update.message.reply_text("⚠️ *চ্যালেঞ্জ প্রয়োজন!* (হয়তো ইনস্টাগ্রাম চেক করছে)\nআবার `/start` দিয়ে চেষ্টা করুন।", parse_mode="Markdown")
        del user_data_store[user_id]
    except Exception as e:
        error_msg = str(e)
        logger.error(f"অ্যাকাউন্ট তৈরি ব্যর্থ: {error_msg}")
        await update.message.reply_text(
            f"❌ *অ্যাকাউন্ট তৈরি ব্যর্থ!*\nত্রুটি: {error_msg[:200]}\n\n"
            f"টিপস:\n• ভুল কোড দিলে `/resend` দিয়ে আবার চেষ্টা করুন\n• নম্বর সঠিক কিনা চেক করুন\n• খুব দ্রুত অনেক চেষ্টা করলে ইনস্টাগ্রাম ব্লক করে দিতে পারে। ২-৩ মিনিট অপেক্ষা করুন।",
            parse_mode="Markdown"
        )
        user_data["cl"] = Client()
        user_data["cl"].set_user_agent(random_user_agent())
        return CODE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data_store:
        del user_data_store[user_id]
    await update.message.reply_text("❌ *প্রক্রিয়া বাতিল করা হয়েছে!* `/start` দিয়ে আবার শুরু করুন।", parse_mode="Markdown")
    return ConversationHandler.END

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤔 *বুঝলাম না!* \nকমান্ড গুলো: `/start`, `/resend`, `/cancel`", parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_handler)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("resend", resend_code))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    print("🤖 বট চালু হয়েছে...")
    app.run_polling()

if __name__ == "__main__":
    main()
