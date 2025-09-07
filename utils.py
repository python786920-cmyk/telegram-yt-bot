import os
import asyncio
import aiofiles
from datetime import datetime
import yt_dlp
import hashlib
import re
from config import *

# Create temp directory
os.makedirs(TEMP_DOWNLOAD_PATH, exist_ok=True)

class ProgressHook:
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback
        self.last_update = 0
    
    def __call__(self, d):
        if d['status'] == 'downloading':
            if self.progress_callback and (datetime.now().timestamp() - self.last_update) > PROGRESS_UPDATE_INTERVAL:
                try:
                    percent = d.get('_percent_str', '0%').replace('%', '')
                    speed = d.get('_speed_str', '0B/s')
                    eta = d.get('_eta_str', 'Unknown')
                    
                    asyncio.create_task(
                        self.progress_callback(f"📥 **Downloading:** {percent}%\n⚡ **Speed:** {speed}\n⏰ **ETA:** {eta}")
                    )
                    self.last_update = datetime.now().timestamp()
                except:
                    pass
        elif d['status'] == 'finished':
            if self.progress_callback:
                asyncio.create_task(
                    self.progress_callback("✅ **Download completed!**\n📤 **Sending file to your chat...**")
                )

async def update_progress_message(message, text):
    """Update progress message safely"""
    try:
        await message.edit_text(text)
    except Exception as e:
        print(f"Error updating progress: {e}")

def sanitize_filename(filename):
    """Sanitize filename for safe storage"""
    # Remove unsafe characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Remove emojis and special characters
    filename = re.sub(r'[^\w\s-.]', '', filename)
    # Limit length
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:95] + ext
    return filename.strip()

async def download_video(url, format_id, format_type, progress_callback, title):
    """Download video/audio from YouTube"""
    try:
        # Create progress hook
        progress_hook = ProgressHook(progress_callback)
        
        # Configure yt-dlp options
        ytdl_opts = get_ytdl_options(format_id, format_type == 'audio')
        ytdl_opts['progress_hooks'] = [progress_hook]
        
        # Sanitize title for filename
        safe_title = sanitize_filename(title)
        
        # Add format-specific options
        if format_type == 'audio':
            ytdl_opts.update({
                'format': f'{format_id}[filesize<2G]/bestaudio[filesize<2G]/best[filesize<2G]',
                'extractaudio': True,
                'audioformat': 'mp3',
                'audioquality': '192K',
                'outtmpl': f'{TEMP_DOWNLOAD_PATH}{safe_title}.%(ext)s'
            })
        else:
            ytdl_opts.update({
                'format': f'{format_id}[filesize<2G]/best[filesize<2G]',
                'outtmpl': f'{TEMP_DOWNLOAD_PATH}{safe_title}.%(ext)s'
            })
        
        # Download
        with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
            # Download the file
            ydl.download([url])
            
            # Find downloaded file
            for file in os.listdir(TEMP_DOWNLOAD_PATH):
                if safe_title in file or any(word in file.lower() for word in safe_title.lower().split()[:3]):
                    file_path = os.path.join(TEMP_DOWNLOAD_PATH, file)
                    if os.path.getsize(file_path) > 100:  # File should be larger than 100 bytes
                        return file_path
            
            # Fallback: get the latest file
            files = [os.path.join(TEMP_DOWNLOAD_PATH, f) for f in os.listdir(TEMP_DOWNLOAD_PATH)]
            if files:
                latest_file = max(files, key=os.path.getctime)
                if os.path.getsize(latest_file) > 100:
                    return latest_file
                
    except Exception as e:
        print(f"Download error: {e}")
        return None

