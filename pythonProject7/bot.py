import asyncio
import json
import os
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка загрузки config.json: {e}")
        return {}

config = load_config()
API_TOKEN = config.get("bot_token")
ADMIN_CHAT_ID = config.get("admin_chat_id")

# Глобальные состояния
user_nav_state = {}       # {user_id: [путь]}
review_pending = {}       # {user_id: bool}
contact_pending = {}      # {user_id: bool}
admin_reply_pending = {}  # {admin_id: target_user_id}
user_test_states = {}     # {user_id: {"questions":..., "current_index":..., "score":...}}

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def load_subjects():
    try:
        with open("subjects.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка загрузки subjects.json: {e}")
        return {}

def load_tests():
    try:
        with open("tests.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка загрузки tests.json: {e}")
        return {}

def get_node(path):
    """
    Проходит по структуре, загружая данные из subjects.json.
    Для каждого ключа:
      - Если значение является словарём – переходит к нему.
      - Если значение – строка и не достигнут конец пути, пытается загрузить файл с этим именем
        (сначала без расширения, затем с добавлением .json) из директории subjects.
      - Если значение – строка на последнем уровне или файл не найден, возвращает конечное содержание в виде {"__content__": ...}.
    """
    subjects = load_subjects()
    node = subjects
    for i, key in enumerate(path):
        if isinstance(node, dict) and key in node:
            node = node[key]
            # Если значение строковое и мы ещё не дошли до конца пути, загрузим файл.
            if isinstance(node, str) and i < len(path) - 1:
                base_dir = "subjects"
                file_path = os.path.join(base_dir, node)
                if not os.path.exists(file_path):
                    file_path_with_ext = file_path + ".json"
                    if os.path.exists(file_path_with_ext):
                        file_path = file_path_with_ext
                    else:
                        logging.warning(f"Файл не найден: {file_path} или {file_path_with_ext}")
                        return {"__content__": node}
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        node = json.load(f)
                except json.JSONDecodeError as e:
                    logging.error(f"Ошибка декодирования JSON в {file_path}: {e}. Читаем как текст.")
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            text_data = f.read().strip()
                        node = {"__content__": text_data}
                    except Exception as e2:
                        logging.error(f"Ошибка чтения файла как текста в {file_path}: {e2}")
                        return {"__content__": node}
        else:
            return None

    # Если итоговое значение – строка, попытаемся загрузить файл, если он существует
    if isinstance(node, str):
        base_dir = "subjects"
        file_path = os.path.join(base_dir, node)
        if os.path.exists(file_path) or os.path.exists(file_path + ".json"):
            if not os.path.exists(file_path):
                file_path = file_path + ".json"
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    node = json.load(f)
            except json.JSONDecodeError:
                with open(file_path, "r", encoding="utf-8") as f:
                    text_data = f.read().strip()
                node = {"__content__": text_data}
        else:
            node = {"__content__": node}
    if isinstance(node, list):
        node = {"__content__": "\n".join(str(x) for x in node)}
    return node

def build_keyboard(options, include_back=False):
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

def get_reply_inline_keyboard(uid: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ответить", callback_data=f"reply_to_user:{uid}")]
    ])

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    uid = str(message.from_user.id)
    user_nav_state[uid] = []
    review_pending[uid] = False
    contact_pending[uid] = False
    user_test_states[uid] = {}
    logging.info(f"/start от {uid}")
    subjects = list(load_subjects().keys())
    await message.answer("Привет! Выберите урок:", reply_markup=build_keyboard(subjects))

