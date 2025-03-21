import asyncio
import json
import os
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# -------------------------
# Настройка логирования
# -------------------------
logging.basicConfig(level=logging.INFO)

# -------------------------
# Загрузка конфигурации из config.json
# -------------------------
def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()
API_TOKEN = config["bot_token"]
ADMIN_CHAT_ID = config.get("admin_chat_id")

# -------------------------
# Функция уведомления в админ-чат
# -------------------------
async def notify_admin(message_text: str):
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=message_text)
        except Exception as e:
            logging.error(f"Ошибка при отправке уведомления в админ-чат: {e}")

# -------------------------
# Регистрация пользователей
# -------------------------
USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

def register_user(user_id, username):
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"username": username}
        save_users(users)

def is_registered(user_id):
    users = load_users()
    return str(user_id) in users

# -------------------------
# Отслеживание прогресса
# -------------------------
PROGRESS_FILE = "progress.json"

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_progress(progress):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=4)

def mark_subject_completed(user_id, subject):
    progress = load_progress()
    uid = str(user_id)
    if uid not in progress:
        progress[uid] = []
    if subject not in progress[uid]:
        progress[uid].append(subject)
        save_progress(progress)

def is_subject_completed(user_id, subject):
    progress = load_progress()
    return str(user_id) in progress and subject in progress[str(user_id)]

# -------------------------
# Работа с предметами и тестами
# -------------------------
SUBJECTS_FILE = "subjects.json"
TESTS_FILE = "tests.json"

def load_subjects():
    try:
        with open(SUBJECTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка чтения {SUBJECTS_FILE}: {e}")
        return {}

def load_tests():
    if os.path.exists(TESTS_FILE):
        with open(TESTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_subject(subject):
    subject = subject.strip().lower()
    path = f"subjects/{subject}.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Ошибка чтения {path}: {e}")
            return None
    return None

def build_keyboard(options):
    kb = ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    for opt in options:
        kb.keyboard.append([KeyboardButton(text=opt)])
    kb.keyboard.append([KeyboardButton(text="Назад")])
    return kb

def get_node(path):
    node = load_subjects()
    for key in path:
        if isinstance(node, dict) and key in node:
            node = node[key]
            if isinstance(node, str):
                file_path = f"subjects/{node}.json"
                if os.path.exists(file_path):
                    try:
                        node = json.load(open(file_path, "r", encoding="utf-8"))
                    except Exception as e:
                        logging.error(f"Ошибка чтения {file_path}: {e}")
                        return None
                else:
                    return node
        else:
            return None
    return node

# -------------------------
# Функция формирования основного меню
# -------------------------
def get_main_menu_keyboard():
    kb = ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    kb.keyboard.append([KeyboardButton(text="Главное меню")])
    kb.keyboard.append([KeyboardButton(text="Оставить отзыв"), KeyboardButton(text="Связаться с админом")])
    return kb

# -------------------------
# Глобальное состояние навигации
# -------------------------
user_nav_state = {}

# -------------------------
# Глобальное состояние тестирования
# -------------------------
user_test_states = {}

# -------------------------
# Инициализация бота и обработчики
# -------------------------
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    uid = str(message.from_user.id)
    username = message.from_user.username or "Неизвестный"
    register_user(uid, username)
    user_nav_state[uid] = []
    top_options = list(load_subjects().keys())
    kb = build_keyboard(top_options)
    await message.answer("Привет! Выберите категорию:", reply_markup=kb)
    # Дополнительное меню
    await message.answer("Меню:", reply_markup=get_main_menu_keyboard())
    await notify_admin(f"Пользователь {username} (ID: {uid}) запустил бота.")

@dp.message()
async def text_handler(message: types.Message):
    uid = str(message.from_user.id)
    if not is_registered(uid):
        await message.answer("Сначала введите /start для регистрации.")
        return

    text = message.text.strip()
    if text.lower() == "главное меню":
        # Сброс навигации и вывод верхнего меню
        user_nav_state[uid] = []
        top_options = list(load_subjects().keys())
        await message.answer("Главное меню. Выберите категорию:", reply_markup=build_keyboard(top_options))
        return

    if text.lower() in {"оставить отзыв", "связаться с админом"}:
        # Обработка кнопок основного меню (если пользователь нажал эти кнопки как текст)
        await message.answer("Пожалуйста, воспользуйтесь кнопками в меню для этого действия.",
                             reply_markup=get_main_menu_keyboard())
        return

    if uid not in user_nav_state:
        user_nav_state[uid] = []
    current_path = user_nav_state[uid]

    if text.lower() == "назад":
        if current_path:
            current_path.pop()
        user_nav_state[uid] = current_path
        node = get_node(current_path) if current_path else load_subjects()
        if isinstance(node, dict):
            options = list(node.keys())
            await message.answer("Выберите подраздел:" if current_path else "Выберите категорию:",
                                 reply_markup=build_keyboard(options))
        else:
            await message.answer("Нет доступных подразделов.", reply_markup=ReplyKeyboardRemove())
        return

    node = get_node(current_path) if current_path else load_subjects()
    if not (isinstance(node, dict) and text in node):
        await message.answer("Пожалуйста, выберите один из предложенных вариантов.",
                             reply_markup=get_main_menu_keyboard())
        return

    current_path.append(text)
    user_nav_state[uid] = current_path
    new_node = get_node(current_path)
    if isinstance(new_node, dict) and new_node:
        options = list(new_node.keys())
        await message.answer(f"Выберите подраздел для {'/'.join(current_path)}:",
                             reply_markup=build_keyboard(options))
    else:
        full_subject = "/".join(current_path)
        content = new_node if new_node is not None else "Описание отсутствует."
        mark_subject_completed(uid, full_subject)
        await message.answer(f"Вы выбрали: {full_subject}\n\n{content}",
                             reply_markup=ReplyKeyboardRemove())
        await notify_admin(f"Пользователь {message.from_user.username} (ID: {uid}) выбрал тему: {full_subject}")
        # После выбора темы можно вернуть главное меню
        await message.answer("Меню:", reply_markup=get_main_menu_keyboard())

@dp.callback_query(lambda c: c.data.startswith("feedback"))
async def feedback_handler(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    username = callback.from_user.username or "Неизвестный"
    await notify_admin(f"Пользователь {username} (ID: {uid}) хочет оставить отзыв. Свяжитесь с ним, пожалуйста.")
    await callback.message.answer("Спасибо! Ваш отзыв будет передан администратору. Пожалуйста, напишите свой отзыв в ответном сообщении.")

@dp.callback_query(lambda c: c.data.startswith("contact_admin"))
async def contact_admin_handler(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    username = callback.from_user.username or "Неизвестный"
    await notify_admin(f"Пользователь {username} (ID: {uid}) хочет связаться с администратором.")
    await callback.message.answer("Сообщение отправлено администратору. Ожидайте обратной связи.")


if __name__ == "__main__":
    async def on_startup(*args, **kwargs):
        await notify_admin("Бот запущен и работает без ошибок.")
    dp.startup.register(on_startup)
    asyncio.run(dp.start_polling(bot))