async def send_file_to_telegram(client, chat_id, file_path, title, format_type, progress_callback):
    """Send file directly to Telegram chat"""
    try:
        if not os.path.exists(file_path):
            return False
        
        # Get file size
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            await progress_callback("❌ **Error:** File too large (max 2GB)")
            return False
        
        if file_size < 100:
            await progress_callback("❌ **Error:** Downloaded file is too small or corrupted")
            return False
        
        await progress_callback("📤 **Sending file to your chat...**\n⏳ Please wait...")
        
        # Prepare file info
        filename = os.path.basename(file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Send file based on type and size
        try:
            if format_type == 'audio':
                # Send as audio
                await client.send_audio(
                    chat_id=chat_id,
                    audio=file_path,
                    title=title,
                    caption=f"🎵 **{title}**\n📁 **Size:** {file_size_mb:.1f} MB\n🎧 **Audio File**",
                    thumb=None
                )
            else:
                # Send as video
                await client.send_video(
                    chat_id=chat_id,
                    video=file_path,
                    caption=f"🎥 **{title}**\n📁 **Size:** {file_size_mb:.1f} MB\n🎬 **Video File**",
                    supports_streaming=True,
                    thumb=None
                )
            
            return True
            
        except Exception as upload_error:
            print(f"Upload error: {upload_error}")
            
            # Fallback: send as document
            try:
                await client.send_document(
                    chat_id=chat_id,
                    document=file_path,
                    caption=f"📁 **{title}**\n📊 **Size:** {file_size_mb:.1f} MB\n🎯 **Downloaded File**",
                    file_name=filename
                )
                return True
                
            except Exception as doc_error:
                print(f"Document upload error: {doc_error}")
                await progress_callback(f"❌ **Upload failed:** {str(doc_error)}")
                return False
            
    except Exception as e:
        print(f"File send error: {e}")
        await progress_callback(f"❌ **Error sending file:** {str(e)}")
        return False
    finally:
        # Clean up local file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Cleaned up: {file_path}")
        except Exception as cleanup_error:
            print(f"Cleanup error: {cleanup_error}")

async def process_download_and_send(client, url, format_id, format_type, progress_message, user_id, title):
    """Main download and send processing function"""
    try:
        # Progress callback function
        async def progress_callback(text):
            await update_progress_message(progress_message, text)
        
        # Step 1: Download
        await progress_callback(f"📥 **Starting download...**\n🎬 **{title}**\n⏳ Initializing...")
        
        file_path = await download_video(url, format_id, format_type, progress_callback, title)
        
        if not file_path or not os.path.exists(file_path):
            await progress_callback("❌ **Download failed!** Please try again or choose different quality.")
            return False
        
        # Step 2: Send file to Telegram
        success = await send_file_to_telegram(
            client, user_id, file_path, title, format_type, progress_callback
        )
        
        return success
        
    except Exception as e:
        await update_progress_message(progress_message, f"❌ **Error:** {str(e)}")
        print(f"Process download error: {e}")
        return False

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    return f"{size_bytes:.1f}{size_names[i]}"

def validate_youtube_url(url):
    """Validate if URL is a valid YouTube URL"""
    youtube_regex = re.compile(
        r'(?:https?://)(?:www\.)?(?:youtube\.com/(?:[^/]+/.+/|(?:v|e(?:mbed)?)/|.*[?&]v=)|youtu\.be/)([^"&?/\s]{11})'
    )
    return bool(youtube_regex.match(url))

async def cleanup_temp_files():
    """Clean up old temporary files"""
    try:
        current_time = datetime.now()
        if not os.path.exists(TEMP_DOWNLOAD_PATH):
            os.makedirs(TEMP_DOWNLOAD_PATH, exist_ok=True)
            return
            
        for filename in os.listdir(TEMP_DOWNLOAD_PATH):
            file_path = os.path.join(TEMP_DOWNLOAD_PATH, filename)
            if os.path.isfile(file_path):
                # Delete files older than 30 minutes
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                if (current_time - file_time).total_seconds() > 1800:
                    try:
                        os.remove(file_path)
                        print(f"Cleaned up temp file: {filename}")
                    except:
                        pass
    except Exception as e:
        print(f"Cleanup error: {e}")

def get_video_info(url):
    """Extract basic video information"""
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'upload_date': info.get('upload_date', ''),
            }
    except Exception as e:
        print(f"Info extraction error: {e}")
        return None

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
    try:
        youtube_regex = re.compile(
            r'(?:https?://)(?:www\.)?(?:youtube\.com/(?:[^/]+/.+/|(?:v|e(?:mbed)?)/|.*[?&]v=)|youtu\.be/)([^"&?/\s]{11})'
        )
        match = youtube_regex.search(url)
        return match.group(1) if match else None
    except:
        return None

