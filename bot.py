import os
import logging
import random
import sqlite3
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
GAME_URL = 'https://jazzy-chimera-90a9b9.netlify.app'
CHANNEL_URL = 'https://t.me/fpv_bank_game_channel'
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ========== БАЗА ДАННЫХ С SQLITE ==========
conn = sqlite3.connect('fpv_bank.db', check_same_thread=False)
cursor = conn.cursor()

# Таблица пользователей
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance INTEGER DEFAULT 0,
        total_clicks INTEGER DEFAULT 0,
        best_combo INTEGER DEFAULT 0,
        chests_opened INTEGER DEFAULT 0,
        games_played INTEGER DEFAULT 0,
        daily_streak INTEGER DEFAULT 0,
        last_daily DATE,
        join_date DATE,
        achievement1 INTEGER DEFAULT 0,
        achievement2 INTEGER DEFAULT 0,
        achievement3 INTEGER DEFAULT 0,
        achievement4 INTEGER DEFAULT 0,
        achievement5 INTEGER DEFAULT 0,
        achievement6 INTEGER DEFAULT 0,
        companion_level INTEGER DEFAULT 1,
        companion_exp INTEGER DEFAULT 0,
        companion_type TEXT DEFAULT 'basic',
        drone_emotion TEXT DEFAULT '😊'
    )
''')

# Таблица рефералов
cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        date DATE,
        bonus_claimed INTEGER DEFAULT 0
    )
''')

# Таблица истории
cursor.execute('''
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        amount INTEGER,
        date DATE
    )
''')
conn.commit()

