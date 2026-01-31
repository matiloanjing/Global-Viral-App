"""
YouTube Auto-Post Module
=========================
Upload videos to YouTube with AI-generated captions.
Uses official YouTube Data API v3 with OAuth 2.0.

Created: 2026-01-31
"""

import os
import sys
import json
import pickle
import httplib2
from pathlib import Path
from typing import Optional, Dict, Any

# Google API imports
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    HAS_YOUTUBE_API = True
except ImportError:
    HAS_YOUTUBE_API = False
    print("⚠️ YouTube API libraries not installed. Run: pip install google-api-python-client google-auth-oauthlib")

# Scopes for YouTube upload
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

# Video categories: https://developers.google.com/youtube/v3/docs/videoCategories/list
YOUTUBE_CATEGORIES = {
    "Film & Animation": "1",
    "Autos & Vehicles": "2",
    "Music": "10",
    "Pets & Animals": "15",
    "Sports": "17",
    "Travel & Events": "19",
    "Gaming": "20",
    "People & Blogs": "22",
    "Comedy": "23",
    "Entertainment": "24",
    "News & Politics": "25",
    "Howto & Style": "26",
    "Education": "27",
    "Science & Technology": "28",
    "Nonprofits & Activism": "29",
}

# Privacy options
PRIVACY_OPTIONS = ["private", "unlisted", "public"]


