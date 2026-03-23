import sqlite3
import logging
import random
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from contextlib import contextmanager

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = "YOUR_BOT_TOKEN"  # Замените на ваш токен
CHANNEL_LINK = "https://t.me/fpv_bank_game_channel"
CHANNEL_USERNAME = "@fpv_bank_game_channel"
VERSION = "2.0.0"
WELCOME_BONUS = 90

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== РАНГИ (ТИТУЛЫ) ==========
RANKS = [
    {"name": "🪂 НОВИЧОК", "min_fpv": 0, "icon": "🪂"},
    {"name": "🛸 ПИЛОТ-СТАЖЕР", "min_fpv": 500, "icon": "🛸"},
    {"name": "🚁 ОПЫТНЫЙ ПИЛОТ", "min_fpv": 2000, "icon": "🚁"},
    {"name": "⚡ АС ВОЗДУШНОГО БОЯ", "min_fpv": 5000, "icon": "⚡"},
    {"name": "🔥 ЭЛИТНЫЙ ДРОНЩИК", "min_fpv": 10000, "icon": "🔥"},
    {"name": "👑 ЛЕГЕНДА FPV", "min_fpv": 25000, "icon": "👑"},
    {"name": "💎 КРИПТО-АС", "min_fpv": 50000, "icon": "💎"},
    {"name": "🚀 ВЛАСТЕЛИН НЕБА", "min_fpv": 100000, "icon": "🚀"},
]

