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

logging.basicConfig(level=logging.INFO)

# ------------------------------
# Загрузка конфигурации
# ------------------------------
def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()
API_TOKEN = config["bot_token"]
ADMIN_CHAT_ID = config.get("admin_chat_id")

# ------------------------------
# Загрузка предметов (навигация по подкаталогам)
# ------------------------------
def load_subjects():
    try:
        with open("subjects.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка чтения subjects.json: {e}")
        return {}

def get_node(path):
    """
    По переданному пути (список ключей) возвращает узел из subjects.json.
    Если узел – строка, пытаемся прочитать файл из папки subjects.
    """
    node = load_subjects()
    for key in path:
        if isinstance(node, dict) and key in node:
            node = node[key]
            if isinstance(node, str):
                file_path = f"subjects/{node}.json"
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            node = json.load(f)
                    except Exception as e:
                        logging.error(f"Ошибка чтения {file_path}: {e}")
                        return None
                else:
                    return node
        else:
            return None
    return node

# ------------------------------
# Загрузка тестов
# ------------------------------
def load_tests():
    try:
        with open("tests.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка чтения tests.json: {e}")
        return {}

# ------------------------------
# Отслеживание прохождения предметов
# ------------------------------
PROGRESS_FILE = "progress.json"

def load_progress():
    if os.path.exists("progress.json"):
        try:
            with open("progress.json", "r", encoding="utf-8") as f:
                data = f.read().strip()
                return json.loads(data) if data else {}
        except json.JSONDecodeError:
            logging.error("Ошибка загрузки progress.json. Файл повреждён.")
            return {}
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

