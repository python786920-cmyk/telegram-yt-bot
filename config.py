import os
from typing import Optional

# Telegram Configuration (Your provided values)
API_ID: int = 21371233
API_HASH: str = "c4640e057a68388e35338f39f19dec3f"
BOT_TOKEN: str = "7987760307:AAEKVDBUZqMtncjLE2zbYBiqsVsYNELJEDo"

# Admin Configuration
ADMIN_USER_ID: int = 5175304803

# MongoDB Configuration (Updated with your credentials)
MONGO_URL: str = "mongodb+srv://cptapansary382_db_user:G87H66ujfAYUcxnF@cluster0.htkte1d.mongodb.net/ytbot?retryWrites=true&w=majority&appName=Cluster0"

# Download Configuration
TEMP_DOWNLOAD_PATH: str = "/tmp/downloads/"
MAX_FILE_SIZE: int = 2 * 1024 * 1024 * 1024  # 2GB limit (Telegram limit)

# YT-DLP Options
YTDL_OPTIONS = {
    'format': 'best[filesize<2G]',  # Limit to 2GB
    'outtmpl': f'{TEMP_DOWNLOAD_PATH}%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'writethumbnail': False,
    'writeinfojson': False,
    'writedescription': False,
    'writesubtitles': False,
    'writeautomaticsub': False,
    'ignoreerrors': True,
    'no_warnings': True,
    'extractaudio': False,
    'audioformat': 'mp3',
    'audioquality': '192K',
    'embed_subs': False,
}

# Video Quality Mappings
VIDEO_QUALITIES = {
    'best': 'Best Available',
    'worst': 'Lowest Quality', 
    '2160': '4K (2160p)',
    '1440': '2K (1440p)',
    '1080': 'Full HD (1080p)',
    '720': 'HD (720p)',
    '480': 'SD (480p)',
    '360': '360p',
    '240': '240p',
}

# Audio Quality Mappings
AUDIO_QUALITIES = {
    'best': 'Best Quality',
    '320': '320 kbps',
    '256': '256 kbps', 
    '192': '192 kbps',
    '128': '128 kbps',
    '64': '64 kbps',
}

# File Extensions
VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.webm', '.avi', '.mov']
AUDIO_EXTENSIONS = ['.mp3', '.m4a', '.opus', '.aac', '.wav']

# Progress Update Intervals
PROGRESS_UPDATE_INTERVAL = 3  # seconds

# Error Messages
ERROR_MESSAGES = {
    'invalid_url': '❌ Invalid YouTube URL. Please send a valid YouTube link.',
    'download_failed': '❌ Download failed. Please try again or contact support.',
    'file_too_large': '❌ File is too large. Maximum size allowed is 2GB.',
    'format_not_available': '❌ Requested format not available for this video.',
    'network_error': '❌ Network error. Please check your connection and try again.',
    'server_error': '❌ Server error. Please try again later.',
    'rate_limit': '❌ Too many requests. Please wait before trying again.',
    'upload_failed': '❌ Failed to send file. Please try again.',
}

# Success Messages
SUCCESS_MESSAGES = {
    'download_started': '🚀 Download started! Please wait...',
    'download_complete': '✅ Download completed successfully!',
    'sending_file': '📤 Sending file to your chat...',
    'file_sent': '✅ File sent successfully!',
}

# Validation Functions
def validate_config() -> bool:
    """Validate all required configuration variables"""
    required_vars = [
        ('API_ID', API_ID),
        ('API_HASH', API_HASH), 
        ('BOT_TOKEN', BOT_TOKEN),
        ('MONGO_URL', MONGO_URL),
        ('ADMIN_USER_ID', ADMIN_USER_ID),
    ]
    
    missing_vars = []
    for var_name, var_value in required_vars:
        if not var_value or (isinstance(var_value, int) and var_value == 0):
            missing_vars.append(var_name)
    
    if missing_vars:
        print(f"❌ Missing configuration variables: {', '.join(missing_vars)}")
        return False
    
    if "YOUR_PASSWORD" in MONGO_URL or "YOUR_ACTUAL_PASSWORD" in MONGO_URL:
        print("❌ Please update MONGO_URL with your actual MongoDB credentials")
        return False
    
    return True

def get_ytdl_options(format_id: Optional[str] = None, audio_only: bool = False) -> dict:
    """Get yt-dlp options based on format requirements"""
    options = YTDL_OPTIONS.copy()
    
    if audio_only:
        options['format'] = 'bestaudio[filesize<2G]/best[filesize<2G]'
        options['extractaudio'] = True
        options['audioformat'] = 'mp3'
    elif format_id:
        options['format'] = f'{format_id}[filesize<2G]/best[filesize<2G]'
    
    return options

# Runtime Configuration Check
if __name__ == "__main__":
    if validate_config():
        print("✅ All configuration variables are set!")
        print("✅ Simplified setup - No AWS required!")
    else:
        print("❌ Configuration validation failed!")
        print("💡 Make sure to replace YOUR_PASSWORD in MONGO_URL!")
        exit(1)
