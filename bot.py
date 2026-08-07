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

# Фейковый сервер для Render
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

# Список Co-Op игр
COOP_GAMES = {
    "tanks": {
        "title": "🛡 Танчики (Battle City)",
        "file": "Battle City (J) [T+Rus1.2 PSCD (07.04.2017)].nes"
    },
    "contra": {
        "title": "💥 Контра (Contra)",
        "file": "Contra (U) [T-Rus uBAH009 (12.11.2016)].nes"
    },
    "chip_dale": {
        "title": "🐿 Чип и Дейл 2",
        "file": "Chip 'n Dale - Rescue Rangers 2 (U) [T+Rus She...nes"
    }
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Вспомогательная функция безопасного удаления сообщений
async def delete_safe(message: types.Message):
    try:
        await message.delete()
    except Exception:
        pass

def generate_room_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

# База данных
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
    # Удаляем сообщение команды /start от пользователя, чтобы не засорять чат
    await delete_safe(message)

    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    
    # Вход второго игрока по инвайт-ссылке
    if args and args[0].startswith("join_"):
        parts = args[0].split("_")
        if len(parts) >= 3:
            game_key = parts[1]
            room_id = parts[2]
            if game_key in COOP_GAMES:
                game = COOP_GAMES[game_key]
                play_url = f"{WEB_APP_URL}?rom={game['file']}&room={room_id}"
                
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="⚔️ Войти в игру (Игрок 2)", web_app=WebAppInfo(url=play_url))
                ]])
                
                text = (
                    f"⚔️ <b>Готов к сетевому дуэту?</b>\n\n"
                    f"Тебя пригласили в игру: <b>{game['title']}</b>\n"
                    f"Жми кнопку ниже, чтобы войти в сессию!"
                )
                await message.answer(text, reply_markup=kb, parse_mode="HTML")
                return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Сыграть с другом (Co-Op)", callback_data="coop_menu")],
        [InlineKeyboardButton(text="📁 Моя картриджная полка", callback_data="my_library")]
    ])
    
    welcome_text = (
        "👾 <b>Retro Co-Op Club</b>\n\n"
        "Добро пожаловать в ретро-клуб! Здесь можно зарубиться в легенды 8-бит "
        "прямо в Telegram — в одиночку или <b>вдвоем с другом в реальном времени</b>.\n\n"
        "Выбери режим в меню ниже:"
    )
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "coop_menu")
async def coop_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, data in COOP_GAMES.items():
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=data["title"], callback_data=f"create_room_{key}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")])
    
    text = "🕹 <b>Зал кооперативных игр:</b>\nВыбери игру, чтобы создать комнату для двоих:"
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("create_room_"))
async def create_room(callback: types.CallbackQuery):
    game_key = callback.data.replace("create_room_", "")
    game = COOP_GAMES.get(game_key)
    
    if not game:
        await callback.answer("Игра не найдена.")
        return

    room_id = generate_room_id()
    bot_info = await bot.get_me()
    
    invite_link = f"https://t.me/{bot_info.username}?start=join_{game_key}_{room_id}"
    host_play_url = f"{WEB_APP_URL}?rom={game['file']}&room={room_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить (Игрок 1 / Хост)", web_app=WebAppInfo(url=host_play_url))],
        [InlineKeyboardButton(text="✉️ Позвать напарника", switch_inline_query=f"Го в {game['title']} вдвоем! Заходи: {invite_link}")],
        [InlineKeyboardButton(text="⬅️ Выбрать другую игру", callback_data="coop_menu")]
    ])

    text = (
        f"🎯 <b>Игровая сессия создана!</b>\n\n"
        f"🎮 Игра: <b>{game['title']}</b>\n"
        f"🔑 ID Сессии: <code>{room_id}</code>\n\n"
        f"<b>Инструкция:</b>\n"
        f"1. Нажми кнопку <b>«Запустить (Игрок 1)»</b>\n"
        f"2. Отправь эту ссылку другу, чтобы он зашел как Игрок 2:\n"
        f"<code>{invite_link}</code>"
    )

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# Загрузка РОМов (пользовательский файл остается в чате, удаляется только уведомление бота)
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
        f"💾 Картридж <b>{message.document.file_name}</b> успешно добавлен в твою библиотеку!", 
        parse_mode="HTML"
    )
    
    # Стираем только статусное сообщение бота через 4 секунды
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
            "Чтобы добавить игру, просто скинь сюда <code>.nes</code> файл прямо сообщением!"
        )
    else:
        text = "💾 <b>Твоя личная коллекция РОМов:</b>\nВыбери игру для запуска:"
        for rom_id, file_name in roms:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"🕹 {file_name}", 
                    web_app=WebAppInfo(url=f"{WEB_APP_URL}?rom={file_name}")
                )
            ])

    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Сыграть с другом (Co-Op)", callback_data="coop_menu")],
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
