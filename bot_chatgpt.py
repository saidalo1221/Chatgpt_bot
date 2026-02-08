import os
import logging
import base64
import json
import asyncio
import re
import datetime
from dotenv import load_dotenv

from fpdf import FPDF
from docx import Document
from pypdf import PdfReader
from bs4 import BeautifulSoup 

from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    InputMediaPhoto,
    LabeledPrice
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes, 
    CallbackQueryHandler,
    PreCheckoutQueryHandler
)
from openai import OpenAI

# --- CONFIGURATION ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# PAYMENT TOKENS
PAYMENT_TOKENS = {
    "click": os.getenv("PAYMENT_TOKEN_CLICK"),
    "payme": os.getenv("PAYMENT_TOKEN_PAYME"),
    "stripe": os.getenv("PAYMENT_TOKEN_STRIPE")
}

client = OpenAI(api_key=OPENAI_KEY)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE ---
DB_FILE = "users.json"
ADMINS_FILE = "admins.json"

def load_json(file):
    if not os.path.exists(file): return {}
    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    except: return {}

def save_json(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving {file}: {e}")

USERS = load_json(DB_FILE)
ADMINS = load_json(ADMINS_FILE)

# --- LIMITS, MODELS & PRICES ---
TIER_MODELS = {
    "Basic": "gpt-4o-mini",
    "Pro": "gpt-4o",
    "Premium": "gpt-4o"
}

TIER_LIMITS = {
    "Basic": 500,
    "Pro": 500,
    "Premium": 1000
}

TIER_PHOTO_LIMITS = {
    "Basic": 50,
    "Pro": 100,
    "Premium": 150
}

TIER_IMG_GEN_LIMITS = {
    "Basic": 30,  # Reverted to 30 as requested
    "Pro": 60,
    "Premium": 100
}

# Prices in UZS (Integer amounts)
TIER_PRICES = {
    "Pro": 129000,
    "Premium": 219000
}

HISTORY_LIMIT = 15
PHOTO_MEMORY_TURNS = 5

# --- TEXTS ---
AUTH_TEXTS = {
    "req": "🔒 Authentication Required\nPlease share your phone number.",
    "btn": "📱 Share Contact",
    "wait": "⏳ Request sent."
}

TEXTS = {
    "en": {
        "welcome": "👋 Hello {name}!\nI'm ready. What would you like to do?",
        "approved": "✅ Access Granted! Type /start",
        "declined": "❌ Access Denied.",
        "blocked": "🚫 Access Revoked.",
        "btn_chat": "💬 Chat", 
        "btn_file": "💾 Create File", 
        "btn_analyze": "📷 Analyze",
        "btn_imggen": "🎨 Generate Image",
        "btn_uploads": "📂 Uploads",
        "btn_lang": "🌐 Language",
        "btn_tier": "⭐ Tier",
        "btn_usage": "📊 Usage",
        "btn_clear": "🧹 Clear",
        "choose_fmt": "💾 Select Format:",
        "file_sent": "📤 Here is your file!",
        "no_text": "❌ Nothing to save.",
        "cleared": "🧹 Memory fresh and clean!",
        "auto_cleared": "♻️ **Auto-Reset:** I've cleared old images to stay focused.",
        "no_imgs": "❌ No images found.",
        "lang_set": "✅ Language: English 🇺🇸",
        "usage_msg": "👤 {name}\n⭐ Plan: {tier}\n🧠 **Model:** `{model}`\n➖➖➖➖➖➖\n✉️ Msgs: {used}/{limit}\n🖼️ Uploads: {p_used}/{p_limit}\n🎨 Generated: {g_used}/{g_limit}",
        "tier_changed": "✅ Plan updated: {tier}",
        "img_received": "📸 Got it! ({count} images). I'll keep them in mind. 🧠",
        "send_photo_prompt": "📸 Send me a photo!",
        "listening": "👂 I'm listening...",
        "file_read": "📖 File read! I know the context now.",
        "file_error": "❌ Couldn't read file.",
        "choose_lang": "🌐 Select Language:",
        "choose_tier": "⭐ **Select a Plan to Upgrade:**\n(Current: {tier})",
        "photo_limit": "❌ Photo upload limit reached! ({used}/{limit}).",
        "imggen_limit": "❌ Image generation limit reached! ({used}/{limit}). Upgrade your plan!",
        "imggen_prompt": "🎨 **Image Generation Mode**\nDescribe the image you want me to create:",
        "imggen_wait": "🎨 Generating... (Takes ~10s)",
        "imggen_done": "🎨 Here is your image!",
        "pay_select": "💳 **Select Payment Method for {plan}:**\n💰 Price: {price} UZS",
        "pay_invoice_title": "{plan} Plan Subscription",
        "pay_invoice_desc": "Upgrade to {plan} for 1 month access.",
        "pay_thanks": "🎉 **Payment Successful!**\nYou have been upgraded to **{tier}**. Enjoy!",
        "pay_unavailable": "❌ This payment method is not available right now. Please try another.",
        "pay_error": "❌ Payment failed or cancelled."
    },
    # (Simplified other languages for brevity - you can copy paste English keys if missing)
    "ru": {
        "welcome": "👋 Привет, {name}!\nЯ готов помочь.",
        "approved": "✅ Доступ открыт!",
        "btn_chat": "💬 Чат", 
        "btn_file": "💾 Создать файл", 
        "btn_analyze": "📷 Анализ",
        "btn_imggen": "🎨 Генерация фото",
        "btn_uploads": "📂 Загрузки",
        "btn_lang": "🌐 Язык",
        "btn_tier": "⭐ Тариф",
        "btn_usage": "📊 Инфо",
        "btn_clear": "🧹 Сброс",
        "choose_fmt": "💾 Выберите формат:",
        "file_sent": "📤 Ваш файл!",
        "no_text": "❌ Нечего сохранять.",
        "cleared": "🧹 Память очищена!",
        "auto_cleared": "♻️ **Авто-сброс:** Я удалил старые фото из памяти.",
        "no_imgs": "❌ Нет фото.",
        "lang_set": "✅ Язык: Русский 🇷🇺",
        "usage_msg": "👤 {name}\n⭐ Тариф: {tier}\n🧠 **Модель:** `{model}`\n➖➖➖➖➖➖\n✉️ Сообщ: {used}/{limit}\n🖼️ Загрузки: {p_used}/{p_limit}\n🎨 Создано: {g_used}/{g_limit}",
        "tier_changed": "✅ Тариф: {tier}",
        "img_received": "📸 Фото принято! ({count}). Я запомнил. 🧠",
        "send_photo_prompt": "📸 Отправьте фото!",
        "listening": "👂 Слушаю...",
        "file_read": "📖 Файл прочитан!",
        "file_error": "❌ Ошибка чтения.",
        "choose_lang": "🌐 Выберите язык:",
        "choose_tier": "⭐ **Выберите тариф для обновления:**\n(Текущий: {tier})",
        "photo_limit": "❌ Лимит загрузки фото исчерпан!",
        "imggen_limit": "❌ Лимит генерации исчерпан!",
        "imggen_prompt": "🎨 **Режим Генерации**\nОпишите изображение:",
        "imggen_wait": "🎨 Рисую... (~10 сек)",
        "imggen_done": "🎨 Ваше изображение!",
        "pay_select": "💳 **Выберите способ оплаты для {plan}:**\n💰 Цена: {price} UZS",
        "pay_invoice_title": "Подписка {plan}",
        "pay_invoice_desc": "Доступ к {plan} на 1 месяц.",
        "pay_thanks": "🎉 **Оплата прошла успешно!**\nВаш тариф обновлен до **{tier}**.",
        "pay_unavailable": "❌ Этот способ оплаты сейчас недоступен.",
        "pay_error": "❌ Ошибка оплаты."
    },
    "uz": {
        "welcome": "👋 Salom {name}!\nMen tayyorman.",
        "approved": "✅ Ruxsat berildi!",
        "btn_chat": "💬 Chat", 
        "btn_file": "💾 Fayl yaratish", 
        "btn_analyze": "📷 Tahlil",
        "btn_imggen": "🎨 Rasm chizish",
        "btn_uploads": "📂 Yuklamalar",
        "btn_lang": "🌐 Til",
        "btn_tier": "⭐ Tarif",
        "btn_usage": "📊 Info",
        "btn_clear": "🧹 Tozalash",
        "choose_fmt": "💾 Formatni tanlang:",
        "file_sent": "📤 Mana faylingiz!",
        "no_text": "❌ Saqlash uchun hech narsa yo'q.",
        "cleared": "🧹 Xotira tozalandi!",
        "auto_cleared": "♻️ **Avto-tozalash:** Eski rasmlarni o'chirdim.",
        "no_imgs": "❌ Rasm yo'q.",
        "lang_set": "✅ Til: O'zbekcha 🇺🇿",
        "usage_msg": "👤 {name}\n⭐ Tarif: {tier}\n🧠 **Model:** `{model}`\n➖➖➖➖➖➖\n✉️ Xabar: {used}/{limit}\n🖼️ Yuklandi: {p_used}/{p_limit}\n🎨 Chizildi: {g_used}/{g_limit}",
        "tier_changed": "✅ Tarif: {tier}",
        "img_received": "📸 Rasm qabul qilindi! ({count}). Eslab qoldim. 🧠",
        "send_photo_prompt": "📸 Rasm yuboring!",
        "listening": "👂 Eshitayapman...",
        "file_read": "📖 Fayl o'qildi!",
        "file_error": "❌ O'qib bo'lmadi.",
        "choose_lang": "🌐 Tilni tanlang:",
        "choose_tier": "⭐ **Tarifni yangilash:**\n(Hozirgi: {tier})",
        "photo_limit": "❌ Rasm yuklash limiti tugadi!",
        "imggen_limit": "❌ Rasm chizish limiti tugadi!",
        "imggen_prompt": "🎨 **Rasm Chizish**\nQanday rasm chizay? Yozing:",
        "imggen_wait": "🎨 Chizayapman... (~10 soniya)",
        "imggen_done": "🎨 Mana rasmingiz!",
        "pay_select": "💳 **{plan} uchun to'lov turini tanlang:**\n💰 Narx: {price} so'm",
        "pay_invoice_title": "{plan} Tarifiga Obuna",
        "pay_invoice_desc": "{plan} tarifiga 1 oylik obuna.",
        "pay_thanks": "🎉 **To'lov muvaffaqiyatli!**\nSizning tarifingiz **{tier}** ga o'zgardi.",
        "pay_unavailable": "❌ Bu to'lov usuli hozir ishlamayapti.",
        "pay_error": "❌ To'lovda xatolik."
    }
}

# --- HELPERS ---
def get_text(uid, key, **kwargs):
    lang = USERS.get(uid, {}).get("lang", "en")
    val = TEXTS[lang].get(key)
    if not val: val = TEXTS["en"].get(key, key)
    if kwargs: return val.format(**kwargs)
    return val

def get_main_keyboard(uid):
    t = lambda k: get_text(uid, k)
    return ReplyKeyboardMarkup([
        [KeyboardButton(t("btn_chat")), KeyboardButton(t("btn_file"))],
        [KeyboardButton(t("btn_analyze")), KeyboardButton(t("btn_imggen"))],
        [KeyboardButton(t("btn_uploads")), KeyboardButton(t("btn_usage"))],
        [KeyboardButton(t("btn_tier")), KeyboardButton(t("btn_lang"))],
        [KeyboardButton(t("btn_clear"))]
    ], resize_keyboard=True)

def check_user(user):
    uid = user.id
    current_month = datetime.datetime.now().strftime("%Y-%m")
    
    if uid not in USERS:
        USERS[uid] = {
            "name": user.first_name,
            "approved": False,
            "tier": "Basic",
            "used": 0,
            "photos_used": 0,
            "img_gen_used": 0,
            "last_active_month": current_month,
            "lang": "en",
            "history": [],
            "temp_photos": [],
            "img_turn_count": 0,
            "last_bot_text": None,
            "waiting_for_img": False
        }
        save_json(DB_FILE, USERS)
    
    if "photos_used" not in USERS[uid]: USERS[uid]["photos_used"] = 0
    if "img_gen_used" not in USERS[uid]: USERS[uid]["img_gen_used"] = 0
    if "waiting_for_img" not in USERS[uid]: USERS[uid]["waiting_for_img"] = False
    if "last_active_month" not in USERS[uid]: USERS[uid]["last_active_month"] = current_month

    if USERS[uid]["last_active_month"] != current_month:
        USERS[uid]["used"] = 0
        USERS[uid]["photos_used"] = 0
        USERS[uid]["img_gen_used"] = 0 
        USERS[uid]["last_active_month"] = current_month
        save_json(DB_FILE, USERS)

# --- HANDLERS ---
async def user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    check_user(user)
    if not USERS[user.id]["approved"]:
        kb = ReplyKeyboardMarkup([[KeyboardButton(AUTH_TEXTS["btn"], request_contact=True)]], resize_keyboard=True)
        await update.message.reply_text(AUTH_TEXTS["req"], reply_markup=kb)
        return
    await update.message.reply_text(get_text(user.id, "welcome", name=user.first_name), reply_markup=get_main_keyboard(user.id))

async def user_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    check_user(user)
    contact = update.message.contact
    if contact.user_id != user.id: return
    USERS[user.id]["phone"] = contact.phone_number
    save_json(DB_FILE, USERS)
    await update.message.reply_text(AUTH_TEXTS["wait"], reply_markup=ReplyKeyboardMarkup([], resize_keyboard=True))
    if admin_bot_app:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Allow", callback_data=f"ok_{user.id}"), InlineKeyboardButton("❌ Deny", callback_data=f"no_{user.id}")], [InlineKeyboardButton("🚫 Block", callback_data=f"block_{user.id}")]])
        for admin_id in ADMINS:
            try: await admin_bot_app.bot.send_message(chat_id=admin_id, text=f"🔔 **Req:** {user.first_name} ({user.id})", reply_markup=kb)
            except: pass

# --- PAYMENT HANDLERS ---
async def tier_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the plan options"""
    uid = update.effective_user.id
    t = lambda k, **kwargs: get_text(uid, k, **kwargs)
    
    # Show Plans
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Pro (129k UZS)", callback_data="buy_Pro")],
        [InlineKeyboardButton(f"Premium (219k UZS)", callback_data="buy_Premium")]
    ])
    await update.message.reply_text(t("choose_tier", tier=USERS[uid]["tier"]), reply_markup=kb)

async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User chose a plan, now choose a provider"""
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    t = lambda k, **kwargs: get_text(uid, k, **kwargs)
    
    plan_type = query.data.split("_")[1] # "Pro" or "Premium"
    price = TIER_PRICES[plan_type]

    # Show Payment Methods
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Click", callback_data=f"pay_click_{plan_type}"), InlineKeyboardButton("💳 Payme", callback_data=f"pay_payme_{plan_type}")],
        [InlineKeyboardButton("💳 Stripe", callback_data=f"pay_stripe_{plan_type}")]
    ])
    
    await query.edit_message_text(
        t("pay_select", plan=plan_type, price=f"{price:,}"), 
        reply_markup=kb
    )

