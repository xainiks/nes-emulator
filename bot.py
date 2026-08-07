import os
import asyncio
import sqlite3
import random
import string
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiohttp import web

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = "https://xainiks.github.io/nes-emulator/index.html"

async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_dummy_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

COOP_GAMES = {
    "tanks": {
        "title": "🛡 Танчики (Battle City)",
        "file": "tanks.nes"
    },
    "contra": {
        "title": "💥 Контра (Contra)",
        "file": "contra.nes"
    },
    "chip_dale": {
        "title": "🐿 Чип и Дейл 2",
        "file": "chip_dale.nes"
    }
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def delete_safe(message: types.Message):
    try:
        await message.delete()
    except Exception:
        pass

def generate_room_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def init_db():
    conn = sqlite3.connect("roms.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_roms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_name TEXT,
            file_id TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await delete_safe(message)

    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    
    # Вход второго игрока по инвайт-ссылке
    if args and args[0].startswith("join_"):
        parts = args[0].split("_")
        if len(parts) >= 3:
            game_file = parts[1]
            room_id = parts[2]
            play_url = f"{WEB_APP_URL}?rom={game_file}&room={room_id}"
            
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⚔️ Войти в игру (Игрок 2)", web_app=WebAppInfo(url=play_url))
            ]])
            
            text = (
                f"⚔️ <b>Тебя пригласили в сетевую игру!</b>\n\n"
                f"Файл: <code>{game_file}</code>\n"
                f"Нажми кнопку ниже, чтобы присоединиться к комнате!"
            )
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
            return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Встроенные Co-Op игры", callback_data="coop_menu")],
        [InlineKeyboardButton(text="📁 Моя картриджная полка", callback_data="my_library")]
    ])
    
    welcome_text = (
        "👾 <b>Retro Co-Op Club</b>\n\n"
        "Добро пожаловать в ретро-клуб! Выбери режим в меню ниже:"
    )
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "coop_menu")
async def coop_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, data in COOP_GAMES.items():
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=data["title"], callback_data=f"create_room_{data['file']}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")])
    
    text = "🕹 <b>Зал кооперативных игр:</b>\nВыбери игру, чтобы создать комнату для двоих:"
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# Создание комнаты для любой игры (встроенной или кастомной)
@dp.callback_query(F.data.startswith("create_room_"))
async def create_room(callback: types.CallbackQuery):
    game_file = callback.data.replace("create_room_", "")
    room_id = generate_room_id()
    bot_info = await bot.get_me()
    
    invite_link = f"https://t.me/{bot_info.username}?start=join_{game_file}_{room_id}"
    host_play_url = f"{WEB_APP_URL}?rom={game_file}&room={room_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить (Игрок 1 / Хост)", web_app=WebAppInfo(url=host_play_url))],
        [InlineKeyboardButton(text="✉️ Позвать напарника", switch_inline_query=f"Го в эмулятор вдвоем! Заходи: {invite_link}")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")]
    ])

    text = (
        f"🎯 <b>Сетевая комната создана!</b>\n\n"
        f"🎮 Файл игры: <code>{game_file}</code>\n"
        f"🔑 ID Комнаты: <code>{room_id}</code>\n\n"
        f"<b>Инструкция:</b>\n"
        f"1. Нажми <b>«Запустить (Игрок 1)»</b>\n"
        f"2. Отправь эту ссылку другу, чтобы он зашел как Игрок 2:\n"
        f"<code>{invite_link}</code>"
    )

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.message(F.document)
async def handle_custom_rom(message: types.Message):
    if not message.document.file_name.endswith('.nes'):
        err_msg = await message.answer("⚠️ Принимаются только файлы <code>.nes</code>", parse_mode="HTML")
        await asyncio.sleep(4)
        await delete_safe(err_msg)
        return
    
    conn = sqlite3.connect("roms.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_roms (user_id, file_name, file_id) VALUES (?, ?, ?)",
        (message.from_user.id, message.document.file_name, message.document.file_id)
    )
    conn.commit()
    conn.close()
    
    status_msg = await message.answer(
        f"💾 Картридж <b>{message.document.file_name}</b> добавился на твою полку!", 
        parse_mode="HTML"
    )
    await asyncio.sleep(4)
    await delete_safe(status_msg)

@dp.callback_query(F.data == "my_library")
async def show_my_library(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    conn = sqlite3.connect("roms.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_name FROM user_roms WHERE user_id = ?", (user_id,))
    roms = cursor.fetchall()
    conn.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    if not roms:
        text = (
            "📦 <b>Твоя полка картриджей пуста.</b>\n\n"
            "Загрузи `.nes` файл прямо в чат сообщением!"
        )
    else:
        text = "💾 <b>Твоя личная коллекция РОМов:</b>\nВыбери игру:"
        for rom_id, file_name in roms:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"🕹 {file_name}", 
                    callback_data=f"rom_options_{file_name}"
                )
            ])

    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# Выбор режима для пользовательского РОМа (Соло или Сеть)
@dp.callback_query(F.data.startswith("rom_options_"))
async def rom_options(callback: types.CallbackQuery):
    file_name = callback.data.replace("rom_options_", "")
    solo_url = f"{WEB_APP_URL}?rom={file_name}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Играть соло", web_app=WebAppInfo(url=solo_url))],
        [InlineKeyboardButton(text="👥 Создать комнату для двоих (Co-Op)", callback_data=f"create_room_{file_name}")],
        [InlineKeyboardButton(text="⬅️ Назад в библиотеку", callback_data="my_library")]
    ])
    
    await callback.message.edit_text(
        f"🎮 Игра: <b>{file_name}</b>\n\nКак ты хочешь сыграть?",
        reply_markup=kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Встроенные Co-Op игры", callback_data="coop_menu")],
        [InlineKeyboardButton(text="📁 Моя картриджная полка", callback_data="my_library")]
    ])
    
    text = "👾 <b>Retro Co-Op Club</b>\n\nВыбери режим в меню ниже:"
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

async def main():
    await start_dummy_server()
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
