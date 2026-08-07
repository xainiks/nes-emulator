import os
import asyncio
import random
import string
import re
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiohttp import web
from github import Github, Auth

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = os.getenv("GITHUB_USER", "xainiks")
GITHUB_REPO = os.getenv("GITHUB_REPO", "nes-emulator")

WEB_APP_URL = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}/index.html"

current_rom_list = []

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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def delete_safe(message: types.Message):
    try: await message.delete()
    except: pass

def generate_rom_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def upload_to_github(file_content: bytes, filename: str) -> bool:
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_user(GITHUB_USER).get_repo(GITHUB_REPO)
        filename = re.sub(r'[^a-zA-Z0-9_\.-]', '_', filename).lower()
        try:
            existing = repo.get_contents(filename)
            repo.update_file(existing.path, "Update via bot", file_content, existing.sha)
        except:
            repo.create_file(filename, "Upload via bot", file_content)
        return True
    except: return False

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await delete_safe(message)
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    
    if args and args[0].startswith("join_"):
        parts = args[0].split("_")
        if len(parts) >= 3:
            game_file = parts[1]
            room_id = parts[2]
            play_url = f"{WEB_APP_URL}?rom={game_file}&room={room_id}"
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⚔️ Войти в игру (Игрок 2)", web_app=WebAppInfo(url=play_url))
            ]])
            await message.answer(f"⚔️ <b>Тебя пригласили в сетевую игру!</b>\nИгра: <code>{game_file}</code>", reply_markup=kb, parse_mode="HTML")
            return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Моя картриджная полка", callback_data="my_library")]
    ])
    await message.answer("👾 <b>Retro Co-Op Club</b>\nСкинь .nes файл или открой полку.", reply_markup=keyboard, parse_mode="HTML")

@dp.message(F.document)
async def handle_custom_rom(message: types.Message):
    if not message.document.file_name.endswith('.nes'): return
    status = await message.answer("⏳ Загружаю РОМ на GitHub...")
    file_info = await bot.get_file(message.document.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    
    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(None, upload_to_github, file_bytes.read(), message.document.file_name)
    
    if success: await status.edit_text("✅ Успешно загружено!")
    else: await status.edit_text("❌ Ошибка загрузки.")
    await asyncio.sleep(3); await delete_safe(status)

@dp.callback_query(F.data == "my_library")
async def show_my_library(callback: types.CallbackQuery):
    global current_rom_list
    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth)
    repo = g.get_user(GITHUB_USER).get_repo(GITHUB_REPO)
    current_rom_list = [c.name for c in repo.get_contents("") if c.name.endswith('.nes')]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for i, name in enumerate(current_rom_list):
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🕹 {name[:22]}", callback_data=f"idx_{i}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="back")])
    await callback.message.edit_text("💾 <b>Твои игры на GitHub:</b>\nВыбери игру:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("idx_"))
async def rom_opts(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    name = current_rom_list[idx]
    solo_url = f"{WEB_APP_URL}?rom={name}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Играть соло", web_app=WebAppInfo(url=solo_url))],
        [InlineKeyboardButton(text="👥 Создать комнату для двоих (Co-Op)", callback_data=f"room_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад в библиотеку", callback_data="my_library")]
    ])
    await callback.message.edit_text(f"🎮 Игра: <code>{name}</code>\n\nВыбери режим:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("room_"))
async def create_room(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    name = current_rom_list[idx]
    room_id = generate_rom_id()
    bot_info = await bot.get_me()
    
    invite_link = f"https://t.me/{bot_info.username}?start=join_{name}_{room_id}"
    host_url = f"{WEB_APP_URL}?rom={name}&room={room_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить (Игрок 1 / Хост)", web_app=WebAppInfo(url=host_url))],
        [InlineKeyboardButton(text="✉️ Позвать напарника", switch_inline_query=f"Го в эмулятор вдвоем! Заходи: {invite_link}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"idx_{idx}")]
    ])

    text = (
        f"🎯 <b>Комната создана!</b>\n\n"
        f"🎮 Игра: <code>{name}</code>\n"
        f"🔑 ID: <code>{room_id}</code>\n\n"
        f"1. Жми <b>Запустить (Хост)</b>\n"
        f"2. Кинь ссылку другу:\n<code>{invite_link}</code>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.message.edit_text("👾 <b>Retro Co-Op Club</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Моя картриджная полка", callback_data="my_library")]
    ]), parse_mode="HTML")

async def main():
    await start_dummy_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