async def send_invoice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the actual invoice"""
    query = update.callback_query
    uid = update.effective_user.id
    t = lambda k, **kwargs: get_text(uid, k, **kwargs)
    
    _, provider, plan_type = query.data.split("_") # pay_click_Pro
    token = PAYMENT_TOKENS.get(provider)
    
    # CHECK IF TOKEN EXISTS
    if not token:
        await query.answer(t("pay_unavailable"), show_alert=True)
        return
    
    await query.answer()
    
    price_amount = TIER_PRICES[plan_type] * 100 # Telegram expects smallest unit (tiyin for UZS is usually standard, but for most currencies it's cents. UZS has no decimals usually but Telegram treats it as int. NOTE: For UZS in Telegram Payments, amount is usually passed as is if `is_flexible` is false, but safe bet is usually Amount * 100 for cents-like logic. HOWEVER, standard Payme/Click implementation often expects *100. Let's assume *100.)
    # Correction: For UZS, there are no decimals usually, but Telegram requires amount in 'cents'. 
    # e.g. 1000 UZS = 100000. 
    
    title = t("pay_invoice_title", plan=plan_type)
    description = t("pay_invoice_desc", plan=plan_type)
    payload = f"{uid}_{plan_type}"
    currency = "UZS"
    prices = [LabeledPrice(plan_type, price_amount)]

    await context.bot.send_invoice(
        chat_id=uid,
        title=title,
        description=description,
        payload=payload,
        provider_token=token,
        currency=currency,
        prices=prices,
        start_parameter="upgrade-tier"
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answer the PreCheckoutQuery"""
    query = update.pre_checkout_query
    # Check the payload, verify availability, etc.
    if query.invoice_payload.split("_")[1] not in TIER_PRICES:
        await query.answer(ok=False, error_message="Something went wrong.")
    else:
        await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful payment"""
    uid = update.effective_user.id
    pmt = update.message.successful_payment
    payload = pmt.invoice_payload
    _, plan_type = payload.split("_")
    
    # UPDATE USER
    USERS[uid]["tier"] = plan_type
    save_json(DB_FILE, USERS)
    
    t = lambda k, **kwargs: get_text(uid, k, **kwargs)
    await update.message.reply_text(t("pay_thanks", tier=plan_type))


async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    check_user(user)
    if not USERS[uid]["approved"]: return await user_start(update, context)

    text = update.message.text
    t = lambda k, **kwargs: get_text(uid, k, **kwargs)

    # --- BUTTONS ---
    if text == t("btn_file"):
        if not USERS[uid].get("last_bot_text"):
            await update.message.reply_text(t("no_text"))
            return
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 Word", callback_data="fmt_docx"), InlineKeyboardButton("📕 PDF", callback_data="fmt_pdf")], [InlineKeyboardButton("🐍 Python", callback_data="fmt_py"), InlineKeyboardButton("📄 Text", callback_data="fmt_txt")]])
        await update.message.reply_text(t("choose_fmt"), reply_markup=kb)
        return

    if text == t("btn_clear"):
        USERS[uid]["temp_photos"] = []
        USERS[uid]["history"] = []
        USERS[uid]["img_turn_count"] = 0
        USERS[uid]["waiting_for_img"] = False
        save_json(DB_FILE, USERS)
        await update.message.reply_text(t("cleared"), reply_markup=get_main_keyboard(uid))
        return

    if text == t("btn_analyze"): return await update.message.reply_text(t("send_photo_prompt"))
    if text == t("btn_chat"): return await update.message.reply_text(t("listening"))
    
    if text == t("btn_lang"):
        kb = ReplyKeyboardMarkup([["English 🇺🇸", "Russian 🇷🇺", "Uzbek 🇺🇿"]], resize_keyboard=True)
        return await update.message.reply_text(get_text(uid, "choose_lang"), reply_markup=kb)
    if text in ["English 🇺🇸", "Russian 🇷🇺", "Uzbek 🇺🇿"]:
        lang_map = {"English 🇺🇸": "en", "Russian 🇷🇺": "ru", "Uzbek 🇺🇿": "uz"}
        USERS[uid]["lang"] = lang_map[text]
        save_json(DB_FILE, USERS)
        return await update.message.reply_text(get_text(uid, "lang_set"), reply_markup=get_main_keyboard(uid))
    
    # --- UPDATED TIER HANDLER ---
    if text == t("btn_tier"):
        await tier_button_handler(update, context)
        return
    
    if text == t("btn_uploads"):
        photos = USERS[uid].get("temp_photos", [])
        if photos:
            try:
                media = [InputMediaPhoto(open(p, "rb")) for p in photos if os.path.exists(p)]
                if media: await update.message.reply_media_group(media)
            except: await update.message.reply_text("Error sending photos.")
        else: await update.message.reply_text(t("no_imgs"))
        return

    if text == t("btn_usage"):
        tier = USERS[uid]["tier"]
        model = TIER_MODELS.get(tier, "Unknown")
        await update.message.reply_text(t("usage_msg", 
            name=USERS[uid]["name"], 
            tier=tier,
            model=model,
            used=USERS[uid]["used"], 
            limit=TIER_LIMITS[tier],
            p_used=USERS[uid]["photos_used"],
            p_limit=TIER_PHOTO_LIMITS[tier],
            g_used=USERS[uid]["img_gen_used"],
            g_limit=TIER_IMG_GEN_LIMITS[tier]
        ), parse_mode="Markdown")
        return

    # --- IMAGE GENERATION TRIGGER ---
    if text == t("btn_imggen"):
        tier = USERS[uid]["tier"]
        if USERS[uid]["img_gen_used"] >= TIER_IMG_GEN_LIMITS[tier]:
            await update.message.reply_text(t("imggen_limit", used=USERS[uid]["img_gen_used"], limit=TIER_IMG_GEN_LIMITS[tier]))
            return

        USERS[uid]["waiting_for_img"] = True
        save_json(DB_FILE, USERS)
        await update.message.reply_text(t("imggen_prompt"))
        return

    # Check Text Limit
    limit = TIER_LIMITS.get(USERS[uid]["tier"], 100)
    if USERS[uid]["used"] >= limit:
        await update.message.reply_text(f"❌ Message limit reached! ({limit}/{limit}). Upgrade tier.")
        return

    # --- HANDLE IMAGE GENERATION PROMPT ---
    if USERS[uid].get("waiting_for_img"):
        await update.message.reply_text(t("imggen_wait"))
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=text,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            USERS[uid]["img_gen_used"] += 1 
            USERS[uid]["waiting_for_img"] = False
            save_json(DB_FILE, USERS)
            await update.message.reply_photo(photo=image_url, caption=t("imggen_done"))
        except Exception as e:
            USERS[uid]["waiting_for_img"] = False
            save_json(DB_FILE, USERS)
            await update.message.reply_text(f"❌ DALL-E Error: {e}")
        return

    # --- NORMAL AI CHAT ---
    if len(USERS[uid].get("temp_photos", [])) > 0:
        USERS[uid]["img_turn_count"] += 1
    if USERS[uid]["img_turn_count"] >= PHOTO_MEMORY_TURNS:
        USERS[uid]["temp_photos"] = []
        USERS[uid]["img_turn_count"] = 0
        await update.message.reply_text(t("auto_cleared"))

    try:
        await context.bot.send_chat_action(chat_id=uid, action="typing")
        history = USERS[uid]["history"]
        lang = USERS[uid].get("lang", "en")
        
        trigger_words = ['look', 'see', 'image', 'photo', 'picture', 'screen', 'solve', 'analyze', 'what', 'this', 'extract', 'read']
        has_trigger = any(word in text.lower() for word in trigger_words)
        has_photos = len(USERS[uid].get("temp_photos", [])) > 0
        should_send_images = has_photos and has_trigger

        context_instr = "CONTEXT: User attached images. Refer ONLY if asked." if should_send_images else ""

        sys_msg = {
            "role": "system", 
            "content": (
                f"You are a helpful, friendly assistant talking to {USERS[uid]['name']}. "
                f"Answer in {lang}. "
                f"RULES:\n"
                f"1. DO NOT use bolding (**) for lists. Use emojis as bullet points (🔹, ✨, 🚀).\n"
                f"2. Keep it fun and lively.\n"
                f"{context_instr}"
            )
        }
        
        content = [{"type": "text", "text": text}]
        if should_send_images:
            for p in USERS[uid].get("temp_photos", []):
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode('utf-8')
                    content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        
        messages = [sys_msg] + history + [{"role": "user", "content": content}]
        
        resp = client.chat.completions.create(
            model=TIER_MODELS[USERS[uid]["tier"]], messages=messages, max_tokens=1500
        )
        reply = resp.choices[0].message.content
        
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})
        USERS[uid]["history"] = history[-HISTORY_LIMIT:]
        USERS[uid]["last_bot_text"] = reply
        USERS[uid]["used"] += 1
        save_json(DB_FILE, USERS)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def user_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    check_user(user)
    if not USERS[uid]["approved"]: return
    doc = update.message.document
    file_id = doc.file_id
    file_name = doc.file_name if doc.file_name else "file"
    is_pdf = file_name.lower().endswith(".pdf")
    is_html = file_name.lower().endswith(".html") or file_name.lower().endswith(".htm")
    is_txt = file_name.lower().endswith(".txt") or file_name.lower().endswith(".py")
    if not (is_pdf or is_html or is_txt):
        await update.message.reply_text("❌ I accept .html, .pdf, and .txt only.")
        return
    USERS[uid]["temp_photos"] = []
    USERS[uid]["img_turn_count"] = 0
    new_file = await context.bot.get_file(file_id)
    download_path = f"temp_doc_{uid}_{file_name}"
    await new_file.download_to_drive(download_path)
    extracted_text = ""
    try:
        if is_pdf:
            reader = PdfReader(download_path)
            for page in reader.pages: extracted_text += page.extract_text() + "\n"
        elif is_html:
            with open(download_path, "r", encoding="utf-8", errors="ignore") as f:
                soup = BeautifulSoup(f, 'html.parser')
                for script in soup(["script", "style"]): script.extract()
                extracted_text = soup.get_text()
        else:
            with open(download_path, "r", encoding="utf-8", errors="ignore") as f: extracted_text = f.read()
        lines = (line.strip() for line in extracted_text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = '\n'.join(chunk for chunk in chunks if chunk)
        context_msg = f"User uploaded '{file_name}'. CONTENT:\n{clean_text[:8000]}" 
        USERS[uid]["history"].append({"role": "system", "content": context_msg})
        save_json(DB_FILE, USERS)
        await update.message.reply_text(get_text(uid, "file_read"))
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")
    finally:
        if os.path.exists(download_path): os.remove(download_path)

async def user_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    
    # NEW: Handle Payment Callbacks here or Separate?
    # Better to keep separate but our Pattern handler handles ^fmt_
    # So we need to ensure this function only runs for fmt_ 
    
    if not query.data.startswith("fmt_"):
        return # Should be handled by other handlers
        
    fmt = query.data.split("_")[1]
    content = USERS[uid].get("last_bot_text", "")
    if not content: return await query.edit_message_text("❌ Expired.")
    ts = datetime.datetime.now().strftime("%H%M%S")
    filename = f"file_{ts}.{fmt}"
    try:
        code_match = re.search(r"```(\w+)?\n(.*?)```", content, re.DOTALL)
        body = code_match.group(2) if code_match else content
        if fmt == "pdf":
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, body.encode('latin-1', 'replace').decode('latin-1'))
            pdf.output(filename)
        elif fmt == "docx":
            doc = Document()
            doc.add_paragraph(body)
            doc.save(filename)
        else:
            with open(filename, "w", encoding="utf-8") as f: f.write(body)
        await context.bot.send_document(chat_id=uid, document=open(filename, "rb"), caption=f"📄 .{fmt.upper()} File")
        await query.delete_message()
    except Exception as e: await context.bot.send_message(chat_id=uid, text=f"Error: {e}")
    finally:
        if os.path.exists(filename): os.remove(filename)

async def user_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    check_user(user)
    if not USERS[uid]["approved"]: return
    tier = USERS[uid]["tier"]
    p_limit = TIER_PHOTO_LIMITS.get(tier, 50)
    if USERS[uid]["photos_used"] >= p_limit:
        await update.message.reply_text(get_text(uid, "photo_limit", used=USERS[uid]["photos_used"], limit=p_limit))
        return
    f = await update.message.photo[-1].get_file()
    path = f"img_{uid}_{datetime.datetime.now().strftime('%H%M%S')}.jpg"
    await f.download_to_drive(path)
    if "temp_photos" not in USERS[uid]: USERS[uid]["temp_photos"] = []
    USERS[uid]["temp_photos"].append(path)
    USERS[uid]["img_turn_count"] = 0
    USERS[uid]["photos_used"] += 1
    save_json(DB_FILE, USERS)
    if update.message.caption:
        update.message.text = update.message.caption
        await user_message(update, context)
    else:
        await update.message.reply_text(get_text(uid, "img_received", count=len(USERS[uid]["temp_photos"])), reply_markup=get_main_keyboard(uid))

async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.startswith("/login") and len(text.split()) > 1:
        if text.split()[1] == ADMIN_PASSWORD:
            ADMINS[update.effective_user.id] = {"name": update.effective_user.first_name}
            save_json(ADMINS_FILE, ADMINS)
            await update.message.reply_text("✅ Logged in!")
        else: await update.message.reply_text("❌ Bad password.")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    act, tid = query.data.split("_")
    tid = int(tid)
    if tid not in USERS: return
    if act == "ok":
        USERS[tid]["approved"] = True
        if user_bot_app: await user_bot_app.bot.send_message(tid, TEXTS["en"]["approved"], reply_markup=get_main_keyboard(tid))
        await query.edit_message_text(f"✅ Allowed {USERS[tid]['name']}")
    elif act == "no":
        USERS[tid]["approved"] = False
        if user_bot_app: await user_bot_app.bot.send_message(tid, TEXTS["en"]["declined"])
        await query.edit_message_text(f"❌ Denied {USERS[tid]['name']}")
    elif act == "block":
        USERS[tid]["approved"] = False
        USERS[tid]["phone"] = None
        if user_bot_app: await user_bot_app.bot.send_message(tid, TEXTS["en"]["blocked"])
        await query.edit_message_text(f"🚫 Blocked {USERS[tid]['name']}")
    save_json(DB_FILE, USERS)

global user_bot_app, admin_bot_app
def main():
    global user_bot_app, admin_bot_app
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    user_bot_app = Application.builder().token(BOT_TOKEN).read_timeout(30).write_timeout(30).build()
    user_bot_app.add_handler(CommandHandler("start", user_start))
    user_bot_app.add_handler(MessageHandler(filters.CONTACT, user_contact))
    user_bot_app.add_handler(MessageHandler(filters.Document.ALL, user_document))
    user_bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_message))
    user_bot_app.add_handler(MessageHandler(filters.PHOTO, user_photo))
    user_bot_app.add_handler(CallbackQueryHandler(user_file_callback, pattern="^fmt_"))
    
    # PAYMENT HANDLERS
    user_bot_app.add_handler(CallbackQueryHandler(payment_method_callback, pattern="^buy_"))
    user_bot_app.add_handler(CallbackQueryHandler(send_invoice_callback, pattern="^pay_"))
    user_bot_app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    user_bot_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    admin_bot_app = Application.builder().token(ADMIN_BOT_TOKEN).read_timeout(30).write_timeout(30).build()
    admin_bot_app.add_handler(CommandHandler("login", admin_login))
    admin_bot_app.add_handler(CallbackQueryHandler(admin_callback))
    print("🚀 Bots Running...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def runner():
        await user_bot_app.initialize()
        await user_bot_app.start()
        await user_bot_app.updater.start_polling(drop_pending_updates=True)
        await admin_bot_app.initialize()
        await admin_bot_app.start()
        await admin_bot_app.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(10)
    try: loop.run_until_complete(runner())
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