# ========== КЛАСС ДЛЯ РАБОТЫ С БД ==========
class Database:
    @staticmethod
    def get_user(user_id):
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'first_name': row[2],
                'balance': row[3],
                'total_clicks': row[4],
                'best_combo': row[5],
                'chests_opened': row[6],
                'games_played': row[7],
                'daily_streak': row[8],
                'last_daily': row[9],
                'join_date': row[10],
                'ach1': row[11],
                'ach2': row[12],
                'ach3': row[13],
                'ach4': row[14],
                'ach5': row[15],
                'ach6': row[16],
                'companion_level': row[17],
                'companion_exp': row[18],
                'companion_type': row[19],
                'drone_emotion': row[20]
            }
        return None
    
    @staticmethod
    def create_user(user_id, username, first_name, referrer=None):
        cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, join_date, drone_emotion)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, datetime.now().date(), '😊'))
        conn.commit()
        
        if referrer and referrer != user_id:
            cursor.execute('''
                INSERT INTO referrals (referrer_id, referred_id, date)
                VALUES (?, ?, ?)
            ''', (referrer, user_id, datetime.now().date()))
            conn.commit()
            
            # Бонус пригласившему
            Database.update_balance(referrer, 200)
            Database.add_history(referrer, 'referral_bonus', 200)
    
    @staticmethod
    def update_balance(user_id, amount):
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
    
    @staticmethod
    def get_balance(user_id):
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0
    
    @staticmethod
    def update_stats(user_id, clicks=0, combo=0, chests=0, games=0):
        cursor.execute('''
            UPDATE users SET 
                total_clicks = total_clicks + ?,
                best_combo = MAX(best_combo, ?),
                chests_opened = chests_opened + ?,
                games_played = games_played + ?
            WHERE user_id = ?
        ''', (clicks, combo, chests, games, user_id))
        conn.commit()
    
    @staticmethod
    def update_achievement(user_id, ach_num):
        cursor.execute(f'UPDATE users SET achievement{ach_num} = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
    
    @staticmethod
    def add_history(user_id, action, amount):
        cursor.execute('''
            INSERT INTO history (user_id, action, amount, date)
            VALUES (?, ?, ?, ?)
        ''', (user_id, action, amount, datetime.now()))
        conn.commit()
    
    @staticmethod
    def get_history(user_id, limit=5):
        cursor.execute('''
            SELECT action, amount, date FROM history 
            WHERE user_id = ? ORDER BY date DESC LIMIT ?
        ''', (user_id, limit))
        return cursor.fetchall()
    
    @staticmethod
    def get_referral_count(user_id):
        cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
        return cursor.fetchone()[0]
    
    @staticmethod
    def get_referral_earnings(user_id):
        cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
        count = cursor.fetchone()[0]
        return count * 200
    
    @staticmethod
    def update_companion(user_id, exp=1):
        cursor.execute('''
            UPDATE users SET 
                companion_exp = companion_exp + ?
            WHERE user_id = ?
        ''', (exp, user_id))
        
        # Проверка на повышение уровня
        cursor.execute('''
            SELECT companion_level, companion_exp FROM users WHERE user_id = ?
        ''', (user_id,))
        level, exp = cursor.fetchone()
        
        if exp >= level * 100:
            cursor.execute('''
                UPDATE users SET 
                    companion_level = companion_level + 1,
                    companion_exp = 0
                WHERE user_id = ?
            ''', (user_id,))
            return True
        return False
    
    @staticmethod
    def set_emotion(user_id, emotion):
        cursor.execute('UPDATE users SET drone_emotion = ? WHERE user_id = ?', (emotion, user_id))
        conn.commit()
    
    @staticmethod
    def get_emotion(user_id):
        cursor.execute('SELECT drone_emotion FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else '😊'

db = Database()

# ========== СТИЛИ ДЛЯ КРАСИВЫХ СООБЩЕНИЙ ==========
STYLES = {
    'title': '╔══════════════════════╗\n║      {}      ║\n╚══════════════════════╝',
    'section': '┌──────────────────────┐\n│ {} │\n└──────────────────────┘',
    'line': '────────────────────────',
    'stats': '📊 *Статистика*',
    'profile': '👤 *Профиль*',
    'game': '🎮 *Игры*',
    'bonus': '🎁 *Бонусы*'
}

# ========== СЛУЧАЙНЫЕ ФАКТЫ ==========
FACTS = [
    "🚁 Дрон может летать до 30 минут без подзарядки!",
    "💰 Самый богатый игрок заработал 1,234,567 FPV!",
    "🎲 Шанс выпадения легендарного кейса всего 3%",
    "🔥 Перегрев длится 5 секунд — не кликай зря!",
    "🤖 Компаньоны приносят до 5 FPV в секунду",
    "📦 В игре 6 видов кейсов с разными шансами",
    "⚡️ Комбо x10 дает двойной доход!",
    "🏆 Таблица лидеров обновляется каждый час",
    "🎮 Мини-игры приносят до 1000 FPV за победу",
    "💎 Кристаллы можно получить за ежедневный вход"
]

# ========== ПОГОДНЫЕ ЭФФЕКТЫ ==========
WEATHER = [
    ("☀️ Солнечно", 1.2, "доход +20%"),
    ("🌧 Дождливо", 1.5, "энергия +50%"),
    ("⚡️ Гроза", 2.0, "крит шанс x2"),
    ("❄️ Снег", 0.8, "охлаждение быстрее"),
    ("🌈 Радуга", 3.0, "ВСЕ БОНУСЫ!")
]

# ========== СЕКРЕТНЫЕ КОМАНДЫ ==========
SECRET_COMMANDS = {
    '🚁': 'Ты нашел секрет! +100 FPV',
    '💰': 'Монетный дождь! +500 FPV',
    '🔥': 'Огненный бонус! +200 FPV',
    '🎲': 'Удача на твоей стороне! +1 кейс'
}

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚁 ЗАПУСТИТЬ ИГРУ", web_app=WebAppInfo(url=GAME_URL)))
    builder.row(
        InlineKeyboardButton(text="📊 ПРОФИЛЬ", callback_data="profile"),
        InlineKeyboardButton(text="📢 КАНАЛ", url=CHANNEL_URL)
    )
    builder.row(
        InlineKeyboardButton(text="🎮 ИГРЫ", callback_data="games"),
        InlineKeyboardButton(text="🎁 БОНУСЫ", callback_data="bonus")
    )
    builder.row(
        InlineKeyboardButton(text="📚 ФАКТЫ", callback_data="fact"),
        InlineKeyboardButton(text="🌤 ПОГОДА", callback_data="weather")
    )
    builder.row(InlineKeyboardButton(text="👥 РЕФЕРАЛЫ", callback_data="referrals"))
    return builder.as_markup()

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")]
    ])

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ''
    first_name = message.from_user.first_name or ''
    
    # Проверка реферала
    args = message.text.split()
    referrer = None
    if len(args) > 1 and args[1].startswith('ref_'):
        try:
            referrer = int(args[1].replace('ref_', ''))
        except:
            pass
    
    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, username, first_name, referrer)
        db.add_history(user_id, 'start_bonus', 100)
        
        welcome_text = (
            f"✨ *ДОБРО ПОЖАЛОВАТЬ, {first_name.upper()}!*\n\n"
            f"┌──────────────────────┐\n"
            f"│ 🚁 Ты в FPV BANK      │\n"
            f"│ 💰 Стартовый бонус: 100 FPV │\n"
            f"│ 🌟 Дрон готов к полету!    │\n"
            f"└──────────────────────┘\n\n"
            f"👇 *Нажми на кнопку, чтобы начать*"
        )
    else:
        # Ежедневный бонус
        today = datetime.now().date()
        last_daily = user['last_daily']
        
        if last_daily:
            last_date = datetime.strptime(last_daily, '%Y-%m-%d').date() if isinstance(last_daily, str) else last_daily
            if last_date == today - timedelta(days=1):
                streak = user['daily_streak'] + 1
                cursor.execute('UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?', 
                             (streak, today, user_id))
                conn.commit()
                
                if streak % 7 == 0:
                    db.update_balance(user_id, 500)
                    db.add_history(user_id, 'weekly_bonus', 500)
            elif last_date != today:
                cursor.execute('UPDATE users SET daily_streak = 1, last_daily = ? WHERE user_id = ?', 
                             (today, user_id))
                conn.commit()
                db.update_balance(user_id, 50)
                db.add_history(user_id, 'daily_bonus', 50)
        else:
            cursor.execute('UPDATE users SET daily_streak = 1, last_daily = ? WHERE user_id = ?', 
                         (today, user_id))
            conn.commit()
            db.update_balance(user_id, 50)
            db.add_history(user_id, 'daily_bonus', 50)
        
        # Меняем эмоцию дрона
        emotions = ['😊', '😎', '🚁', '✨', '🌟']
        db.set_emotion(user_id, random.choice(emotions))
        
        welcome_text = (
            f"🚁 *С ВОЗВРАЩЕНИЕМ, {first_name.upper()}!*\n\n"
            f"┌──────────────────────┐\n"
            f"│ {db.get_emotion(user_id)} Твой дрон скучал!       │\n"
            f"│ 🔥 Стрик: {user['daily_streak']} дней         │\n"
            f"│ 💰 Баланс: {user['balance']} FPV          │\n"
            f"└──────────────────────┘"
        )
    
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# ========== ПРОФИЛЬ ==========
@dp.callback_query(F.data == 'profile')
async def show_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        await callback.answer("❌ Ошибка загрузки")
        return
    
    # Проверка достижений
    achievements = []
    if user['total_clicks'] >= 1000 and not user['ach1']:
        db.update_achievement(user_id, 1)
        achievements.append("🔥 1000 кликов! +500 FPV")
        db.update_balance(user_id, 500)
    
    if user['best_combo'] >= 10 and not user['ach2']:
        db.update_achievement(user_id, 2)
        achievements.append("⚡️ Комбо x10! +500 FPV")
        db.update_balance(user_id, 500)
    
    if user['balance'] >= 10000 and not user['ach3']:
        db.update_achievement(user_id, 3)
        achievements.append("💰 10к монет! +1000 FPV")
        db.update_balance(user_id, 1000)
    
    if user['chests_opened'] >= 10 and not user['ach4']:
        db.update_achievement(user_id, 4)
        achievements.append("📦 10 кейсов! +500 FPV")
        db.update_balance(user_id, 500)
    
    if user['games_played'] >= 5 and not user['ach5']:
        db.update_achievement(user_id, 5)
        achievements.append("🎮 5 игр! +500 FPV")
        db.update_balance(user_id, 500)
    
    if user['companion_level'] >= 3 and not user['ach6']:
        db.update_achievement(user_id, 6)
        achievements.append("🐉 Компаньон 3 ур! +1000 FPV")
        db.update_balance(user_id, 1000)
    
    # Статистика
    referrals = db.get_referral_count(user_id)
    referral_earnings = db.get_referral_earnings(user_id)
    history = db.get_history(user_id)
    
    text = (
        f"👤 *ПРОФИЛЬ ПИЛОТА*\n"
        f"┌──────────────────────┐\n"
        f"│ 🆔 ID: `{user_id}`\n"
        f"│ 📛 Имя: {user['first_name']}\n"
        f"│ 🤖 Дрон: {user['drone_emotion']}\n"
        f"├──────────────────────┤\n"
        f"│ 💰 Баланс: {user['balance']} FPV\n"
        f"│ 🔥 Стрик: {user['daily_streak']} дней\n"
        f"│ 🖱 Кликов: {user['total_clicks']}\n"
        f"│ ⚡️ Комбо: {user['best_combo']}\n"
        f"│ 📦 Кейсов: {user['chests_opened']}\n"
        f"│ 🎮 Игр: {user['games_played']}\n"
        f"├──────────────────────┤\n"
        f"│ 🐉 Компаньон: ур.{user['companion_level']}\n"
        f"│ ⭐️ Опыт: {user['companion_exp']}/{user['companion_level']*100}\n"
        f"├──────────────────────┤\n"
        f"│ 👥 Рефералов: {referrals}\n"
        f"│ 💰 Заработано: {referral_earnings} FPV\n"
        f"└──────────────────────┘"
    )
    
    if achievements:
        text += "\n\n✨ *НОВЫЕ ДОСТИЖЕНИЯ:*\n" + "\n".join(achievements)
    
    # Последние действия
    if history:
        text += "\n\n📋 *ПОСЛЕДНИЕ ДЕЙСТВИЯ:*\n"
        for action, amount, date in history[:3]:
            date_str = date.split('.')[0][11:16] if isinstance(date, str) else ''
            text += f"• {action}: {amount:+d} FPV\n"
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_back_keyboard())
    await callback.answer()

