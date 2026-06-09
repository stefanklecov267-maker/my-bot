import os
import asyncio
from aiohttp import web
from telethon import TelegramClient, events, Button
import yt_dlp

# --- НАСТРОЙКИ (Берутся из настроек Render) ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Создаем объект клиента, но не запускаем его сразу
bot = TelegramClient('bot_session', API_ID, API_HASH)

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (Заглушка для работы 24/7 бесплатно) ---
async def handle_ping(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f" Web-server started on port {port}")

# --- ФУНКЦИИ СКАЧИВАНИЯ МЕДИА ---
def download_general_video(url):
    """Скачивание для TikTok и Instagram (лучшее качество автоматически)"""
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            filename = os.path.splitext(filename)[0] + '.mp4'
        return filename

def get_youtube_formats(url):
    """Получение доступных разрешений для YouTube видео"""
    ydl_opts = {'quiet': True, 'no_warnings': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = info.get('formats', [])
        
        available_res = set()
        for f in formats:
            res = f.get('height')
            if res and res in [360, 480, 720, 1080]:
                available_res.add(res)
                
        return sorted(list(available_res)), info.get('title', 'Video')

def download_youtube_video(url, resolution):
    """Скачивание YouTube видео в выбранном качестве"""
    ydl_opts = {
        'format': f'bestvideo[height<={resolution}]+bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            filename = os.path.splitext(filename)[0] + '.mp4'
        return filename

# --- ОБРАБОТКА КОМАНД И ССЫЛОК ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond("Привет! Отправь мне ссылку на видео из TikTok, Instagram или YouTube, и я его скачаю!")

@bot.on(events.NewMessage)
async def handle_message(event):
    url = event.text.strip()
    
    if not url.startswith(("http://", "https://")):
        return

    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    status_msg = await event.respond("Обрабатываю ссылку, подожди...")

    try:
        if "youtube.com" in url or "youtu.be" in url:
            loop = asyncio.get_running_loop()
            resolutions, title = await loop.run_in_executor(None, get_youtube_formats, url)
            
            if not resolutions:
                resolutions = [360]

            # rb"" исправляет предупреждение синтаксиса (SyntaxWarning)
            buttons = [
                [Button.inline(f"🎬 {res}p", data=f"yt|{res}|{url}")] for res in resolutions
            ]
            await status_msg.edit(f"Выбери качество для видео:\n**{title}**", buttons=buttons)
            
        elif "tiktok.com" in url or "instagram.com" in url:
            await status_msg.edit("⏳ Скачиваю видео...")
            loop = asyncio.get_running_loop()
            filepath = await loop.run_in_executor(None, download_general_video, url)
            
            await status_msg.edit("📤 Отправляю видео в Telegram...")
            await bot.send_file(event.chat_id, filepath, caption="Вот твое видео!")
            
            if os.path.exists(filepath):
                os.remove(filepath)
            await status_msg.delete()
            
    except Exception as e:
        await status_msg.edit(f"❌ Произошла ошибка: {str(e)}")

# --- ОБРАБОТКА НАЖАТИЯ НА КНОПКИ КАЧЕСТВА YOUTUBE ---
# Добавлена буква r перед b (rb"yt\|"), чтобы убрать ошибку escape-последовательности
@bot.on(events.CallbackQuery(pattern=rb"yt\|"))
async def youtube_callback(event):
    data = event.data.decode('utf-8').split('|')
    resolution = data[1]
    url = data[2]
    
    await event.edit(f"⏳ Скачиваю YouTube видео в качестве {resolution}p...")
    
    try:
        loop = asyncio.get_running_loop()
        filepath = await loop.run_in_executor(None, download_youtube_video, url, resolution)
        
        await event.edit("📤 Отправляю видео в Telegram...")
        await bot.send_file(event.chat_id, filepath, caption=f"YouTube видео ({resolution}p)")
        
        if os.path.exists(filepath):
            os.remove(filepath)
        await event.delete()
        
    except Exception as e:
        await event.edit(f"❌ Ошибка загрузки: {str(e)}")

# --- ИСПРАВЛЕННЫЙ И СТАБИЛЬНЫЙ ЗАПУСК ---
async def main():
    # 1. Запуск веб-сервера заглушки для Render
    await start_web_server()
    
    # 2. Безопасный асинхронный старт самого бота Telethon
    await bot.start(bot_token=BOT_TOKEN)
    print(" Бот успешно запущен и авторизован в Telegram!")
    
    # 3. Поддержание работы бота
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот принудительно остановлен.")
