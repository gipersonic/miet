import asyncio
import json
import os
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)

logging.basicConfig(level=logging.INFO)

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()
API_TOKEN = config["bot_token"]
ADMIN_CHAT_ID = config.get("admin_chat_id")

def load_subjects():
    try:
        with open("subjects.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка чтения subjects.json: {e}")
        return {}

def build_keyboard(options):
    # Клавиатура для выбора уроков
    buttons = [[KeyboardButton(text=opt)] for opt in options]
    buttons.append([KeyboardButton(text="Главное меню")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_main_menu_keyboard():
    # Клавиатура главного меню с кнопками для отзыва, связи с админом и возврата назад
    buttons = [
        [KeyboardButton(text="Оставить отзыв"), KeyboardButton(text="Связаться с админом")],
        [KeyboardButton(text="Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Глобальные словари для отслеживания режимов ожидания отзыва и контакта
review_pending = {}
contact_pending = {}

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    top_options = list(load_subjects().keys())
    kb = build_keyboard(top_options)
    await message.answer("Привет! Выберите урок:", reply_markup=kb)
    # Сброс режимов при старте
    review_pending[str(message.from_user.id)] = False
    contact_pending[str(message.from_user.id)] = False

@dp.message()
async def text_handler(message: types.Message):
    if not message.text:
        return

    uid = str(message.from_user.id)
    text = message.text.strip().lower()

    # Если пользователь находится в режиме ожидания отзыва
    if review_pending.get(uid, False):
        if text == "назад":
            review_pending[uid] = False
            top_options = list(load_subjects().keys())
            await message.answer("Отзыв отменён. Выберите урок:", reply_markup=build_keyboard(top_options))
        else:
            sender_info = f"Отзыв от {message.from_user.full_name} (ID: {uid})"
            review_message = f"{sender_info}:\n\n{message.text}"
            try:
                await bot.send_message(chat_id=ADMIN_CHAT_ID, text=review_message)
                await message.answer("Ваш отзыв отправлен. Спасибо!", reply_markup=get_main_menu_keyboard())
            except Exception as e:
                logging.error(f"Ошибка при отправке отзыва: {e}")
                await message.answer("Произошла ошибка при отправке отзыва.", reply_markup=get_main_menu_keyboard())
            review_pending[uid] = False
        return

    # Если пользователь находится в режиме связи с администрацией
    if contact_pending.get(uid, False):
        if text == "назад":
            contact_pending[uid] = False
            top_options = list(load_subjects().keys())
            await message.answer("Связь с администрацией отменена. Выберите урок:", reply_markup=build_keyboard(top_options))
        else:
            sender_info = f"Сообщение от {message.from_user.full_name} (ID: {uid})"
            contact_message = f"{sender_info}:\n\n{message.text}"
            try:
                await bot.send_message(chat_id=ADMIN_CHAT_ID, text=contact_message)
                await message.answer("Ваше сообщение отправлено администратору. Напишите ещё или введите 'Назад' для выхода.", reply_markup=get_main_menu_keyboard())
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения администратору: {e}")
                await message.answer("Произошла ошибка при отправке вашего сообщения.", reply_markup=get_main_menu_keyboard())
        return

    # Обработка кнопки "главное меню" - переходим в главное меню
    if text == "главное меню":
        await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
        return

    # Обработка кнопки "оставить отзыв"
    if text == "оставить отзыв":
        review_pending[uid] = True
        await message.answer("Пожалуйста, напишите ваш отзыв и отправьте его. Для отмены введите 'Назад'.", reply_markup=get_main_menu_keyboard())
        return

    # Обработка кнопки "связаться с админом"
    if text == "связаться с админом":
        contact_pending[uid] = True
        await message.answer("Пожалуйста, напишите ваше сообщение для администрации. Для отмены введите 'Назад'.", reply_markup=get_main_menu_keyboard())
        return

    # Обработка кнопки "назад" - возвращаем к выбору уроков
    if text == "назад":
        top_options = list(load_subjects().keys())
        await message.answer("Привет! Выберите урок:", reply_markup=build_keyboard(top_options))
        return

    subjects = load_subjects()
    if text in subjects:
        await message.answer(f"Вы выбрали урок: {text}", reply_markup=ReplyKeyboardRemove())
        return

    await message.answer("Пожалуйста, выберите один из предложенных вариантов.", reply_markup=get_main_menu_keyboard())

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
