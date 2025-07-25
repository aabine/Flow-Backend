"""
OAuth service for social login integration.
Implements Google and Facebook OAuth authentication flows.
"""

import httpx
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.user import User, UserProfile
from app.core.config import get_settings
from shared.models import UserRole

settings = get_settings()


class OAuthProvider:
    """OAuth provider configuration."""
    
    GOOGLE = "google"
    FACEBOOK = "facebook"


class OAuthConfig:
    """OAuth configuration settings."""
    
    # Google OAuth
    GOOGLE_CLIENT_ID = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
    GOOGLE_REDIRECT_URI = getattr(settings, 'GOOGLE_REDIRECT_URI', 'http://localhost:3000/auth/google/callback')
    
    # Facebook OAuth
    FACEBOOK_APP_ID = getattr(settings, 'FACEBOOK_APP_ID', '')
    FACEBOOK_APP_SECRET = getattr(settings, 'FACEBOOK_APP_SECRET', '')
    FACEBOOK_REDIRECT_URI = getattr(settings, 'FACEBOOK_REDIRECT_URI', 'http://localhost:3000/auth/facebook/callback')
    
    # OAuth URLs
    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    
    FACEBOOK_AUTH_URL = "https://www.facebook.com/v18.0/dialog/oauth"
    FACEBOOK_TOKEN_URL = "https://graph.facebook.com/v18.0/oauth/access_token"
    FACEBOOK_USER_INFO_URL = "https://graph.facebook.com/v18.0/me"


