import asyncio
import json
import os
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
                           InlineKeyboardMarkup, InlineKeyboardButton)

# -------------------------
# Настройка логирования
# -------------------------
logging.basicConfig(level=logging.INFO)

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
# Отслеживание прогресса (если требуется)
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
    """
    Для листового узла, когда мы хотим просто вывести текст,
    текст уже хранится непосредственно в файле, поэтому возвращаем его.
    """
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
    """
    Проходит по иерархии по заданному пути (список ключей).
    Если значение узла – строка, пытается загрузить файл subjects/{value}.json.
    Если файл не найден, считается, что узел является листовым, и возвращается строка.
    """
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
                    # Если файл не найден, возвращаем строку как листовой узел.
                    return node
        else:
            return None
    return node

# -------------------------
# Глобальное состояние навигации
# -------------------------
user_nav_state = {}

# -------------------------
# Глобальное состояние тестирования (если требуется)
# -------------------------
user_test_states = {}

# -------------------------
# Инициализация бота и обработчики
# -------------------------
API_TOKEN = "7270273640:AAHP_9Z2ut-hMfAT3D2qWO8CIeR9Gq6KvzI"  # Замените на ваш токен
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

@dp.message()
async def text_handler(message: types.Message):
    uid = str(message.from_user.id)
    if not is_registered(uid):
        await message.answer("Сначала введите /start для регистрации.")
        return

    text = message.text.strip()
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
            kb = build_keyboard(options)
            prompt = "Выберите подраздел:" if current_path else "Выберите категорию:"
            await message.answer(prompt, reply_markup=kb)
        else:
            await message.answer("Нет доступных подразделов.", reply_markup=ReplyKeyboardRemove())
        return

    node = get_node(current_path) if current_path else load_subjects()
    if not (isinstance(node, dict) and text in node):
        await message.answer("Пожалуйста, выберите один из предложенных вариантов.")
        return

    current_path.append(text)
    user_nav_state[uid] = current_path
    new_node = get_node(current_path)
    if isinstance(new_node, dict) and new_node:
        options = list(new_node.keys())
        kb = build_keyboard(options)
        prompt = f"Выберите подраздел для {'/'.join(current_path)}:"
        await message.answer(prompt, reply_markup=kb)
    else:
        full_subject = "/".join(current_path)
        # Если new_node является None, заменяем на сообщение о том, что описание отсутствует
        content = new_node if new_node is not None else "Описание отсутствует."
        await message.answer(f"Вы выбрали: {full_subject}\n\n{content}", reply_markup=ReplyKeyboardRemove())

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