@dp.message()
async def text_handler(message: types.Message):
    uid = str(message.from_user.id)
    if not message.text:
        logging.warning(f"Пустое сообщение от {uid}")
        return
    text = message.text.strip()
    lower_text = text.lower()
    logging.info(f"Сообщение от {uid}: {text}")

    # Если введённая команда не является системной, и пользователь уже на конечном уровне, повторяем содержание
    system_commands = {"назад", "главное меню", "оставить отзыв", "связаться с админом", "тест"}
    current_path = user_nav_state.get(uid, [])
    node = get_node(current_path) if current_path else None
    if lower_text not in system_commands and node is not None and isinstance(node, dict) and "__content__" in node:
        await message.answer(f"Вы уже выбрали: {'/'.join(current_path)}\n\n{node['__content__']}", reply_markup=get_main_menu_keyboard())
        return

    # Обработка кнопки "Назад": сброс навигации до верхнего уровня
    if lower_text == "назад":
        user_nav_state[uid] = []
        subjects = list(load_subjects().keys())
        await message.answer("Вы находитесь на самом начале. Выберите урок:", reply_markup=build_keyboard(subjects))
        return

    # Режим отзыва
    if review_pending.get(uid, False):
        review_pending[uid] = False
        review_msg = f"Отзыв от {message.from_user.full_name} (ID {uid}):\n{text}"
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=review_msg)
            await message.answer("Спасибо! Ваш отзыв отправлен.", reply_markup=get_main_menu_keyboard())
            logging.info(f"Отзыв от {uid} отправлен")
        except Exception as e:
            logging.error(f"Ошибка отправки отзыва от {uid}: {e}")
            await message.answer("Произошла ошибка при отправке отзыва.", reply_markup=get_main_menu_keyboard())
        return

    # Режим связи с админом (пользовательский)
    if contact_pending.get(uid, False):
        contact_pending[uid] = False
        contact_msg = f"Сообщение от {message.from_user.full_name} (ID {uid}):\n{text}"
        try:
            inline_kb = get_reply_inline_keyboard(uid)
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=contact_msg, reply_markup=inline_kb)
            await message.answer("Ваше сообщение отправлено администратору.", reply_markup=get_main_menu_keyboard())
            logging.info(f"Сообщение для связи от {uid} отправлено")
        except Exception as e:
            logging.error(f"Ошибка отправки сообщения от {uid} админу: {e}")
            await message.answer("Произошла ошибка при отправке вашего сообщения.", reply_markup=get_main_menu_keyboard())
        return

    # Режим тестирования
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

    # Обработка команды "Главное меню"
    if lower_text == "главное меню":
        await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
        return

    # Обработка кнопок "Оставить отзыв" и "Связаться с админом"
    if lower_text == "оставить отзыв":
        review_pending[uid] = True
        await message.answer("Пожалуйста, напишите ваш отзыв и отправьте его. Для отмены введите 'Назад'.", reply_markup=get_main_menu_keyboard())
        return
    if lower_text == "связаться с админом":
        contact_pending[uid] = True
        await message.answer("Пожалуйста, напишите ваше сообщение для администрации. Для отмены введите 'Назад'.", reply_markup=get_main_menu_keyboard())
        return
    if lower_text == "тест":
        if uid in user_nav_state and user_nav_state[uid]:
            test_key = "/".join(user_nav_state[uid]) + "/Тест"
            tests = load_tests().get(test_key, [])
            if tests and isinstance(tests, list):
                user_test_states[uid] = {"questions": tests, "current_index": 0, "score": 0}
                await message.answer("Тест начат!")
                await send_test_question(uid, message.chat.id)
            else:
                await message.answer("Тест по выбранному уроку не найден.", reply_markup=get_main_menu_keyboard())
            return
        else:
            await message.answer("Пожалуйста, выберите урок перед началом теста.", reply_markup=get_main_menu_keyboard())
            return

    # Обработка навигации по предметам/подкатегориям
    current_path = user_nav_state.get(uid, [])
    node = get_node(current_path) if current_path else load_subjects()
    if isinstance(node, dict) and text in node:
        current_path.append(text)
        user_nav_state[uid] = current_path
        new_node = get_node(current_path)
        if isinstance(new_node, dict):
            if "__content__" in new_node:
                await message.answer(f"Вы выбрали: {'/'.join(current_path)}\n\n{new_node['__content__']}", reply_markup=get_main_menu_keyboard())
            else:
                await message.answer(f"Выберите подраздел для {'/'.join(current_path)}:", reply_markup=build_keyboard(list(new_node.keys()), include_back=True))
        return

    await message.answer("Пожалуйста, выберите один из предложенных вариантов.", reply_markup=get_main_menu_keyboard())

async def send_test_question(uid, chat_id):
    state = user_test_states.get(uid, {})
    questions = state.get("questions", [])
    current_index = state.get("current_index", 0)
    if current_index < len(questions):
        q = questions[current_index]
        options = q.get("options", [])
        question_text = q.get("question", "Вопрос не найден.")
        if options and isinstance(options, list):
            options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
            full_text = f"{question_text}\n\nВарианты ответов:\n{options_text}\n\nВведите ваш ответ:"
        else:
            full_text = f"{question_text}\n\nВведите ваш ответ:"
        await bot.send_message(chat_id, full_text)
    else:
        score = state.get("score", 0)
        total = len(questions)
        await bot.send_message(chat_id, f"Тест завершён! Вы набрали {score} из {total} баллов.")
        user_test_states[uid] = {}

@dp.callback_query(lambda c: c.data.startswith("reply_to_user:"))
async def inline_reply_handler(callback: types.CallbackQuery):
    admin_id = callback.from_user.id
    target_uid = callback.data.split(":")[1]
    admin_reply_pending[admin_id] = target_uid
    await bot.send_message(admin_id, "Напишите ответ пользователю.")
    await callback.answer()

@dp.message(lambda message: message.chat.id == ADMIN_CHAT_ID)
async def admin_message_handler(message: types.Message):
    admin_id = message.from_user.id
    if admin_id in admin_reply_pending:
        target_uid = admin_reply_pending.pop(admin_id)
        await bot.send_message(target_uid, f"Ответ от админа:\n{message.text}")
        await message.answer("Ответ отправлен пользователю.")

if __name__ == "__main__":
    logging.info("Бот запускается и ожидает сообщений...")
    asyncio.run(dp.start_polling(bot))