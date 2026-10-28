import os
import math
import asyncio
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

API_ID = int(os.environ.get("API_ID", 2040))
API_HASH = os.environ.get("API_HASH", "b18441a1ff607e10a989891a5462e627")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", -100123456789))
SPONSOR_CHANNEL = os.environ.get("SPONSOR_CHANNEL", "").replace("@", "")
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", os.environ.get("BASE_URL", "")).rstrip("/")
PORT = int(os.environ.get("PORT", 8080))

app = Client("streamer_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
routes = web.RouteTableDef()

@routes.get("/")
async def home_handler(request):
    return web.Response(text="Bot is Running 24/7 on Render!", status=200)

@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    await message.reply_text("👋 سلام! هر فایلی (تا ۴ گیگابایت) را برای من بفرستید یا فوروارد کنید تا بلافاصله لینک مستقیم پرسرعت آن را تحویل بگیرید.")

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def file_handler(client, message):
    user_id = message.from_user.id
    
    if SPONSOR_CHANNEL:
        try:
            await client.get_chat_member(f"@{SPONSOR_CHANNEL}", user_id)
        except UserNotParticipant:
            join_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 عضویت در کانال ما", url=f"https://t.me/{SPONSOR_CHANNEL}")],
                [InlineKeyboardButton("✅ عضو شدم", url=f"https://t.me/{(await client.get_me()).username}?start=check")]
            ])
            return await message.reply_text(
                "⚠️ **برای دریافت لینک دانلود مستقیم، ابتدا در کانال ما عضو شوید و سپس فایل را دوباره ارسال کنید:**",
                reply_markup=join_btn
            )

    log_msg = await message.copy(chat_id=LOG_CHANNEL)
    
    media = message.document or message.video or message.audio
    file_name = getattr(media, "file_name", None) or f"file_{log_msg.id}.mp4"
    file_name = file_name.replace(" ", "_")
    file_size_mb = round(media.file_size / (1024 * 1024), 2)

    stream_link = f"{BASE_URL}/dl/{log_msg.id}/{file_name}"

    buttons = [[InlineKeyboardButton("🚀 دانلود مستقیم (IDM)", url=stream_link)]]
    if SPONSOR_CHANNEL:
        buttons.append([InlineKeyboardButton("🔥 کانال ما", url=f"https://t.me/{SPONSOR_CHANNEL}")])

    await message.reply_text(
        f"✅ **لینک مستقیم آماده شد!**\n\n"
        f"📁 **نام فایل:** `{file_name}`\n"
        f"📦 **حجم:** `{file_size_mb} MB`\n\n"
        f"🔗 **لینک دانلود:**\n{stream_link}",
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )

@routes.get("/dl/{msg_id}/{file_name}")
async def stream_handler(request):
    try:
        msg_id = int(request.match_info["msg_id"])
        file_name = request.match_info["file_name"]

        msg = await app.get_messages(LOG_CHANNEL, msg_id)
        media = msg.document or msg.video or msg.audio
        if not media:
            return web.Response(status=404, text="File Not Found!")

        file_size = media.file_size
        mime_type = getattr(media, "mime_type", "application/octet-stream")

        range_header = request.headers.get("Range", None)
        from_bytes = 0
        until_bytes = file_size - 1

        if range_header:
            range_parts = range_header.replace("bytes=", "").split("-")
            from_bytes = int(range_parts[0])
            if range_parts[1]:
                until_bytes = int(range_parts[1])

        content_length = until_bytes - from_bytes + 1
        chunk_size = 1024 * 1024 
        offset_chunks = from_bytes // chunk_size
        first_part_cut = from_bytes % chunk_size
        total_chunks = math.ceil((until_bytes + 1) / chunk_size) - offset_chunks

        headers = {
            "Content-Type": mime_type,
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Disposition": f'attachment; filename="{file_name}"',
        }
        if range_header:
            headers["Content-Range"] = f"bytes {from_bytes}-{until_bytes}/{file_size}"

        response = web.StreamResponse(status=206 if range_header else 200, headers=headers)
        await response.prepare(request)

        current_chunk = 0
        bytes_written = 0

        async for chunk in app.stream_media(msg, offset=offset_chunks, limit=total_chunks):
            current_chunk += 1
            if current_chunk == 1 and first_part_cut > 0:
                chunk = chunk[first_part_cut:]
            if bytes_written + len(chunk) > content_length:
                chunk = chunk[:content_length - bytes_written]
            await response.write(chunk)
            bytes_written += len(chunk)
            if bytes_written >= content_length:
                break

        return response
    except Exception as e:
        return web.Response(status=500, text=f"Error: {str(e)}")

async def start_services():
    await app.start()
    server = web.Application()
    server.add_routes(routes)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Bot is running on port {PORT}!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(start_services())
