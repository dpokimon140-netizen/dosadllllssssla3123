import os
import logging
import random
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
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

# ========== БАЗА ДАННЫХ ==========
conn = sqlite3.connect('fpv_bank.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance INTEGER DEFAULT 90,
        total_clicks INTEGER DEFAULT 0,
        best_combo INTEGER DEFAULT 0,
        chests_opened INTEGER DEFAULT 0,
        games_played INTEGER DEFAULT 0,
        daily_streak INTEGER DEFAULT 0,
        last_daily DATE,
        join_date DATE
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        amount INTEGER,
        details TEXT,
        date DATE
    )
''')
conn.commit()

# ========== ФАКТЫ ==========
FACTS = [
    "👨‍💻 Игра была создана всего за 30 дней одним разработчиком!",
    "☕ Разработчик выпил 50 литров чая пока делал эту игру",
    "🐛 В бета-тесте нашли и исправили 19+ багов",
    "🚀 Первая версия игры вышла в Марте 2026",
    "💡 Идея игры пришла разработчику во сне",
    "📱 FPV Bank работает на всех устройствах с Telegram",
    "⚡️ Сервер бота находится в США, но играет быстро везде",
    "🔄 База данных переписывалась 3 раза с нуля",
    "🎨 Дизайн игры переделывали 5 раз пока не стало красиво",
    "🤝 Никто не верил в успех, но игра работает!",
    "👥 В игре уже зарегистрировано 100+ пилотов",
    "🖱️ Все игроки сделали более 100000 тысяч кликов",
    "💰 В сумме заработано 10 миллионов FPV",
    "🎲 Самый везучий игрок открыл 3 легендарки подряд",
    "🐉 Компаньон 'Старый' самый популярный среди новичков",
    "🔥 Рекорд по кликам за минуту — 54!",
    "📅 Самый преданный игрок заходит уже 6 дней подряд",
    "🎮 В мини-игры сыграли уже 50+ раз",
    "💎 Один игрок накопил 25940 FPV за день",
    "🏆 Топ-1 игрок пока только формируется"
]

# ========== ФУНКЦИИ БД ==========
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
            'join_date': row[10]
        }
    return None

def create_user(user_id, username, first_name):
    cursor.execute('''
        INSERT OR IGNORE INTO users 
        (user_id, username, first_name, join_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, datetime.now().date()))
    conn.commit()

def update_balance(user_id, amount):
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()

def get_balance(user_id):
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

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

