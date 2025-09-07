import asyncio
import re
import os
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import yt_dlp
from motor.motor_asyncio import AsyncIOMotorClient
from config import *
from utils import *

# Initialize bot
app = Client("yt_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB setup
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client.ytbot
users_col = db.users
downloads_col = db.downloads

# Start command
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # Add user to database
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "first_seen": datetime.now()}, "$inc": {"download_count": 0}},
        upsert=True
    )
    
    welcome_text = f"""
🎥 **Professional YouTube Downloader Bot**

👋 Hello {message.from_user.first_name}!

🚀 **Features:**
• Download videos in all qualities (240p → 2160p60)
• Audio formats: MP3, M4A, Opus
• Direct Telegram file delivery
• Fast & secure downloads

📝 **How to use:**
Just send me any YouTube link and I'll handle the rest!

⚡ **Supported:** YouTube, YouTube Music, YouTube Shorts
📊 **File Limit:** Up to 2GB per file
"""
    
    await message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Help", callback_data="help")],
            [InlineKeyboardButton("📊 My Stats", callback_data="stats")]
        ])
    )

# YouTube URL handler
@app.on_message(filters.regex(r'(?:https?://)(?:www\.)?(?:youtube\.com/(?:[^/]+/.+/|(?:v|e(?:mbed)?)/|.*[?&]v=)|youtu\.be/)([^"&?/\s]{11})'))
async def url_handler(client, message):
    url = message.text.strip()
    user_id = message.from_user.id
    
    # Send processing message
    process_msg = await message.reply_text("🔍 **Analyzing video...**\n⏳ Please wait...")
    
    try:
        # Extract video info
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            
        title = info.get('title', 'Unknown Title')[:50]
        duration = info.get('duration', 0)
        thumbnail = info.get('thumbnail', '')
        uploader = info.get('uploader', 'Unknown')
        
        # Format duration
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Unknown"
        
        # Get available formats
        formats = info.get('formats', [])
        video_formats = []
        audio_formats = []
        
        # Video formats
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('height'):
                height = f.get('height')
                fps = f.get('fps', 30)
                filesize = f.get('filesize', 0)
                
                # Check file size limit (2GB = 2147483648 bytes)
                if filesize and filesize > 2147483648:
                    continue
                    
                if height >= 240:
                    format_note = f"{height}p{fps}" if fps > 30 else f"{height}p"
                    size_mb = f" ({filesize//1024//1024}MB)" if filesize > 0 else ""
                    
                    if not any(vf[1].split('(')[0].strip() == format_note for vf in video_formats):
                        video_formats.append((f['format_id'], f"{format_note}{size_mb}", filesize))
        
        # Audio formats
        for f in formats:
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                ext = f.get('ext', 'unknown')
                abr = f.get('abr', 128)
                filesize = f.get('filesize', 0)
                
                # Check file size limit
                if filesize and filesize > 2147483648:
                    continue
                    
                if ext in ['mp3', 'm4a', 'opus']:
                    size_mb = f" ({filesize//1024//1024}MB)" if filesize > 0 else ""
                    audio_formats.append((f['format_id'], f"{ext.upper()} {int(abr)}kbps{size_mb}", filesize))
        
        # Sort formats
        video_formats.sort(key=lambda x: int(x[1].split('p')[0]), reverse=True)
        audio_formats = audio_formats[:3]  # Top 3 audio formats
        
        # Create keyboard
        keyboard = []
        
        # Video buttons (2 per row)
        video_row = []
        for i, (format_id, format_name, size) in enumerate(video_formats[:8]):
            video_row.append(InlineKeyboardButton(
                f"🎥 {format_name}", 
                callback_data=f"dl_video_{format_id}_{i}"
            ))
            if len(video_row) == 2:
                keyboard.append(video_row)
                video_row = []
        if video_row:
            keyboard.append(video_row)
        
        # Audio buttons
        audio_row = []
        for i, (format_id, format_name, size) in enumerate(audio_formats):
            audio_row.append(InlineKeyboardButton(
                f"🎵 {format_name}",
                callback_data=f"dl_audio_{format_id}_{i}"
            ))
        if audio_row:
            keyboard.append(audio_row)
        
        # Store URL in callback data workaround
        app.temp_urls = getattr(app, 'temp_urls', {})
        app.temp_urls[user_id] = {
            'url': url,
            'video_formats': video_formats,
            'audio_formats': audio_formats,
            'title': title
        }
        
        # Update message
        video_info = f"""
🎥 **{title}**

👤 **Channel:** {uploader}
⏱️ **Duration:** {duration_str}

📊 **Available Formats:**
📹 **Video:** {len(video_formats)} qualities
🎵 **Audio:** {len(audio_formats)} formats

🔽 **Select format to download:**
"""
        
        await process_msg.edit_text(
            video_info,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await process_msg.edit_text(f"❌ **Error:** {str(e)}")

# Download callback handler
@app.on_callback_query(filters.regex(r"dl_(video|audio)_(.+)_(\d+)"))
async def download_callback(client, callback_query: CallbackQuery):
    try:
        data = callback_query.data
        parts = data.split('_')
        format_type = parts[1]  # video or audio
        format_id = parts[2]
        format_index = int(parts[3])
        
        user_id = callback_query.from_user.id
        
        # Get stored URL and formats
        if not hasattr(app, 'temp_urls') or user_id not in app.temp_urls:
            await callback_query.answer("❌ Session expired! Send YouTube link again.")
            return
        
        user_data = app.temp_urls[user_id]
        url = user_data['url']
        title = user_data['title']
        
        await callback_query.answer("🚀 Starting download...")
        
        # Edit message to show progress
        progress_msg = await callback_query.message.edit_text(
            f"⏳ **Preparing download...**\n🎬 **{title}**\n📥 Initializing..."
        )
        
        # Download and send file
        success = await process_download_and_send(
            client, url, format_id, format_type, progress_msg, user_id, title
        )
        
        if success:
            # Log download
            await downloads_col.insert_one({
                "user_id": user_id,
                "yt_url": url,
                "format": format_id,
                "format_type": format_type,
                "title": title,
                "download_time": datetime.now()
            })
            
            # Update user stats
            await users_col.update_one(
                {"user_id": user_id},
                {"$inc": {"download_count": 1}}
            )
            
            # Send completion message
            await progress_msg.edit_text(
                f"✅ **Download Completed!**\n\n"
                f"🎬 **{title}**\n"
                f"📱 **File sent successfully to your chat!**\n\n"
                f"🔄 Send another YouTube link to download more!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Download Another", callback_data="new_download")]
                ])
            )
        else:
            await progress_msg.edit_text(
                f"❌ **Download failed!**\n\n"
                f"🎬 **{title}**\n"
                f"Please try again or choose different quality."
            )
            
    except Exception as e:
        await callback_query.message.edit_text(f"❌ **Error:** {str(e)}")