# ========== ЕЖЕДНЕВНЫЕ ЗАДАНИЯ ==========
DAILY_QUESTS = [
    {"id": "click_25", "name": "🎯 МЕТКИЙ СТРЕЛОК", "description": "Сделать 25 кликов", "target": 25, "reward": 250},
    {"id": "click_50", "name": "💥 ШТУРМОВИК", "description": "Сделать 50 кликов", "target": 50, "reward": 500},
    {"id": "quest_3", "name": "🔍 ЛЮБОПЫТНЫЙ", "description": "Посмотреть 3 случайных факта", "target": 3, "reward": 150},
    {"id": "quest_5", "name": "📜 ИСТОРИК", "description": "Открыть историю действий", "target": 1, "reward": 100},
    {"id": "daily_3", "name": "📅 СТАБИЛЬНОСТЬ", "description": "Заходить 3 дня подряд", "target": 3, "reward": 500},
]

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self, db_path: str = "fpv_bank.db"):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей (расширенная)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    balance INTEGER DEFAULT 0,
                    total_clicks INTEGER DEFAULT 0,
                    total_earned INTEGER DEFAULT 0,
                    daily_streak INTEGER DEFAULT 0,
                    last_daily TIMESTAMP,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    rank_index INTEGER DEFAULT 0,
                    completed_quests TEXT DEFAULT '[]',
                    quest_progress TEXT DEFAULT '{}'
                )
            ''')
            
            # Таблица истории действий
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Новая таблица для достижений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS achievements (
                    user_id INTEGER,
                    achievement_id TEXT,
                    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, achievement_id)
                )
            ''')
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ==========
    def get_user(self, user_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_user(self, user_id: int, username: str = None, first_name: str = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, balance, total_clicks, total_earned)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, WELCOME_BONUS, 0, WELCOME_BONUS))
            
            # Логируем создание
            self.add_history(user_id, "🎮", "Запуск игры", conn)
    
    def update_balance(self, user_id: int, amount: int) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ? RETURNING balance",
                (amount, max(0, amount), user_id)
            )
            result = cursor.fetchone()
            return result[0] if result else 0
    
    def add_click(self, user_id: int, amount: int = 1):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET balance = balance + ?, total_clicks = total_clicks + 1 WHERE user_id = ?",
                (amount, user_id)
            )
            # Обновляем прогресс квестов
            self._update_quest_progress(user_id, "click", 1, conn)
    
    def add_history(self, user_id: int, action: str, details: str = "", conn=None):
        if conn:
            cursor = conn.cursor()
        else:
            with self._get_connection() as new_conn:
                cursor = new_conn.cursor()
                cursor.execute(
                    "INSERT INTO history (user_id, action, details) VALUES (?, ?, ?)",
                    (user_id, action, details)
                )
                return
        
        cursor.execute(
            "INSERT INTO history (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details)
        )
    
    def get_history(self, user_id: int, limit: int = 15) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT action, details, timestamp FROM history 
                WHERE user_id = ? 
                ORDER BY timestamp DESC LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self, user_id: int) -> Dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT balance, total_clicks, total_earned, daily_streak, join_date
                FROM users WHERE user_id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    # ========== ДЕЙЛИКИ ==========
    def claim_daily(self, user_id: int) -> Tuple[int, int]:
        """Возвращает (бонус, новый_стрик)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_daily, daily_streak FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            today = datetime.now().date()
            last_date = datetime.fromisoformat(row[0]).date() if row[0] else None
            
            if last_date == today:
                return 0, row[1]
            
            if last_date and last_date == today - timedelta(days=1):
                new_streak = row[1] + 1
            else:
                new_streak = 1
            
            # Расчет бонуса (база 100 + бонус за стрик)
            bonus = 100 + (new_streak * 10)
            bonus = min(bonus, 500)  # Максимум 500
            
            cursor.execute(
                "UPDATE users SET balance = balance + ?, daily_streak = ?, last_daily = ? WHERE user_id = ?",
                (bonus, new_streak, datetime.now().isoformat(), user_id)
            )
            
            self._update_quest_progress(user_id, "daily", 1, conn)
            
            return bonus, new_streak
    
    # ========== РАНГИ ==========
    def get_user_rank(self, user_id: int) -> Dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT total_earned FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            total_earned = row[0] if row else 0
            
            # Определяем ранг
            current_rank = RANKS[0]
            for rank in reversed(RANKS):
                if total_earned >= rank["min_fpv"]:
                    current_rank = rank
                    break
            
            # Обновляем индекс в БД
            rank_index = RANKS.index(current_rank)
            cursor.execute("UPDATE users SET rank_index = ? WHERE user_id = ?", (rank_index, user_id))
            
            next_rank = None
            if rank_index + 1 < len(RANKS):
                next_rank = RANKS[rank_index + 1]
            
            return {
                "current": current_rank,
                "next": next_rank,
                "progress": total_earned,
                "next_needed": next_rank["min_fpv"] - total_earned if next_rank else 0
            }
    
    # ========== КВЕСТЫ ==========
    def get_user_quests(self, user_id: int) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT completed_quests, quest_progress FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            import json
            completed = json.loads(row[0]) if row and row[0] else []
            progress = json.loads(row[1]) if row and row[1] else {}
            
            quests = []
            for quest in DAILY_QUESTS:
                if quest["id"] in completed:
                    quests.append({**quest, "completed": True, "progress": quest["target"]})
                else:
                    current_progress = progress.get(quest["id"], 0)
                    quests.append({**quest, "completed": False, "progress": current_progress})
            
            return quests
    
    def _update_quest_progress(self, user_id: int, action_type: str, increment: int, conn):
        """Обновляет прогресс квестов"""
        import json
        cursor = conn.cursor()
        cursor.execute("SELECT completed_quests, quest_progress FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        completed = json.loads(row[0]) if row and row[0] else []
        progress = json.loads(row[1]) if row and row[1] else {}
        
        updated = False
        
        for quest in DAILY_QUESTS:
            if quest["id"] in completed:
                continue
            
            # Маппинг действий
            if quest["id"].startswith("click") and action_type == "click":
                progress[quest["id"]] = progress.get(quest["id"], 0) + increment
                if progress[quest["id"]] >= quest["target"]:
                    completed.append(quest["id"])
                    # Награда за выполнение
                    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (quest["reward"], user_id))
                    updated = True
                else:
                    updated = True
            
            elif quest["id"] == "quest_3" and action_type == "fact":
                progress[quest["id"]] = progress.get(quest["id"], 0) + increment
                if progress[quest["id"]] >= quest["target"]:
                    completed.append(quest["id"])
                    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (quest["reward"], user_id))
                    updated = True
                else:
                    updated = True
            
            elif quest["id"] == "quest_5" and action_type == "history":
                progress[quest["id"]] = progress.get(quest["id"], 0) + increment
                if progress[quest["id"]] >= quest["target"]:
                    completed.append(quest["id"])
                    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (quest["reward"], user_id))
                    updated = True
                else:
                    updated = True
            
            elif quest["id"] == "daily_3" and action_type == "daily":
                progress[quest["id"]] = progress.get(quest["id"], 0) + increment
                if progress[quest["id"]] >= quest["target"]:
                    completed.append(quest["id"])
                    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (quest["reward"], user_id))
                    updated = True
                else:
                    updated = True
        
        if updated:
            cursor.execute(
                "UPDATE users SET completed_quests = ?, quest_progress = ? WHERE user_id = ?",
                (json.dumps(completed), json.dumps(progress), user_id)
            )
    
    def reset_quests(self):
        """Сброс ежедневных квестов (вызывать при старте)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET completed_quests = '[]', quest_progress = '{}'")
    
    # ========== СТАТИСТИКА ==========
    def get_global_stats(self) -> Dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(total_clicks) FROM users")
            total_clicks = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT SUM(total_earned) FROM users")
            total_fpv = cursor.fetchone()[0] or 0
            
            return {
                "total_users": total_users,
                "total_clicks": total_clicks,
                "total_fpv": total_fpv
            }