# ========== СЛУЧАЙНЫЙ ФАКТ ==========
@dp.callback_query(F.data == 'fact')
async def show_fact(callback: types.CallbackQuery):
    fact = random.choice(FACTS)
    await callback.message.edit_text(
        f"📚 *ЗНАЕШЬ ЛИ ТЫ?*\n\n{fact}\n\n*Хочешь еще фактов?*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ЕЩЕ ФАКТ", callback_data="fact"),
             InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")]
        ])
    )
    await callback.answer()

# ========== ПОГОДА ==========
@dp.callback_query(F.data == 'weather')
async def show_weather(callback: types.CallbackQuery):
    weather, multiplier, bonus = random.choice(WEATHER)
    await callback.message.edit_text(
        f"🌤 *ПОГОДА В ИГРЕ*\n\n"
        f"┌──────────────────────┐\n"
        f"│ {weather}         \n"
        f"│ 📈 {bonus}        \n"
        f"│ ✨ Множитель: x{multiplier}   \n"
        f"└──────────────────────┘\n\n"
        f"*Погода влияет на твой доход!*",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

# ========== РЕФЕРАЛЫ ==========
@dp.callback_query(F.data == 'referrals')
async def show_referrals(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ref_link = f"https://t.me/{(await bot.me()).username}?start=ref_{user_id}"
    count = db.get_referral_count(user_id)
    earnings = db.get_referral_earnings(user_id)
    
    text = (
        f"👥 *РЕФЕРАЛЬНАЯ СИСТЕМА*\n\n"
        f"┌──────────────────────┐\n"
        f"│ 🔗 *Твоя ссылка:*    \n"
        f"│ `{ref_link}`\n"
        f"├──────────────────────┤\n"
        f"│ 👤 Приглашено: {count}\n"
        f"│ 💰 Заработано: {earnings} FPV\n"
        f"├──────────────────────┤\n"
        f"│ 🎁 За каждого друга:  \n"
        f"│ • Ты получаешь 200 FPV\n"
        f"│ • Друг получает 100 FPV\n"
        f"└──────────────────────┘\n\n"
        f"👇 *Нажми на ссылку, чтобы скопировать*"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 КОПИРОВАТЬ ССЫЛКУ", callback_data="copy_ref")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == 'copy_ref')
async def copy_ref(callback: types.CallbackQuery):
    await callback.answer("✅ Ссылка скопирована! Отправь её друзьям", show_alert=True)

# ========== ИГРЫ ==========
@dp.callback_query(F.data == 'games')
async def show_games(callback: types.CallbackQuery):
    text = (
        f"🎮 *МИНИ-ИГРЫ*\n\n"
        f"┌──────────────────────┐\n"
        f"│ 🎯 *Угадай число*    \n"
        f"│    от 1 до 10        \n"
        f"│    Ставка: 50 FPV    \n"
        f"│    Выигрыш: x10      \n"
        f"├──────────────────────┤\n"
        f"│ 🔮 *Орёл-решка*      \n"
        f"│    Угадай исход      \n"
        f"│    Ставка: 30 FPV    \n"
        f"│    Выигрыш: x2       \n"
        f"├──────────────────────┤\n"
        f"│ 🎲 *Кости*           \n"
        f"│    Брось кубик       \n"
        f"│    Ставка: 20 FPV    \n"
        f"│    Выигрыш: x6       \n"
        f"└──────────────────────┘\n\n"
        f"👇 *Выбери игру*"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 УГАДАЙ ЧИСЛО", callback_data="game_guess")],
        [InlineKeyboardButton(text="🔮 ОРЁЛ-РЕШКА", callback_data="game_flip")],
        [InlineKeyboardButton(text="🎲 КОСТИ", callback_data="game_dice")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

# Игра: Угадай число
@dp.callback_query(F.data == 'game_guess')
async def game_guess(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    balance = db.get_balance(user_id)
    
    if balance < 50:
        await callback.answer("❌ Недостаточно монет! Нужно 50 FPV", show_alert=True)
        return
    
    number = random.randint(1, 10)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(i), callback_data=f"guess_{i}_{number}") for i in range(1, 6)],
        [InlineKeyboardButton(text=str(i), callback_data=f"guess_{i}_{number}") for i in range(6, 11)],
        [InlineKeyboardButton(text="◀️ ОТМЕНА", callback_data="games")]
    ])
    
    await callback.message.edit_text(
        f"🎯 *УГАДАЙ ЧИСЛО*\n\n"
        f"💰 Твой баланс: {balance} FPV\n"
        f"💎 Ставка: 50 FPV\n"
        f"🎁 Выигрыш: 500 FPV (x10)\n\n"
        f"👇 *Выбери число от 1 до 10:*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith('guess_'))
async def process_guess(callback: types.CallbackQuery):
    _, guess, secret = callback.data.split('_')
    guess = int(guess)
    secret = int(secret)
    user_id = callback.from_user.id
    
    db.update_balance(user_id, -50)
    
    if guess == secret:
        win = 500
        db.update_balance(user_id, win)
        db.add_history(user_id, 'game_win', win)
        db.update_stats(user_id, games=1)
        result = f"🎉 *ПОБЕДА!*\n\nЗагадано число {secret}\nТы выиграл {win} FPV!"
    else:
        db.add_history(user_id, 'game_lose', -50)
        result = f"😢 *ПРОИГРЫШ*\n\nЗагадано число {secret}\nТы потерял 50 FPV"
    
    await callback.message.edit_text(
        result,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ЕЩЕ", callback_data="game_guess"),
             InlineKeyboardButton(text="◀️ НАЗАД", callback_data="games")]
        ])
    )
    await callback.answer()