# Admin stats command
@app.on_message(filters.command("stats") & filters.user(ADMIN_USER_ID))
async def stats_handler(client, message):
    try:
        total_users = await users_col.count_documents({})
        total_downloads = await downloads_col.count_documents({})
        
        # Recent stats (last 24 hours)
        yesterday = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        recent_downloads = await downloads_col.count_documents({"download_time": {"$gte": yesterday}})
        
        # Top downloaded formats
        pipeline = [
            {"$group": {"_id": "$format_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        format_stats = await downloads_col.aggregate(pipeline).to_list(length=10)
        
        stats_text = f"""
📊 **Bot Statistics**

👥 **Total Users:** {total_users:,}
📥 **Total Downloads:** {total_downloads:,}
🔥 **Today's Downloads:** {recent_downloads:,}

📊 **Popular Formats:**
"""
        
        for stat in format_stats[:3]:
            stats_text += f"• {stat['_id'].title()}: {stat['count']} downloads\n"
        
        stats_text += f"\n🕐 **Updated:** {datetime.now().strftime('%H:%M:%S')}"
        
        await message.reply_text(stats_text)
        
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

# Broadcast command
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_USER_ID))
async def broadcast_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text("**Usage:** /broadcast <message>")
        return
    
    broadcast_msg = " ".join(message.command[1:])
    
    # Get all users
    users = await users_col.find({}).to_list(length=None)
    
    sent = 0
    failed = 0
    
    status_msg = await message.reply_text(f"📢 Broadcasting to {len(users)} users...")
    
    for user in users:
        try:
            await app.send_message(user['user_id'], broadcast_msg)
            sent += 1
        except:
            failed += 1
        
        # Update status every 10 users
        if (sent + failed) % 10 == 0:
            await status_msg.edit_text(
                f"📢 Broadcasting...\n✅ Sent: {sent}\n❌ Failed: {failed}"
            )
    
    await status_msg.edit_text(
        f"📢 **Broadcast Complete!**\n✅ Sent: {sent}\n❌ Failed: {failed}"
    )

# Help callback
@app.on_callback_query(filters.regex("help"))
async def help_callback(client, callback_query):
    help_text = """
📖 **How to Use**

1️⃣ Send any YouTube link
2️⃣ Choose video quality or audio format  
3️⃣ Wait for download to complete
4️⃣ File will be sent directly to your chat!

🎥 **Video Qualities:** 240p, 360p, 480p, 720p, 1080p, 1440p, 2160p
🎵 **Audio Formats:** MP3, M4A, Opus

⚡ **Features:**
• Direct file delivery
• Up to 2GB file support
• Fast downloads
• Multiple quality options

📱 **Mobile & Desktop friendly**
"""
    await callback_query.answer()
    await callback_query.message.reply_text(help_text)

# Statistics callback
@app.on_callback_query(filters.regex("stats"))
async def stats_callback(client, callback_query):
    user_id = callback_query.from_user.id
    
    try:
        user_data = await users_col.find_one({"user_id": user_id})
        user_downloads = user_data.get('download_count', 0) if user_data else 0
        
        stats_text = f"""
📊 **Your Statistics**

📥 **Your Downloads:** {user_downloads}
📅 **Member Since:** {user_data.get('first_seen', datetime.now()).strftime('%Y-%m-%d') if user_data else 'Today'}

🚀 **Keep downloading with our fast service!**
"""
        
        await callback_query.answer()
        await callback_query.message.reply_text(stats_text)
        
    except Exception as e:
        await callback_query.answer("Error loading stats")

# New download callback
@app.on_callback_query(filters.regex("new_download"))
async def new_download_callback(client, callback_query):
    await callback_query.answer()
    await callback_query.message.reply_text(
        "🎥 **Ready for new download!**\n\n📝 Send me any YouTube link to get started."
    )

# Run bot
if __name__ == "__main__":
    print("🚀 Starting Professional YT Downloader Bot...")
    print("✅ No AWS required - Direct Telegram delivery!")
    app.run()
