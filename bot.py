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

# Фейковый веб-сервер для Render
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

# Список Co-Op игр (названия файлов строго как в репозитории)
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

def generate_room_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

# База данных для личной библиотеки
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
                    InlineKeyboardButton(text="🎮 Войти в игру (Игрок 2)", web_app=WebAppInfo(url=play_url))
                ]])
                await message.answer(
                    f"⚔️ **Вас пригласили в Co-Op!**\nИгра: **{game['title']}**\nНажми кнопку ниже, чтобы войти в комнату!",
                    reply_markup=kb
                )
                return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть с другом (Co-Op)", callback_data="coop_menu")],
        [InlineKeyboardButton(text="📁 Моя библиотека РОМов", callback_data="my_library")]
    ])
    
    await message.answer(
        "👋 **Привет! Это сетевой NES-эмулятор.**\n\n"
        "Выбери режим:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "coop_menu")
async def coop_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, data in COOP_GAMES.items():
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=data["title"], callback_data=f"create_room_{key}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    
    await callback.message.edit_text("🕹 **Выбери игру для совместной игры:**", reply_markup=kb)

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
        [InlineKeyboardButton(text="▶️ Запустить как Игрок 1 (Host)", web_app=WebAppInfo(url=host_play_url))],
        [InlineKeyboardButton(text="✉️ Пригласить друга", switch_inline_query=f"Сыграем в {game['title']} вдвоем! Заходи: {invite_link}")],
        [InlineKeyboardButton(text="⬅️ Выбрать другую игру", callback_data="coop_menu")]
    ])

    await callback.message.edit_text(
        f"🎮 **Комната создана!**\n\n"
        f"Игра: **{game['title']}**\n"
        f"ID Сессии: `{room_id}`\n\n"
        f"1. Нажми **«Запустить как Игрок 1»**\n"
        f"2. Перешли ссылку другу:\n`{invite_link}`",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message(F.document)
async def handle_custom_rom(message: types.Message):
    if not message.document.file_name.endswith('.nes'):
        await message.answer("⚠️ Принимаются только файлы `.nes`")
        return
    
    conn = sqlite3.connect("roms.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_roms (user_id, file_name, file_id) VALUES (?, ?, ?)",
        (message.from_user.id, message.document.file_name, message.document.file_id)
    )
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Файл **{message.document.file_name}** добавлен в библиотеку!")

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
            "📁 **Твоя библиотека пока пуста.**\n\n"
            "Чтобы добавить свою игру, просто **отправь `.nes` файл** боту в этот чат!"
        )
    else:
        text = "📁 **Твои загруженные РОМы:**\nВыбери игру для запуска:"
        for rom_id, file_name in roms:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"🎮 {file_name}", 
                    web_app=WebAppInfo(url=f"{WEB_APP_URL}?rom={file_name}")
                )
            ])

    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть с другом (Co-Op)", callback_data="coop_menu")],
        [InlineKeyboardButton(text="📁 Моя библиотека РОМов", callback_data="my_library")]
    ])
    await callback.message.edit_text("👋 **Привет! Это сетевой NES-эмулятор.**\n\nВыбери режим:", reply_markup=keyboard)

async def main():
    await start_dummy_server()
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