class YouTubePoster:
    """Upload videos to YouTube using official API."""
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize YouTube Poster.
        
        Args:
            config_dir: Directory to store OAuth tokens. 
                        Defaults to same folder as config.json
        """
        if not HAS_YOUTUBE_API:
            raise ImportError("YouTube API libraries not installed")
        
        # Config directory (same as config.json location)
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # Use app directory or user's config folder
            self.config_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        
        self.token_path = self.config_dir / "youtube_token.pickle"
        self.credentials = None
        self.youtube_service = None
    
    def get_client_secrets_path(self) -> Optional[Path]:
        """Find client_secrets.json file."""
        possible_paths = [
            self.config_dir / "client_secrets.json",
            self.config_dir / "client_secret.json",
            Path("client_secrets.json"),
            Path("client_secret.json"),
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        return None
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        if self.credentials and self.credentials.valid:
            return True
        
        # Try to load saved token
        if self.token_path.exists():
            try:
                with open(self.token_path, 'rb') as token:
                    self.credentials = pickle.load(token)
                
                # Check if token is valid or can be refreshed
                if self.credentials.valid:
                    return True
                elif self.credentials.expired and self.credentials.refresh_token:
                    self.credentials.refresh(Request())
                    self._save_token()
                    return True
            except Exception as e:
                print(f"Error loading token: {e}")
        
        return False
    
    def authenticate(self, client_secrets_path: Optional[str] = None) -> bool:
        """
        Authenticate with YouTube using OAuth 2.0.
        Opens browser for user login if needed.
        
        Args:
            client_secrets_path: Path to client_secrets.json (optional if auto-detected)
        
        Returns:
            bool: True if authentication successful
        """
        # Check if already authenticated
        if self.is_authenticated():
            self._build_service()
            return True
        
        # Find client secrets file
        if client_secrets_path:
            secrets_path = Path(client_secrets_path)
        else:
            secrets_path = self.get_client_secrets_path()
        
        if not secrets_path or not secrets_path.exists():
            raise FileNotFoundError(
                "client_secrets.json not found. Please download from Google Cloud Console."
            )
        
        # Run OAuth flow
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(secrets_path),
                YOUTUBE_SCOPES
            )
            
            # Run local server for OAuth callback
            self.credentials = flow.run_local_server(
                port=8080,
                prompt='consent',
                authorization_prompt_message='Opening browser for YouTube authorization...'
            )
            
            # Save token for reuse
            self._save_token()
            
            # Build service
            self._build_service()
            
            return True
            
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False
    
    def _save_token(self):
        """Save OAuth token for reuse."""
        try:
            with open(self.token_path, 'wb') as token:
                pickle.dump(self.credentials, token)
        except Exception as e:
            print(f"Warning: Could not save token: {e}")
    
    def _build_service(self):
        """Build YouTube API service."""
        if self.credentials:
            self.youtube_service = build(
                'youtube', 'v3',
                credentials=self.credentials
            )
    
    def disconnect(self):
        """Remove saved credentials."""
        if self.token_path.exists():
            self.token_path.unlink()
        self.credentials = None
        self.youtube_service = None
    
    def auto_generate_thumbnail(self, video_path: str, timestamp: float = 2.5) -> str:
        """
        Auto-generate thumbnail from video frame at specified timestamp.
        Default 2.5 seconds = center of hook text (0-5s).
        
        Args:
            video_path: Path to video file
            timestamp: Time in seconds to extract frame (default 2.5 = hook center)
        
        Returns:
            Path to generated thumbnail (JPG) or empty string if failed
        """
        import subprocess
        from pathlib import Path
        
        video_file = Path(video_path)
        if not video_file.exists():
            return ""
        
        # Output path: same folder as video, with _thumb.jpg suffix
        thumb_path = video_file.with_suffix('.thumb.jpg')
        
        try:
            # Use ffmpeg to extract frame
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(timestamp),
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",
                str(thumb_path)
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            
            if thumb_path.exists():
                return str(thumb_path)
            else:
                return ""
                
        except Exception as e:
            print(f"Auto thumbnail failed: {e}")
            return ""
    
    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list = None,
        privacy: str = "private",
        made_for_kids: bool = False,
        notify_subscribers: bool = True,
        category: str = "Entertainment",
        schedule_datetime: str = None,  # ISO 8601 format: "2026-01-31T15:00:00Z"
        thumbnail_path: str = None,  # Path to thumbnail image (JPG/PNG)
        playlist_id: str = None,  # Playlist ID to add video to
        default_language: str = None,  # e.g., "id", "en"
        embeddable: bool = True,  # Allow embedding on other sites
        license_type: str = "youtube",  # "youtube" or "creativeCommon"
        contains_synthetic_media: bool = True  # AI-generated/altered content disclosure
    ) -> Dict[str, Any]:
        """
        Upload video to YouTube with full parameters.
        
        Args:
            video_path: Path to video file
            title: Video title (max 100 chars)
            description: Video description (max 5000 chars)
            tags: List of tags (total max 500 chars)
            privacy: "private", "unlisted", or "public"
            made_for_kids: True if made for children
            notify_subscribers: True to notify subscribers
            category: Category name (see YOUTUBE_CATEGORIES)
            schedule_datetime: Schedule publish time (ISO 8601, e.g., "2026-01-31T15:00:00Z")
            thumbnail_path: Path to custom thumbnail image
            playlist_id: Playlist ID to add video after upload
            default_language: Default language code (e.g., "id", "en")
            embeddable: Allow embedding on other websites
            license_type: "youtube" (standard) or "creativeCommon"
            contains_synthetic_media: True if AI-generated or digitally altered content (required disclosure)
        
        Returns:
            dict with video_id, video_url, status
        """
        if not self.youtube_service:
            if not self.authenticate():
                return {"error": "Not authenticated", "success": False}
        
        # Validate video file
        video_path = Path(video_path)
        if not video_path.exists():
            return {"error": f"Video not found: {video_path}", "success": False}
        
        # Truncate title if needed
        title = title[:100] if len(title) > 100 else title
        
        # Truncate description if needed
        description = description[:5000] if len(description) > 5000 else description
        
        # Process tags
        if tags is None:
            tags = []
        
        # Ensure total tag length <= 500 chars
        total_len = 0
        valid_tags = []
        for tag in tags:
            if total_len + len(tag) + 1 <= 500:
                valid_tags.append(tag)
                total_len += len(tag) + 1
            else:
                break
        
        # Get category ID
        category_id = YOUTUBE_CATEGORIES.get(category, "22")  # Default: People & Blogs
        
        # Validate privacy
        if privacy not in PRIVACY_OPTIONS:
            privacy = "private"
        
        # Build request body
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": valid_tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": made_for_kids,
                "embeddable": embeddable,
                "license": license_type,
                "containsSyntheticMedia": contains_synthetic_media,  # AI content disclosure
            }
        }
        
        # Add default language if specified
        if default_language:
            body["snippet"]["defaultLanguage"] = default_language
            body["snippet"]["defaultAudioLanguage"] = default_language
        
        # Handle scheduled publish (requires privacy = private initially)
        if schedule_datetime and privacy == "public":
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = schedule_datetime
        
        # Create media upload
        media = MediaFileUpload(
            str(video_path),
            mimetype='video/*',
            resumable=True,
            chunksize=1024*1024  # 1MB chunks
        )
        
        try:
            # Execute upload
            request = self.youtube_service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
                notifySubscribers=notify_subscribers
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"Upload progress: {int(status.progress() * 100)}%")
            
            video_id = response.get('id')
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            result = {
                "success": True,
                "video_id": video_id,
                "video_url": video_url,
                "title": title,
                "privacy": privacy,
                "scheduled": schedule_datetime is not None
            }
            
            # Upload custom thumbnail if provided
            if thumbnail_path and video_id:
                try:
                    thumb_path = Path(thumbnail_path)
                    if thumb_path.exists():
                        self.youtube_service.thumbnails().set(
                            videoId=video_id,
                            media_body=MediaFileUpload(str(thumb_path), mimetype='image/jpeg')
                        ).execute()
                        result["thumbnail"] = True
                except Exception as e:
                    result["thumbnail_error"] = str(e)
            
            # Add to playlist if specified
            if playlist_id and video_id:
                try:
                    self.youtube_service.playlistItems().insert(
                        part="snippet",
                        body={
                            "snippet": {
                                "playlistId": playlist_id,
                                "resourceId": {
                                    "kind": "youtube#video",
                                    "videoId": video_id
                                }
                            }
                        }
                    ).execute()
                    result["playlist_added"] = True
                except Exception as e:
                    result["playlist_error"] = str(e)
            
            return result
            
        except HttpError as e:
            error_msg = str(e)
            if "quotaExceeded" in error_msg:
                return {"error": "YouTube API quota exceeded. Try again tomorrow.", "success": False}
            elif "uploadLimitExceeded" in error_msg:
                return {"error": "Daily upload limit exceeded.", "success": False}
            else:
                return {"error": f"Upload failed: {error_msg}", "success": False}
        except Exception as e:
            return {"error": f"Upload error: {e}", "success": False}
    
    def get_channel_info(self) -> Optional[Dict[str, Any]]:
        """Get authenticated user's channel info."""
        if not self.youtube_service:
            return None
        
        try:
            response = self.youtube_service.channels().list(
                part="snippet",
                mine=True
            ).execute()
            
            if response.get('items'):
                channel = response['items'][0]
                return {
                    "channel_id": channel['id'],
                    "channel_name": channel['snippet']['title'],
                    "channel_url": f"https://www.youtube.com/channel/{channel['id']}"
                }
        except Exception as e:
            print(f"Error getting channel info: {e}")
        
        return None
    
    def get_playlists(self, max_results: int = 25) -> list:
        """Get user's playlists for selection dropdown."""
        if not self.youtube_service:
            if not self.authenticate():
                return []
        
        try:
            response = self.youtube_service.playlists().list(
                part="snippet",
                mine=True,
                maxResults=max_results
            ).execute()
            
            playlists = []
            for item in response.get('items', []):
                playlists.append({
                    "id": item['id'],
                    "title": item['snippet']['title']
                })
            return playlists
        except Exception as e:
            print(f"Error getting playlists: {e}")
            return []


