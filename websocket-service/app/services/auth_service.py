from typing import Optional, Dict, Any
from jose import JWTError, jwt
import httpx
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import settings


class AuthService:
    def __init__(self):
        self.user_service_url = settings.USER_SERVICE_URL
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token with User Service."""
        try:
            # First try to decode locally
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            
            # Verify with user service
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.user_service_url}/auth/verify-token",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code == 200:
                    user_data = response.json()
                    return {
                        "user_id": user_data.get("user_id"),
                        "email": user_data.get("email"),
                        "role": user_data.get("role"),
                        "valid": True
                    }
        
        except JWTError:
            pass
        except Exception as e:
            print(f"Token verification error: {e}")
        
        return None
    
    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information from User Service."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.user_service_url}/users/{user_id}"
                )
                
                if response.status_code == 200:
                    return response.json()
        
        except Exception as e:
            print(f"Failed to get user info: {e}")
        
        return None