# ========== ФАКТЫ ==========
FACTS = [
    "🏆 FPV-дроны могут разгоняться до 200+ км/ч!",
    "🔋 Среднее время полета FPV-дрона — 3-7 минут.",
    "📡 FPV расшифровывается как First Person View — вид от первого лица.",
    "🎮 Многие пилоты используют очки виртуальной реальности для управления.",
    "⚡ Соревнования по FPV-гонкам проходят по всему миру.",
    "🛠️ Собрать FPV-дрон можно самостоятельно из запчастей.",
    "📸 FPV-дроны часто используют для съемки экстремальных видов спорта.",
    "🚁 Самый быстрый FPV-дрон разогнался до 300 км/ч!",
]

# ========== ОФОРМЛЕНИЕ ==========
def format_balance(balance: int) -> str:
    """Форматирование баланса с разделителями"""
    return f"{balance:,}".replace(",", " ")

def create_frame(title: str, content: str, icon: str = "🏦") -> str:
    """Создает красивую рамку для сообщений"""
    width = 42
    top = f"╔{'═' * (width - 2)}╗"
    bottom = f"╚{'═' * (width - 2)}╝"
    
    title_line = f"║ {icon} {title.center(width - 6)} {icon} ║"
    
    lines = [top, title_line]
    
    for line in content.split('\n'):
        # Обрезаем длинные строки для мобильных
        if len(line) > width - 4:
            # Разбиваем длинные строки
            words = line.split()
            current_line = ""
            for word in words:
                if len(current_line) + len(word) + 1 <= width - 4:
                    current_line += word + " "
                else:
                    lines.append(f"║ {current_line:<{width-4}} ║")
                    current_line = word + " "
            if current_line:
                lines.append(f"║ {current_line:<{width-4}} ║")
        else:
            lines.append(f"║ {line:<{width-4}} ║")
    
    lines.append(bottom)
    return '\n'.join(lines)

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 КАНАЛ", url=CHANNEL_LINK),
            InlineKeyboardButton("ℹ️ О ИГРЕ", callback_data="about"),
        ],
        [
            InlineKeyboardButton("❓ ФАКТЫ", callback_data="facts"),
            InlineKeyboardButton("📜 ИСТОРИЯ", callback_data="history"),
        ],
        [
            InlineKeyboardButton("🏆 РАНГИ", callback_data="ranks"),
            InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats"),
        ],
        [
            InlineKeyboardButton("✨ ЗАДАНИЯ", callback_data="quests"),
            InlineKeyboardButton("🎁 ДЕЙЛИК", callback_data="daily"),
        ],
        [
            InlineKeyboardButton("📈 ТОП", callback_data="top"),
            InlineKeyboardButton("💸 КЛИК", callback_data="click"),
        ],
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ НАЗАД", callback_data="main")]
    ])

# ========== ХЕНДЛЕРЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = context.bot_data['db']
    
    existing = db.get_user(user.id)
    if not existing:
        db.create_user(user.id, user.username, user.first_name)
        db.add_history(user.id, "🎮", "Запуск игры")
        
        # Приветственное сообщение для новых
        content = f"""ДОБРО ПОЖАЛОВАТЬ В FPV BANK, {user.first_name}!

🎁 БОНУС: +{WELCOME_BONUS} FPV

📌 ОСНОВНЫЕ ФИЧИ:
• 💸 КЛИКАЙ — зарабатывай FPV
• 🎁 ЕЖЕДНЕВНЫЙ БОНУС — заходи каждый день
• ✨ ЗАДАНИЯ — выполняй и получай награды
• 🏆 РАНГИ — прокачивай свой статус
• 📊 СТАТИСТИКА — отслеживай прогресс

🔐 СЕКРЕТНЫЕ КОМАНДЫ:
🚁 💰 🔥 🎲 — каждая дает +100 FPV

👥 ПОДПИШИСЬ НА КАНАЛ: {CHANNEL_USERNAME}

Версия {VERSION}"""
        
        msg = create_frame("FPV BANK", content, "🏦")
        await update.message.reply_text(msg, reply_markup=get_main_keyboard())
    else:
        # Приветствие для старых пользователей
        stats = db.get_stats(user.id)
        rank = db.get_user_rank(user.id)
        content = f"""С ВОЗВРАЩЕНИЕМ, {user.first_name}!

💰 БАЛАНС: {format_balance(stats['balance'])} FPV
🏆 РАНГ: {rank['current']['icon']} {rank['current']['name']}
📊 ВСЕГО ЗАРАБОТАНО: {format_balance(stats['total_earned'])} FPV
🎯 ВСЕГО КЛИКОВ: {stats['total_clicks']}

Версия {VERSION}"""
        
        msg = create_frame("FPV BANK", content, "🏦")
        await update.message.reply_text(msg, reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    db = context.bot_data['db']
    
    if query.data == "main":
        user = query.from_user
        stats = db.get_stats(user_id)
        rank = db.get_user_rank(user_id)
        content = f"""🏦 FPV BANK — ПРЕМИУМ КЛИКЕР

{user.first_name}, твой профиль:

💰 БАЛАНС: {format_balance(stats['balance'])} FPV
🏆 РАНГ: {rank['current']['icon']} {rank['current']['name']}
📊 ВСЕГО: {format_balance(stats['total_earned'])} FPV
🎯 КЛИКОВ: {stats['total_clicks']}

📅 СТРИК: {stats['daily_streak']} дней

Версия {VERSION}"""
        
        msg = create_frame("ГЛАВНОЕ МЕНЮ", content, "🏦")
        await query.edit_message_text(msg, reply_markup=get_main_keyboard())
    
    elif query.data == "about":
        content = """FPV BANK — это игра-кликер в мире дронов и высоких технологий.

⚡ ОСНОВНЫЕ МЕХАНИКИ:
• Кликай по кнопке 💸 и зарабатывай FPV
• Получай ежедневные бонусы за активность
• Выполняй задания и повышай свой ранг
• Открывай случайные факты о мире FPV

🎮 СЕКРЕТНЫЕ КОМАНДЫ:
Введи в чат: 🚁 💰 🔥 🎲
Каждая дает +100 FPV!

📢 НАШ КАНАЛ: {CHANNEL_USERNAME}
Там новости, обновления и эксклюзивные бонусы!

🔧 Версия {VERSION}"""
        
        msg = create_frame("О ИГРЕ", content, "ℹ️")
        await query.edit_message_text(msg, reply_markup=get_back_keyboard())
        db.add_history(user_id, "ℹ️", "Просмотр информации об игре")
    
    elif query.data == "facts":
        fact = random.choice(FACTS)
        content = f"""📖 СЛУЧАЙНЫЙ ФАКТ

{fact}

💡 Факты обновляются каждый раз при нажатии!"""
        
        msg = create_frame("FPV ФАКТЫ", content, "❓")
        await query.edit_message_text(msg, reply_markup=get_back_keyboard())
        db.add_history(user_id, "❓", f"Просмотр факта: {fact[:30]}...")
        db._update_quest_progress(user_id, "fact", 1, None)
    
    elif query.data == "history":
        history = db.get_history(user_id, 12)
        
        if not history:
            content = "📭 История действий пока пуста. Начни играть!"
        else:
            history_lines = []
            for h in history:
                timestamp = datetime.fromisoformat(h['timestamp']).strftime("%d.%m %H:%M")
                history_lines.append(f"{h['action']} {timestamp} — {h['details']}")
            content = '\n'.join(history_lines)
        
        msg = create_frame("ИСТОРИЯ ДЕЙСТВИЙ", content, "📜")
        await query.edit_message_text(msg, reply_markup=get_back_keyboard())
        db.add_history(user_id, "📜", "Просмотр истории действий")
        db._update_quest_progress(user_id, "history", 1, None)
    
    elif query.data == "click":
        db.add_click(user_id)
        stats = db.get_stats(user_id)
        
        # Анимация клика (просто обновляем сообщение)
        content = f"""💸 КЛИК ЗАСЧИТАН!

Ты получил +1 FPV

💰 ТЕКУЩИЙ БАЛАНС: {format_balance(stats['balance'])} FPV

Продолжай кликать! 🚁"""
        
        msg = create_frame("КЛИК", content, "💸")
        await query.edit_message_text(msg, reply_markup=get_back_keyboard())
        db.add_history(user_id, "💸", "Клик (+1 FPV)")
    
    elif query.data == "daily":
        bonus, streak = db.claim_daily(user_id)
        stats = db.get_stats(user_id)
        
        if bonus == 0:
            content = f"""🎁 ЕЖЕДНЕВНЫЙ БОНУС УЖЕ ПОЛУЧЕН!

Ты уже забирал бонус сегодня.

📅 ТЕКУЩИЙ СТРИК: {streak} дней
💰 БАЛАНС: {format_balance(stats['balance'])} FPV

Возвращайся завтра!"""
        else:
            content = f"""🎁 ЕЖЕДНЕВНЫЙ БОНУС!

✨ +{bonus} FPV

📅 СТРИК: {streak} дней (максимум +50% к бонусу!)

💰 НОВЫЙ БАЛАНС: {format_balance(stats['balance'])} FPV

Заходи каждый день — стрик растет!"""
        
        msg = create_frame("ЕЖЕДНЕВНЫЙ БОНУС", content, "🎁")
        await query.edit_message_text(msg, reply_markup=get_back_keyboard())
        db.add_history(user_id, "🎁", f"Ежедневный бонус: +{bonus} FPV (стрик {streak})")
    
    elif query.data == "ranks":
        rank_data = db.get_user_rank(user_id)
        stats = db.get_stats(user_id)
        
        # Создаем шкалу прогресса
        if rank_data["next"]:
            progress_percent = int((rank_data["progress"] - rank_data["current"]["min_fpv"]) / 
                                   (rank_data["next"]["min_fpv"] - rank_data["current"]["min_fpv"]) * 100)
            progress_bar = "█" * (progress_percent // 10) + "░" * (10 - (progress_percent // 10))
            
            content = f"""🏆 ТВОЙ РАНГ: {rank_data['current']['icon']} {rank_data['current']['name']}

📊 ДО СЛЕДУЮЩЕГО РАНГА:
{rank_data['next']['icon']} {rank_data['next']['name']}
Нужно: {format_balance(rank_data['next_needed'])} FPV

📈 ПРОГРЕСС:
[{progress_bar}] {progress_percent}%

💰 ВСЕГО ЗАРАБОТАНО: {format_balance(rank_data['progress'])} FPV

ДОСТУПНЫЕ РАНГИ:"""
        else:
            content = f"""🏆 ТВОЙ РАНГ: {rank_data['current']['icon']} {rank_data['current']['name']}

👑 ТЫ ДОСТИГ МАКСИМАЛЬНОГО РАНГА!
Ты — настоящая легенда FPV!

💰 ВСЕГО ЗАРАБОТАНО: {format_balance(rank_data['progress'])} FPV

ДОСТУПНЫЕ РАНГИ:"""
        
        # Добавляем список всех рангов
        for rank in RANKS:
            if rank == rank_data["current"]:
                content += f"\n✅ {rank['icon']} {rank['name']} — текущий"
            elif rank_data["next"] and rank == rank_data["next"]:
                content += f"\n🎯 {rank['icon']} {rank['name']} — следующий"
            else:
                content += f"\n   {rank['icon']} {rank['name']}"
        
        msg = create_frame("СИСТЕМА РАНГОВ", content, "🏆")
        await query.edit_message_text(msg, reply_markup=get_back_keyboard())
        db.add_history(user_id, "🏆", "Просмотр системы рангов")
    
    elif query.data == "quests":
        quests = db.get_user_quests(user_id)
        
        content = "✨ АКТИВНЫЕ ЗАДАНИЯ\n\n"
        completed_count = 0
        
        for quest in quests:
            if quest["completed"]:
                status = "✅ ВЫПОЛНЕНО"
                completed_count += 1
                content += f"{quest['name']}\n   {status} (+{quest['reward']} FPV)\n\n"
            else:
                progress_bar = "█" * (quest["progress"] // max(1, quest["target"] // 10)) + "░" * (10 - (quest["progress"] // max(1, quest["target"] // 10)))
                content += f"{quest['name']}\n   📋 {quest['description']}\n   🎯 {quest['progress']}/{quest['target']}\n   [{progress_bar}]\n   🎁 Награда: +{quest['reward']} FPV\n\n"
        
        content += f"📊 ВЫПОЛНЕНО: {completed_count}/{len(quests)}"
        
        msg = create_frame("ЕЖЕДНЕВНЫЕ ЗАДАНИЯ", content, "✨")
        await query.edit_message_text(msg, reply_markup=get_back_keyboard())
        db.add_history(user_id, "✨", "Просмотр заданий")
    
    elif query.data == "stats":
        user_stats = db.get_stats(user_id)
        global_stats = db.get_global_stats()
        rank = db.get_user_rank(user_id)
        
        # Расчет места в топе (простой вариант)
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM users WHERE total_earned > ?
            """, (user_stats['total_earned'],))
            higher_count = cursor.fetchone()[0]
            position = higher_count + 1
        
        content = f"""📊 ТВОЯ СТАТИСТИКА

💰 БАЛАНС: {format_balance(user_stats['balance'])} FPV
🏆 РАНГ: {rank['current']['icon']} {rank['current']['name']}
🎯 ВСЕГО КЛИКОВ: {user_stats['total_clicks']}
💎 ВСЕГО ЗАРАБОТАНО: {format_balance(user_stats['total_earned'])} FPV
📅 ДНЕЙ В ИГРЕ: {(datetime.now() - datetime.fromisoformat(user_stats['join_date'])).days}
🔥 ТЕКУЩИЙ СТРИК: {user_stats['daily_streak']} дней

🌍 ГЛОБАЛЬНАЯ СТАТИСТИКА:
👥 ВСЕГО ИГРОКОВ: {global_stats['total_users']}
🖱️ ВСЕГО КЛИКОВ: {format_balance(global_stats['total_clicks'])}
💸 ВСЕГО FPV: {format_balance(global_stats['total_fpv'])}

🏅 ТВОЕ МЕСТО: {position}/{global_stats['total_users']}"""
        
        msg = create_frame("СТАТИСТИКА", content, "📊")
        await query.edit_message_text(msg, reply_markup=get_back_keyboard())
        db.add_history(user_id, "📊", "Просмотр статистики")
    
    elif query.data == "top":
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, first_name, total_earned 
                FROM users 
                ORDER BY total_earned DESC 
                LIMIT 10
            """)
            top_users = cursor.fetchall()
        
        content = "🏆 ТОП-10 ИГРОКОВ\n\n"
        for i, user in enumerate(top_users, 1):
            name = user[2] or f"User_{user[0]}"
            if user[1]:
                name = f"@{user[1]}"
            content += f"{i}. {name} — {format_balance(user[3])} FPV\n"
        
        if not top_users:
            content += "📭 Пока нет игроков"
        
        msg = create_frame("ТОП ИГРОКОВ", content, "🏆")
        await query.edit_message_text(msg, reply_markup=get_back_keyboard())
        db.add_history(user_id, "🏆", "Просмотр топа игроков")

# ========== СЕКРЕТНЫЕ КОМАНДЫ ==========
SECRET_COMMANDS = ["🚁", "💰", "🔥", "🎲"]

async def secret_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    db = context.bot_data['db']
    
    if text in SECRET_COMMANDS:
        db.update_balance(user_id, 100)
        stats = db.get_stats(user_id)
        db.add_history(user_id, "🔐", f"Секретная команда {text}: +100 FPV")
        
        content = f"""🔓 СЕКРЕТНАЯ КОМАНДА АКТИВИРОВАНА!

✨ +100 FPV

💰 НОВЫЙ БАЛАНС: {format_balance(stats['balance'])} FPV

Попробуй найти другие секретные команды!"""
        
        msg = create_frame("СЕКРЕТ", content, "🔐")
        await update.message.reply_text(msg, reply_markup=get_main_keyboard())

# ========== ОСНОВНОЙ ЗАПУСК ==========
async def post_init(application: Application):
    """Сброс квестов при запуске"""
    db = application.bot_data['db']
    db.reset_quests()
    logger.info("Ежедневные квесты сброшены")

def main():
    # Инициализация БД
    db = Database("fpv_bank.db")
    
    # Создание приложения
    application = Application.builder().token(TOKEN).build()
    application.bot_data['db'] = db
    
    # Хендлеры
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Секретные команды
    for cmd in SECRET_COMMANDS:
        application.add_handler(MessageHandler(filters.Text(cmd), secret_command_handler))
    
    # Запуск
    application.post_init = post_init
    
    logger.info("Бот FPV BANK запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()
