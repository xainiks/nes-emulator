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

fn_cache = {}

def generate_room_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def clean_filename(filename: str) -> str:
    # Заменяем плюсы и прочие спецсимволы на подчеркивание
    filename = filename.replace('+', '_')
    clean = re.sub(r'[^a-zA-Z0-9_\.-]', '_', filename).lower()
    fn_cache[clean] = filename
    return clean

def upload_to_github(file_content: bytes, filename: str) -> bool:
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN не установлен!")
        return False
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_user(GITHUB_USER).get_repo(GITHUB_REPO)
        try:
            existing_file = repo.get_contents(filename)
            repo.update_file(existing_file.path, f"Update {filename} via bot", file_content, existing_file.sha)
        except Exception:
            repo.create_file(filename, f"Upload {filename} via bot", file_content)
        return True
    except Exception as e:
        print(f"Ошибка загрузки на GitHub: {e}")
        return False

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
            
            text = (
                f"⚔️ <b>Тебя пригласили в сетевую игру!</b>\n\n"
                f"Игра: <code>{game_file}</code>\n"
                f"Жми кнопку ниже, чтобы войти в комнату!"
            )
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
            return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Встроенные Co-Op игры", callback_data="coop_menu")],
        [InlineKeyboardButton(text="📁 Моя картриджная полка", callback_data="my_library")]
    ])
    
    welcome_text = (
        "👾 <b>Retro Co-Op Club</b>\n\n"
        "Выбери режим или скинь `.nes` файл в чат, чтобы добавить свою игру!"
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
        f"🎮 Игра: <code>{game_file}</code>\n"
        f"🔑 ID Комнаты: <code>{room_id}</code>\n\n"
        f"<b>Инструкция:</b>\n"
        f"1. Нажми <b>«Запустить (Игрок 1)»</b>\n"
        f"2. Перешли ссылку другу:\n"
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

    status_msg = await message.answer("⏳ <i>Загружаю РОМ в облако GitHub, подожди пару секунд...</i>", parse_mode="HTML")

    original_name = message.document.file_name
    clean_name = clean_filename(original_name)

    file_info = await bot.get_file(message.document.file_id)
    file_bytes = await bot.download_file(file_info.file_path)

    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(None, upload_to_github, file_bytes.read(), clean_name)

    if success:
        await status_msg.edit_text(
            f"✅ Картридж <b>{original_name}</b> сохранён и выгружен на GitHub!\nТеперь можно играть соло или с другом.",
            parse_mode="HTML"
        )
    else:
        await status_msg.edit_text("❌ Ошибка при загрузке файла на GitHub. Проверь GITHUB_TOKEN.", parse_mode="HTML")

    await asyncio.sleep(5)
    await delete_safe(status_msg)

@dp.callback_query(F.data == "my_library")
async def show_my_library(callback: types.CallbackQuery):
    await callback.answer("⏳ Загружаю список игр с GitHub...")
    
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_user(GITHUB_USER).get_repo(GITHUB_REPO)
        contents = repo.get_contents("")
        roms = [c for c in contents if c.name.endswith('.nes')]

        kb = InlineKeyboardMarkup(inline_keyboard=[])

        if not roms:
            text = "📦 <b>Твоя полка картриджей пуста.</b>\n\nЗагрузи `.nes` файл прямо в чат!"
        else:
            text = "💾 <b>Твоя личная коллекция РОМов на GitHub:</b>\nВыбери игру:"
            for rom in roms:
                safe_data = clean_filename(rom.name)
                kb.inline_keyboard.append([
                    InlineKeyboardButton(
                        text=f"🕹 {rom.name[:25]}...", 
                        callback_data=f"rom_opts_{safe_data}"
                    )
                ])
        
        kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка при чтении с GitHub: {e}", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]])
        )

@dp.callback_query(F.data.startswith("rom_opts_"))
async def rom_options(callback: types.CallbackQuery):
    clean_name = callback.data.replace("rom_opts_", "")
    solo_url = f"{WEB_APP_URL}?rom={clean_name}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Играть соло", web_app=WebAppInfo(url=solo_url))],
        [InlineKeyboardButton(text="👥 Создать комнату для двоих (Co-Op)", callback_data=f"create_room_{clean_name}")],
        [InlineKeyboardButton(text="⬅️ Назад в библиотеку", callback_data="my_library")]
    ])
    
    await callback.message.edit_text(
        f"🎮 Игра: <code>{clean_name}</code>\n\nКак ты хочешь сыграть?",
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