def generate_youtube_caption(
    transcript: str,
    language: str = "id",
    gemini_api_key: str = None
) -> Dict[str, Any]:
    """
    Generate YouTube caption using Gemini AI.
    
    Args:
        transcript: Video transcript text
        language: Language code (id, en)
        gemini_api_key: Gemini API key
    
    Returns:
        dict with title, description, tags
    """
    try:
        import google.generativeai as genai
        
        if not gemini_api_key:
            return {"error": "Gemini API key required"}
        
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Truncate transcript
        transcript_preview = transcript[:2000] if len(transcript) > 2000 else transcript
        
        prompt = f"""Generate a viral YouTube Shorts caption based on this video transcript.

Transcript:
{transcript_preview}

Language: {"Indonesian" if language == "id" else "English"}

Requirements:
1. Title: Max 100 characters, clickbait style, use emoji
2. Description: Max 500 characters, engaging, include call-to-action (subscribe, like, comment)
3. Tags: 10-15 relevant tags for SEO, trending topics if applicable

Output ONLY valid JSON (no markdown, no explanation):
{{"title": "...", "description": "...", "tags": ["tag1", "tag2", ...]}}"""

        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Clean JSON if wrapped in markdown
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        text = text.strip()
        
        result = json.loads(text)
        return result
        
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse AI response: {e}"}
    except Exception as e:
        return {"error": f"Caption generation failed: {e}"}


# Convenience function
def upload_to_youtube(
    video_path: str,
    title: str,
    description: str = "",
    tags: list = None,
    privacy: str = "private",
    made_for_kids: bool = False
) -> Dict[str, Any]:
    """Quick upload function."""
    poster = YouTubePoster()
    return poster.upload_video(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        privacy=privacy,
        made_for_kids=made_for_kids
    )


if __name__ == "__main__":
    # Test authentication
    print("YouTube Poster - Test Mode")
    print("=" * 40)
    
    if not HAS_YOUTUBE_API:
        print("ERROR: Install required packages:")
        print("pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)
    
    poster = YouTubePoster()
    
    if poster.is_authenticated():
        print("✓ Already authenticated")
        info = poster.get_channel_info()
        if info:
            print(f"  Channel: {info['channel_name']}")
            print(f"  URL: {info['channel_url']}")
    else:
        print("Not authenticated. Run authenticate() to login.")