def add_history(user_id, action, amount, details):
    cursor.execute('''
        INSERT INTO history (user_id, action, amount, details, date)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, action, amount, details, datetime.now()))
    conn.commit()

def get_history(user_id, limit=10):
    cursor.execute('''
        SELECT action, amount, details, date FROM history 
        WHERE user_id = ? ORDER BY date DESC LIMIT ?
    ''', (user_id, limit))
    return cursor.fetchall()

def update_daily_streak(user_id):
    today = datetime.now().date()
    user = get_user(user_id)
    
    if user and user['last_daily']:
        last = datetime.strptime(user['last_daily'], '%Y-%m-%d').date()
        if last == today - timedelta(days=1):
            streak = user['daily_streak'] + 1
            cursor.execute('UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?', 
                         (streak, today, user_id))
            conn.commit()
            return streak
        elif last != today:
            cursor.execute('UPDATE users SET daily_streak = 1, last_daily = ? WHERE user_id = ?', 
                         (today, user_id))
            conn.commit()
            return 1
    else:
        cursor.execute('UPDATE users SET daily_streak = 1, last_daily = ? WHERE user_id = ?', 
                     (today, user_id))
        conn.commit()
        return 1
    return user['daily_streak'] if user else 0

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚀 ЗАПУСТИТЬ ИГРУ", web_app=WebAppInfo(url=GAME_URL)))
    builder.row(
        InlineKeyboardButton(text="📢", url=CHANNEL_URL),
        InlineKeyboardButton(text="ℹ️", callback_data="about"),
        InlineKeyboardButton(text="❓", callback_data="fact"),
        InlineKeyboardButton(text="📜", callback_data="history")
    )
    return builder.as_markup()

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")]
    ])

def get_fact_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 ЕЩЕ ФАКТ", callback_data="fact"),
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")
        ]
    ])

def get_history_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="history"),
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")
        ]
    ])

# ========== СТАРТ ==========
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ''
    first_name = message.from_user.first_name or ''
    
    user = get_user(user_id)
    if not user:
        create_user(user_id, username, first_name)
        update_balance(user_id, 90)
        add_history(user_id, 'start', 0, 'Запустил бота')
    
    streak = update_daily_streak(user_id)
    if streak > 1:
        add_history(user_id, 'daily_streak', 50, f'Ежедневный бонус (день {streak})')
        update_balance(user_id, 50)
    
    text = (
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "     🚁 FPV BANK GAME    \n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "        v2.0 beta        \n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "          \n"
        "🖱️  КЛИКЕР\n"
        "🐉  КОМПАНЬОНЫ\n"
        "🎲  КЕЙСЫ\n"
        "🎮  МИНИ-ИГРЫ\n"
        "🎁  БОНУСЫ\n"
        "          \n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "   🔥 ПОЧЕМУ СЕЙЧАС? 🔥\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✓ Бонус 90 FPV при регистрации\n"
        "✓ Удвоенные шансы в кейсах\n"
        "✓ Эксклюзивный компаньон для первых 100\n"
        "✓ Бета-доступ уже открыт\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    await message.answer(text, reply_markup=get_main_keyboard())

# ========== О ИГРЕ ==========
@dp.callback_query(lambda c: c.data == 'about')
async def show_about(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    add_history(user_id, 'about', 0, 'Открыл раздел "О игре"')
    
    text = (
        "╭────────────────────────╮\n"
        "│   🚁 FPV BANK GAME     │\n"
        "│   РАССКАЗЫВАЕМ         │\n"
        "╰────────────────────────╯\n\n"
        "👋 Привет! Это FPV Bank.\n\n"
        "───────── ЧТО ЗА ИГРА? ───────\n"
        "Мы сделали кликер про дронов.\n"
        "Ты просто кликаешь по дрону,\n"
        "а он приносит тебе монеты.\n"
        "Чем больше кликаешь — тем\n"
        "больше зарабатываешь!\n\n"
        "───────── КАК ИГРАТЬ? ────────\n"
        "🖱️  Кликай по дрону — получай FPV\n"
        "⚡️ 10+ быстрых кликов = x2 доход\n"
        "🔥 Следи за перегревом (красная шкала)\n"
        "🔋 Энергия восстанавливается со временем\n"
        "💰 Копи монеты и покупай апгрейды\n\n"
        "───────── ЧТО ТУТ ЕСТЬ? ───────\n"
        "🖱️  Кликер (энергия, перегрев, комбо)\n"
        "🐉  Компаньоны (помогают зарабатывать)\n"
        "🎲  Кейсы (удача, азарт, шансы)\n"
        "🎮  Мини-игры (отдохни от кликов)\n"
        "🎁  Бонусы и промокоды\n\n"
        "───────── НОВОСТИ ──────────────\n"
        "📢 Канал: @fpv_bank_game_channel\n"
        "📅 Запуск: Март 2026\n"
        "⭐️ Версия: 2.0 (бета)\n"
        "✅ Бот работает 24/7\n"
        "🔥 Уже 100+ игроков"
    )
    
    await callback.message.edit_text(text, reply_markup=get_back_keyboard())
    await callback.answer()

# ========== ФАКТ ==========
@dp.callback_query(lambda c: c.data == 'fact')
async def show_fact(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    fact_number = random.randint(1, len(FACTS))
    fact = random.choice(FACTS)
    
    add_history(user_id, 'fact', 0, f'Открыл факт #{fact_number}')
    
    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "   🚁 ЗНАЕШЬ ЛИ ТЫ?\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📚 ФАКТ #{fact_number}\n\n"
        f"{fact}\n\n"
        "⚡️ Хочешь побить рекорд?\n"
        "Жми 🚀 ИГРАТЬ!"
    )
    
    await callback.message.edit_text(text, reply_markup=get_fact_keyboard())
    await callback.answer()

# ========== ИСТОРИЯ ==========
@dp.callback_query(lambda c: c.data == 'history')
async def show_history(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    history = get_history(user_id)
    balance = get_balance(user_id)
    
    add_history(user_id, 'history', 0, 'Посмотрел историю действий')
    
    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "   📜 ИСТОРИЯ ДЕЙСТВИЙ\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "⏱️ Последние действия в боте:\n\n"
    )
    
    if not history:
        text += (
            "😢 История пока пуста\n\n"
            "👇 Нажимай на кнопки, чтобы\n"
            "она начала заполняться!"
        )
    else:
        for action, amount, details, date in history[:8]:
            # Парсим время
            if isinstance(date, str):
                try:
                    date_obj = datetime.fromisoformat(date)
                    now = datetime.now()
                    diff = now - date_obj
                    
                    if diff.seconds < 60:
                        time_str = "только что"
                    elif diff.seconds < 3600:
                        minutes = diff.seconds // 60
                        time_str = f"{minutes} мин назад"
                    elif diff.seconds < 86400:
                        hours = diff.seconds // 3600
                        time_str = f"{hours} ч назад"
                    else:
                        days = diff.days
                        time_str = f"{days} дн назад"
                except:
                    time_str = "недавно"
            else:
                time_str = "недавно"
            
            # Эмодзи для разных действий
            if 'запустил игру' in details.lower() or '🚀' in details:
                emoji = "🚀"
            elif 'о игре' in details.lower() or 'about' in action:
                emoji = "ℹ️"
            elif 'факт' in details.lower():
                emoji = "❓"
            elif 'история' in details.lower():
                emoji = "📜"
            elif 'канал' in details.lower() or 'channel' in action:
                emoji = "📢"
            elif 'назад' in details.lower():
                emoji = "◀️"
            elif 'start' in action or 'бота' in details.lower():
                emoji = "🤖"
                if 'запустил бота' not in details.lower():
                    details = 'Запустил бота'
            elif 'бонус' in details.lower():
                emoji = "🎁"
            else:
                emoji = "🔄"
            
            text += f"{emoji} {time_str} — {details}\n"
    
    text += f"\n───────── БАЛАНС ───────────\n"
    text += f"💰 Текущий: {balance} FPV"
    
    await callback.message.edit_text(text, reply_markup=get_history_keyboard())
    await callback.answer()

# ========== НАЗАД ==========
@dp.callback_query(lambda c: c.data == 'back')
async def go_back(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    add_history(user_id, 'back', 0, 'Вернулся в главное меню')
    await cmd_start(callback.message)
    await callback.answer()

# ========== СЕКРЕТНЫЕ КОМАНДЫ ==========
@dp.message()
async def secret_commands(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    secrets = {
        '🚁': 'Ты нашел секрет! +100 FPV',
        '💰': 'Монетный дождь! +100 FPV',
        '🔥': 'Огненный бонус! +100 FPV',
        '🎲': 'Удача на твоей стороне! +100 FPV'
    }
    
    if text in secrets:
        update_balance(user_id, 100)
        add_history(user_id, 'secret', 100, f'Секрет {text}')
        await message.reply(f"🎉 *СЕКРЕТ НАЙДЕН!*\n\n{secrets[text]}", parse_mode="Markdown")

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