# ------------------------------
# Формирование клавиатур
# ------------------------------
def build_keyboard(options, include_back=False):
    """
    Создает клавиатуру для выбора разделов.
    Если include_back=True, добавляет кнопку «Назад» перед кнопкой «Главное меню».
    """
    buttons = [[KeyboardButton(text=opt)] for opt in options]
    if include_back:
        buttons.append([KeyboardButton(text="Назад")])
    buttons.append([KeyboardButton(text="Главное меню")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_main_menu_keyboard():
    buttons = [
        [KeyboardButton(text="Оставить отзыв"), KeyboardButton(text="Связаться с админом")],
        [KeyboardButton(text="Тест")],
        [KeyboardButton(text="Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ------------------------------
# Глобальные состояния
# ------------------------------
user_nav_state = {}         # Навигация по предметам
review_pending = {}         # Режим ожидания отзыва
contact_pending = {}        # Режим связи с администрацией (пользователь)
# Для обратной связи от админа
admin_reply_pending = {}    # {admin_id: target_user_id}
# Состояние тестирования
user_test_states = {}

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ------------------------------
# Функция отправки вопроса теста
# ------------------------------
async def send_test_question(uid, chat_id):
    state = user_test_states.get(uid, {})
    questions = state.get("questions", [])
    current_index = state.get("current_index", 0)
    if current_index < len(questions):
        q = questions[current_index]
        question_text = q.get("question", "Вопрос не найден.")
        options = q.get("options")
        if options and isinstance(options, list):
            options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
            full_text = f"{question_text}\n\nВарианты ответов:\n{options_text}\n\nВведите ваш ответ:"
        else:
            full_text = f"{question_text}\n\nВведите ваш ответ:"
        await bot.send_message(chat_id=chat_id, text=full_text)
    else:
        score = state.get("score", 0)
        total = len(questions)
        await bot.send_message(chat_id=chat_id, text=f"Тест завершён! Вы набрали {score} из {total} баллов.")
        user_test_states[uid] = {}

# ------------------------------
# Обработчик команды /start
# ------------------------------
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    uid = str(message.from_user.id)
    user_nav_state[uid] = []          # Сбрасываем навигацию
    review_pending[uid] = False
    contact_pending[uid] = False
    user_test_states[uid] = {}
    top_options = list(load_subjects().keys())
    kb = build_keyboard(top_options)
    await message.answer("Привет! Выберите урок:", reply_markup=kb)

# ------------------------------
# Основной обработчик текстовых сообщений
# ------------------------------
@dp.message()
async def text_handler(message: types.Message):
    if not message.text:
        return

    uid = str(message.from_user.id)
    text = message.text.strip()
    lower_text = text.lower()

    # Унифицированная обработка кнопки "назад" для возврата на верхний уровень
    if lower_text == "назад":
        user_nav_state[uid] = []  # Сбрасываем навигацию
        top_options = list(load_subjects().keys())
        await message.answer("Вы находитесь на самом начале. Выберите урок:", reply_markup=build_keyboard(top_options))
        return

    # Если пользователь в режиме ожидания отзыва
    if review_pending.get(uid, False):
        sender_info = f"Отзыв от {message.from_user.full_name} (ID: {uid})"
        review_message = f"{sender_info}:\n\n{text}"
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=review_message)
            await message.answer("Ваш отзыв отправлен. Спасибо!", reply_markup=get_main_menu_keyboard())
        except Exception as e:
            logging.error(f"Ошибка при отправке отзыва: {e}")
            await message.answer("Произошла ошибка при отправке отзыва.", reply_markup=get_main_menu_keyboard())
        review_pending[uid] = False
        return

    # Если пользователь в режиме связи с администрацией (от пользователя)
    if contact_pending.get(uid, False):
        sender_info = f"Сообщение от {message.from_user.full_name} (ID: {uid})"
        contact_message = f"{sender_info}:\n\n{text}"
        try:
            # Формируем inline клавиатуру с кнопкой "Ответить", callback data содержит id пользователя
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Ответить", callback_data=f"reply_to_user:{uid}")]
            ])
            forwarded = await bot.send_message(chat_id=ADMIN_CHAT_ID, text=contact_message, reply_markup=inline_kb)
            await message.answer("Ваше сообщение отправлено администратору. Ждём ответа.", reply_markup=get_main_menu_keyboard())
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения администратору: {e}")
            await message.answer("Произошла ошибка при отправке вашего сообщения.", reply_markup=get_main_menu_keyboard())
        return

    # Если пользователь в режиме тестирования (ожидается ответ на вопрос)
    if user_test_states.get(uid, {}).get("questions") is not None:
        state = user_test_states[uid]
        questions = state.get("questions", [])
        current_index = state.get("current_index", 0)
        if current_index < len(questions):
            q = questions[current_index]
            expected_answer = q.get("answer", "").strip().lower()
            if lower_text == expected_answer:
                state["score"] = state.get("score", 0) + 1
                await message.answer("Верно!")
            else:
                await message.answer(f"Неверно. Правильный ответ: {expected_answer}")
            state["current_index"] = current_index + 1
            await send_test_question(uid, message.chat.id)
        else:
            score = state.get("score", 0)
            total = len(questions)
            await message.answer(f"Тест завершён! Вы набрали {score} из {total} баллов.", reply_markup=get_main_menu_keyboard())
            user_test_states[uid] = {}
        return

    # Обработка команды "главное меню"
    if lower_text == "главное меню":
        await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
        return

    # Обработка кнопки "оставить отзыв"
    if lower_text == "оставить отзыв":
        review_pending[uid] = True
        await message.answer("Пожалуйста, напишите ваш отзыв и отправьте его. Для отмены введите 'Назад'.", reply_markup=get_main_menu_keyboard())
        return

    # Обработка кнопки "связаться с админом"
    if lower_text == "связаться с админом":
        contact_pending[uid] = True
        await message.answer("Пожалуйста, напишите ваше сообщение для администрации. Для отмены введите 'Назад'.", reply_markup=get_main_menu_keyboard())
        return

    # Обработка кнопки "тест" – запуск теста для выбранного урока
    if lower_text == "тест":
        if uid in user_nav_state and user_nav_state[uid]:
            test_key = "/".join(user_nav_state[uid]) + "/Тест"
            tests = load_tests()
            if test_key in tests and isinstance(tests[test_key], list) and tests[test_key]:
                user_test_states[uid] = {
                    "questions": tests[test_key],
                    "current_index": 0,
                    "score": 0
                }
                await message.answer("Тест начат!")
                await send_test_question(uid, message.chat.id)
                return
            else:
                await message.answer("Тест по выбранному уроку не найден.", reply_markup=get_main_menu_keyboard())
                return
        else:
            await message.answer("Пожалуйста, выберите урок перед началом теста.", reply_markup=get_main_menu_keyboard())
            return

    # Обработка навигации по предметам
    if uid not in user_nav_state:
        user_nav_state[uid] = []
    current_path = user_nav_state[uid]
    node = get_node(current_path) if current_path else load_subjects()
    if isinstance(node, dict) and text in node:
        current_path.append(text)
        user_nav_state[uid] = current_path
        new_node = get_node(current_path)
        if isinstance(new_node, dict) and new_node:
            options = list(new_node.keys())
            await message.answer(
                f"Выберите подраздел для {'/'.join(current_path)}:",
                reply_markup=build_keyboard(options, include_back=True)
            )
        else:
            full_subject = "/".join(current_path)
            content = new_node if new_node is not None else "Описание отсутствует."
            mark_subject_completed(uid, full_subject)
            await message.answer(f"Вы выбрали: {full_subject}\n\n{content}", reply_markup=ReplyKeyboardRemove())
            await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
        return

    await message.answer("Пожалуйста, выберите один из предложенных вариантов.", reply_markup=get_main_menu_keyboard())

# ------------------------------
# Обработчик callback-запросов от inline кнопок (для ответа админа)
# ------------------------------
@dp.callback_query(lambda c: c.data.startswith("reply_to_user:"))
async def inline_reply_handler(callback: types.CallbackQuery):
    # Из callback data получаем id пользователя, которому нужно ответить
    target_uid = callback.data.split("reply_to_user:")[1]
    admin_id = str(callback.from_user.id)
    # Сохраняем состояние: админ отвечает на сообщение пользователя с target_uid
    admin_reply_pending[admin_id] = target_uid
    await callback.answer("Пишите ваш ответ", show_alert=True)
    # Отправляем сообщение администратору для уточнения
    await bot.send_message(chat_id=admin_id, text="Пожалуйста, напишите ваш ответ для пользователя.")

# ------------------------------
# Обработчик сообщений от администратора для обратной связи (при ожидании ответа)
# ------------------------------
@dp.message(lambda message: message.chat.id == ADMIN_CHAT_ID)
async def admin_message_handler(message: types.Message):
    admin_id = str(message.from_user.id)
    if admin_reply_pending.get(admin_id):
        target_uid = admin_reply_pending.pop(admin_id)
        reply_text = f"Ответ от администрации:\n\n{message.text}"
        try:
            await bot.send_message(chat_id=target_uid, text=reply_text)
            await message.reply("Ответ отправлен пользователю.")
        except Exception as e:
            logging.error(f"Ошибка при отправке ответа пользователю: {e}")
    # Если админ пишет не в режиме ответа, можно добавить и старую логику через reply
    elif message.reply_to_message and message.reply_to_message.message_id in contact_mapping:
        target_uid = contact_mapping[message.reply_to_message.message_id]
        reply_text = f"Ответ от администрации:\n\n{message.text}"
        try:
            await bot.send_message(chat_id=target_uid, text=reply_text)
            await message.reply("Ответ отправлен пользователю.")
        except Exception as e:
            logging.error(f"Ошибка при отправке ответа пользователю: {e}")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
