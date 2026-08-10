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

def clean_game_name(filename: str) -> str:
    name = filename.replace('.nes', '').replace('_', ' ').strip()
    return name.title()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await delete_safe(message)
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    
    # Обработка входа по пригласительной ссылке
    if args and args[0].startswith("join_"):
        parts = args[0].split("_")
        if len(parts) >= 3:
            game_file = parts[1]
            room_id = parts[2]
            display_name = clean_game_name(game_file)
            play_url = f"{WEB_APP_URL}?rom={game_file}&room={room_id}"
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚔️ Занять место 2-го Игрока", web_app=WebAppInfo(url=play_url))],
                [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back")]
            ])
            
            await message.answer(
                f"🎮 <b>Приглашение в игру!</b>\n\n"
                f"Тебя позвали сыграть в <b>{display_name}</b> 🕹\n\n"
                f"Жми кнопку ниже, чтобы подключиться ко 2-му джойстику:",
                reply_markup=kb, parse_mode="HTML"
            )
            return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Моя картриджная полка", callback_data="my_library")],
        [InlineKeyboardButton(text="❓ Инструкция и Справка", callback_data="faq")]
    ])
    await message.answer(
        "👾 <b>Retro Co-Op Club</b>\n\n"
        "Отправь сюда файл игры (<code>.nes</code>) или выбери картридж из своей коллекции ниже!", 
        reply_markup=keyboard, parse_mode="HTML"
    )

@dp.message(F.document)
async def handle_custom_rom(message: types.Message):
    if not message.document.file_name.endswith('.nes'): return
    status = await message.answer("⏳ <i>Продуваем картридж и вставляем в консоль...</i>", parse_mode="HTML")
    file_info = await bot.get_file(message.document.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    
    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(None, upload_to_github, file_bytes.read(), message.document.file_name)
    
    if success: 
        await status.edit_text("✅ <b>Картридж успешно добавлен на полку!</b>\n<i>Запуск будет доступен через 1 минуту.</i>", parse_mode="HTML")
    else: 
        await status.edit_text("❌ <i>Ошибка считывания картриджа. Попробуй ещё раз.</i>", parse_mode="HTML")
    await asyncio.sleep(4); await delete_safe(status)

@dp.callback_query(F.data == "my_library")
async def show_my_library(callback: types.CallbackQuery):
    global current_rom_list
    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth)
    repo = g.get_user(GITHUB_USER).get_repo(GITHUB_REPO)
    current_rom_list = [c.name for c in repo.get_contents("") if c.name.endswith('.nes')]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for i, filename in enumerate(current_rom_list):
        display_name = clean_game_name(filename)
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🕹 {display_name[:24]}", callback_data=f"idx_{i}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back")])
    await callback.message.edit_text("🎰 <b>Твоя коллекция картриджей:</b>\nВыбери игру для запуска:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("idx_"))
async def rom_opts(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    filename = current_rom_list[idx]
    display_name = clean_game_name(filename)
    solo_url = f"{WEB_APP_URL}?rom={filename}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Одиночный режим (Solo)", web_app=WebAppInfo(url=solo_url))],
        [InlineKeyboardButton(text="👥 Создать комнату для двоих (Co-Op)", callback_data=f"room_{idx}")],
        [InlineKeyboardButton(text="⬅️ К полке картриджей", callback_data="my_library")]
    ])
    await callback.message.edit_text(f"🎮 Игра: <b>{display_name}</b>\n\nВыбери режим игры:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("room_"))
async def create_room(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    filename = current_rom_list[idx]
    display_name = clean_game_name(filename)
    room_id = generate_rom_id()
    bot_info = await bot.get_me()
    
    invite_link = f"https://t.me/{bot_info.username}?start=join_{filename}_{room_id}"
    host_url = f"{WEB_APP_URL}?rom={filename}&room={room_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить игровую сессию (Игрок 1)", web_app=WebAppInfo(url=host_url))],
        [InlineKeyboardButton(text="✉️ Поделиться с другом", switch_inline_query=f"join_{filename}_{room_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"idx_{idx}")]
    ])

    text = (
        f"🎯 <b>Игровая комната создана!</b>\n\n"
        f"🎮 Игра: <b>{display_name}</b>\n"
        f"🔑 Код сессии: <code>{room_id}</code>\n\n"
        f"<b>Порядок действий:</b>\n"
        f"1. Ты (Хост) нажимаешь <b>«Запустить игровую сессию»</b>.\n"
        f"2. Пересылаешь ссылку другу:\n<code>{invite_link}</code>\n\n"
        f"<i>Друг перейдет по ссылке, нажмет /start и сразу получит кнопку для входа вторым игроком.</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "faq")
async def show_faq(callback: types.CallbackQuery):
    faq_text = (
        "📖 <b>Инструкция и Справка:</b>\n\n"
        "1️⃣ <b>Задержка при добавлении игры:</b>\n"
        "После того как ты скинул новый файл <code>.nes</code>, подожди примерно <b>1 минуту</b> перед запуском. Эмулятору нужно время, чтобы подготовить новый картридж.\n\n"
        "2️⃣ <b>Как играть вдвоем (Co-Op):</b>\n"
        "• Выбери игру на полке ➡️ <b>«Создать комнату для двоих»</b>.\n"
        "• <b>Первый игрок (Хост)</b> обязательно запускает игру ПЕРВЫМ.\n"
        "• <b>Второй игрок</b> подключается по пересланной ссылке только ПОСЛЕ того, как Хост вошел в игру.\n\n"
        "3️⃣ <b>Если появляется «Ошибка сети»:</b>\n"
        "Просто закрой окно игры, подожди полминуты и нажми «Запустить» еще раз."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back")]
    ])
    await callback.message.edit_text(faq_text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Моя картриджная полка", callback_data="my_library")],
        [InlineKeyboardButton(text="❓ Инструкция и Справка", callback_data="faq")]
    ])
    await callback.message.edit_text("👾 <b>Retro Co-Op Club</b>", reply_markup=keyboard, parse_mode="HTML")

async def main():
    await start_dummy_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