# ========== БОНУСЫ ==========
@dp.callback_query(F.data == 'bonus')
async def show_bonus(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    
    # Случайный бонус дня
    bonus_type = random.choice(['coins', 'exp', 'chest', 'nothing'])
    bonus_values = {'coins': 100, 'exp': 50, 'chest': 1, 'nothing': 0}
    bonus_names = {'coins': '💰 Монеты', 'exp': '⚡️ Опыт', 'chest': '📦 Кейс', 'nothing': '😢 Увы'}
    
    bonus_value = bonus_values[bonus_type]
    if bonus_type == 'coins':
        db.update_balance(user_id, bonus_value)
        db.add_history(user_id, 'daily_bonus', bonus_value)
    elif bonus_type == 'exp':
        db.update_companion(user_id, bonus_value)
    elif bonus_type == 'chest':
        db.update_stats(user_id, chests=1)
    
    text = (
        f"🎁 *БОНУС ДНЯ*\n\n"
        f"┌──────────────────────┐\n"
        f"│ ✨ *Ты получил:*      \n"
        f"│ {bonus_names[bonus_type]} +{bonus_value if bonus_value > 0 else ''}\n"
        f"├──────────────────────┤\n"
        f"│ 🔥 Твой стрик: {user['daily_streak']} дней\n"
        f"│ 📅 Заходи каждый день!\n"
        f"└──────────────────────┘"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

# ========== СЕКРЕТНЫЕ КОМАНДЫ ПО ЭМОДЗИ ==========
@dp.message(F.text)
async def secret_commands(message: types.Message):
    text = message.text.strip()
    user_id = message.from_user.id
    
    # Секретные команды эмодзи
    if text in SECRET_COMMANDS:
        reward_text = SECRET_COMMANDS[text]
        db.update_balance(user_id, 100)
        db.add_history(user_id, 'secret_found', 100)
        await message.reply(f"🎉 *СЕКРЕТ НАЙДЕН!*\n\n{reward_text}", parse_mode="Markdown")
        return
    
    # Реакция на имя
    if 'бот' in text.lower() or 'fpv' in text.lower():
        reactions = [
            "🚁 Я тут! Чего хочешь, пилот?",
            "🎮 Сыграем? У меня есть кнопка в меню!",
            "💰 Хочешь заработать? Жми /start",
            "😊 Я скучал! Давай играть!"
        ]
        await message.reply(random.choice(reactions))
    
    # Поздравление с рекордом
    if 'рекорд' in text.lower() or 'топ' in text.lower():
        user = db.get_user(user_id)
        if user:
            await message.reply(
                f"🎉 *ТВОЙ РЕКОРД!*\n\n"
                f"🔥 Лучшее комбо: {user['best_combo']}\n"
                f"💰 Всего заработано: {user['balance']} FPV\n"
                f"📦 Открыто кейсов: {user['chests_opened']}",
                parse_mode="Markdown"
            )

# ========== НАЗАД ==========
@dp.callback_query(F.data == 'back')
async def go_back(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if user:
        await callback.message.edit_text(
            f"🚁 *ГЛАВНОЕ МЕНЮ*\n\n"
            f"┌──────────────────────┐\n"
            f"│ {db.get_emotion(callback.from_user.id)} Привет, {user['first_name']}!\n"
            f"│ 💰 Баланс: {user['balance']} FPV\n"
            f"│ 🔥 Стрик: {user['daily_streak']} дней\n"
            f"└──────────────────────┘",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await cmd_start(callback.message)
    await callback.answer()

# ========== ЗАПУСК ==========
async def main():
    await bot.delete_webhook()
    print("✅ Бот запущен!")
    print(f"📱 Игра: {GAME_URL}")
    print(f"📢 Канал: {CHANNEL_URL}")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())