class OAuthService:
    """OAuth authentication service."""
    
    def __init__(self):
        self.config = OAuthConfig()
        self.state_expiry_minutes = 10
    
    def generate_oauth_state(self) -> str:
        """Generate secure state parameter for OAuth flow."""
        return secrets.token_urlsafe(32)
    
    def get_google_auth_url(self, state: str, role: str = None) -> str:
        """Generate Google OAuth authorization URL."""
        
        scopes = ["openid", "email", "profile"]
        scope_string = " ".join(scopes)
        
        params = {
            "client_id": self.config.GOOGLE_CLIENT_ID,
            "redirect_uri": self.config.GOOGLE_REDIRECT_URI,
            "scope": scope_string,
            "response_type": "code",
            "state": f"{state}:{role}" if role else state,
            "access_type": "offline",
            "prompt": "consent"
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.config.GOOGLE_AUTH_URL}?{query_string}"
    
    def get_facebook_auth_url(self, state: str, role: str = None) -> str:
        """Generate Facebook OAuth authorization URL."""
        
        scopes = ["email", "public_profile"]
        scope_string = ",".join(scopes)
        
        params = {
            "client_id": self.config.FACEBOOK_APP_ID,
            "redirect_uri": self.config.FACEBOOK_REDIRECT_URI,
            "scope": scope_string,
            "response_type": "code",
            "state": f"{state}:{role}" if role else state
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.config.FACEBOOK_AUTH_URL}?{query_string}"
    
    async def exchange_google_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange Google authorization code for access token."""
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.config.GOOGLE_TOKEN_URL,
                    data={
                        "client_id": self.config.GOOGLE_CLIENT_ID,
                        "client_secret": self.config.GOOGLE_CLIENT_SECRET,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": self.config.GOOGLE_REDIRECT_URI
                    },
                    headers={"Accept": "application/json"}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"Google token exchange failed: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"Error exchanging Google code: {e}")
            return None
    
    async def exchange_facebook_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange Facebook authorization code for access token."""
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.config.FACEBOOK_TOKEN_URL,
                    params={
                        "client_id": self.config.FACEBOOK_APP_ID,
                        "client_secret": self.config.FACEBOOK_APP_SECRET,
                        "code": code,
                        "redirect_uri": self.config.FACEBOOK_REDIRECT_URI
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"Facebook token exchange failed: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"Error exchanging Facebook code: {e}")
            return None
    
    async def get_google_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get user information from Google."""
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.config.GOOGLE_USER_INFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"Google user info failed: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"Error getting Google user info: {e}")
            return None
    
    async def get_facebook_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get user information from Facebook."""
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.config.FACEBOOK_USER_INFO_URL,
                    params={
                        "access_token": access_token,
                        "fields": "id,name,email,first_name,last_name,picture"
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"Facebook user info failed: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"Error getting Facebook user info: {e}")
            return None
    
    async def authenticate_with_google(
        self,
        db: AsyncSession,
        code: str,
        role: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Complete Google OAuth authentication."""
        
        # Exchange code for token
        token_data = await self.exchange_google_code(code)
        if not token_data or "access_token" not in token_data:
            return None
        
        # Get user info
        user_info = await self.get_google_user_info(token_data["access_token"])
        if not user_info or "email" not in user_info:
            return None
        
        # Find or create user
        user = await self._find_or_create_oauth_user(
            db, user_info, OAuthProvider.GOOGLE, role
        )
        
        return {
            "user": user,
            "oauth_provider": OAuthProvider.GOOGLE,
            "oauth_user_info": user_info
        }
    
    async def authenticate_with_facebook(
        self,
        db: AsyncSession,
        code: str,
        role: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Complete Facebook OAuth authentication."""
        
        # Exchange code for token
        token_data = await self.exchange_facebook_code(code)
        if not token_data or "access_token" not in token_data:
            return None
        
        # Get user info
        user_info = await self.get_facebook_user_info(token_data["access_token"])
        if not user_info or "email" not in user_info:
            return None
        
        # Find or create user
        user = await self._find_or_create_oauth_user(
            db, user_info, OAuthProvider.FACEBOOK, role
        )
        
        return {
            "user": user,
            "oauth_provider": OAuthProvider.FACEBOOK,
            "oauth_user_info": user_info
        }
    
    async def _find_or_create_oauth_user(
        self,
        db: AsyncSession,
        oauth_user_info: Dict[str, Any],
        provider: str,
        role: Optional[str] = None
    ) -> User:
        """Find existing user or create new user from OAuth info."""
        
        email = oauth_user_info.get("email")
        if not email:
            raise ValueError("Email not provided by OAuth provider")
        
        # Try to find existing user
        result = await db.execute(
            select(User).filter(User.email == email)
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Update last login
            user.last_login = datetime.utcnow()
            await db.commit()
            return user
        
        # Create new user
        user_role = UserRole.HOSPITAL  # Default role
        if role:
            try:
                user_role = UserRole(role)
            except ValueError:
                pass  # Use default if invalid role
        
        # Generate a random password (user won't use it for OAuth login)
        random_password = secrets.token_urlsafe(32)
        
        from app.services.password_service import password_service
        password_hash = password_service.hash_password(random_password)
        
        # Create user
        new_user = User(
            email=email,
            password_hash=password_hash,
            role=user_role,
            is_active=True,
            email_verified=True,  # OAuth emails are considered verified
            created_at=datetime.utcnow(),
            last_login=datetime.utcnow()
        )
        
        db.add(new_user)
        await db.flush()  # Get the user ID
        
        # Create user profile
        first_name = oauth_user_info.get("given_name") or oauth_user_info.get("first_name") or ""
        last_name = oauth_user_info.get("family_name") or oauth_user_info.get("last_name") or ""
        
        # Handle Facebook name format
        if not first_name and not last_name:
            full_name = oauth_user_info.get("name", "")
            name_parts = full_name.split(" ", 1)
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""
        
        # Get profile picture URL
        avatar_url = None
        if provider == OAuthProvider.GOOGLE:
            avatar_url = oauth_user_info.get("picture")
        elif provider == OAuthProvider.FACEBOOK:
            picture_data = oauth_user_info.get("picture", {})
            if isinstance(picture_data, dict):
                avatar_url = picture_data.get("data", {}).get("url")
        
        profile = UserProfile(
            user_id=new_user.id,
            first_name=first_name,
            last_name=last_name,
            avatar_url=avatar_url,
            created_at=datetime.utcnow()
        )
        
        db.add(profile)
        await db.commit()
        await db.refresh(new_user)
        
        return new_user


# Global OAuth service instance
oauth_service = OAuthService()