async def get_video_formats(url):
    """Get available video formats with file size filtering"""
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            video_formats = []
            audio_formats = []
            
            # Process video formats
            for f in formats:
                if f.get('vcodec') != 'none' and f.get('height'):
                    height = f.get('height')
                    fps = f.get('fps', 30)
                    filesize = f.get('filesize', 0)
                    
                    # Skip files larger than 2GB
                    if filesize and filesize > MAX_FILE_SIZE:
                        continue
                        
                    if height >= 240:
                        format_note = f"{height}p{fps}" if fps > 30 else f"{height}p"
                        if not any(vf[1].split('(')[0].strip() == format_note for vf in video_formats):
                            video_formats.append((
                                f['format_id'], 
                                format_note, 
                                filesize,
                                f.get('ext', 'mp4')
                            ))
            
            # Process audio formats
            for f in formats:
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    ext = f.get('ext', 'unknown')
                    abr = f.get('abr', 128)
                    filesize = f.get('filesize', 0)
                    
                    # Skip files larger than 2GB
                    if filesize and filesize > MAX_FILE_SIZE:
                        continue
                        
                    if ext in ['mp3', 'm4a', 'opus', 'aac']:
                        audio_formats.append((
                            f['format_id'], 
                            f"{ext.upper()} {int(abr)}kbps", 
                            filesize,
                            ext
                        ))
            
            # Sort formats
            video_formats.sort(key=lambda x: int(x[1].split('p')[0]), reverse=True)
            audio_formats.sort(key=lambda x: int(re.search(r'(\d+)', x[1]).group(1)) if re.search(r'(\d+)', x[1]) else 0, reverse=True)
            
            return video_formats, audio_formats
            
    except Exception as e:
        print(f"Format extraction error: {e}")
        return [], []

def is_valid_format(format_id, available_formats):
    """Check if format ID is valid and available"""
    try:
        return any(f[0] == format_id for f in available_formats)
    except:
        return False

async def estimate_download_time(file_size, avg_speed_mbps=10):
    """Estimate download time based on file size"""
    try:
        if file_size <= 0:
            return "Unknown"
        
        # Convert to MB and estimate time
        size_mb = file_size / (1024 * 1024)
        time_seconds = size_mb / avg_speed_mbps
        
        if time_seconds < 60:
            return f"{int(time_seconds)}s"
        elif time_seconds < 3600:
            return f"{int(time_seconds/60)}m {int(time_seconds%60)}s"
        else:
            return f"{int(time_seconds/3600)}h {int((time_seconds%3600)/60)}m"
            
    except:
        return "Unknown"

def get_file_type_from_extension(filename):
    """Determine file type from extension"""
    try:
        _, ext = os.path.splitext(filename.lower())
        if ext in VIDEO_EXTENSIONS:
            return 'video'
        elif ext in AUDIO_EXTENSIONS:
            return 'audio'
        else:
            return 'document'
    except:
        return 'document'

def create_temp_directory():
    """Ensure temp directory exists"""
    try:
        os.makedirs(TEMP_DOWNLOAD_PATH, exist_ok=True)
        print(f"✅ Temp directory ready: {TEMP_DOWNLOAD_PATH}")
    except Exception as e:
        print(f"❌ Error creating temp directory: {e}")

# Run cleanup periodically
async def periodic_cleanup():
    """Run cleanup every 30 minutes"""
    while True:
        try:
            await asyncio.sleep(1800)  # 30 minutes
            await cleanup_temp_files()
        except Exception as e:
            print(f"Periodic cleanup error: {e}")

# Initialize on import
create_temp_directory()

# Start periodic cleanup if event loop is running
try:
    if asyncio.get_running_loop():
        asyncio.create_task(periodic_cleanup())
except RuntimeError:
    # No event loop running yet
    pass
