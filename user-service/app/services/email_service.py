"""
Email verification service with secure token generation and email sending.
Implements email verification flow for new user accounts.
"""

import secrets
import hashlib
import smtplib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.user import User, EmailVerificationToken
from app.core.config import get_settings

settings = get_settings()


class EmailVerificationToken:
    """Email verification token model (stored in database)."""
    
    def __init__(self, user_id: str, token_hash: str, expires_at: datetime):
        self.user_id = user_id
        self.token_hash = token_hash
        self.expires_at = expires_at
        self.created_at = datetime.utcnow()
        self.used_at = None


class EmailService:
    """Email verification and notification service."""
    
    def __init__(self):
        self.smtp_server = getattr(settings, 'SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = getattr(settings, 'SMTP_PORT', 587)
        self.smtp_username = getattr(settings, 'SMTP_USERNAME', '')
        self.smtp_password = getattr(settings, 'SMTP_PASSWORD', '')
        self.from_email = getattr(settings, 'FROM_EMAIL', 'noreply@oxygen-platform.com')
        self.frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        
        # Token expiry (24 hours)
        self.token_expire_hours = 24
    
    def generate_verification_token(self) -> tuple[str, str]:
        """
        Generate secure email verification token.
        Returns (token, token_hash) tuple.
        """
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token, token_hash
    
    async def create_verification_token(
        self,
        db: AsyncSession,
        user_id: str,
        ip_address: str = None
    ) -> str:
        """Create and store email verification token."""

        # Generate token
        token, token_hash = self.generate_verification_token()
        expires_at = datetime.utcnow() + timedelta(hours=self.token_expire_hours)

        # Store in database
        verification_token = EmailVerificationToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            ip_address=ip_address
        )

        db.add(verification_token)
        await db.commit()

        return token
    
    async def verify_email_token(
        self,
        db: AsyncSession,
        token: str
    ) -> Optional[str]:
        """
        Verify email verification token.
        Returns user_id if valid, None if invalid/expired.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Query for valid token
        result = await db.execute(
            select(EmailVerificationToken).filter(
                and_(
                    EmailVerificationToken.token_hash == token_hash,
                    EmailVerificationToken.expires_at > datetime.utcnow(),
                    EmailVerificationToken.used_at.is_(None)
                )
            )
        )

        verification_token = result.scalar_one_or_none()
        if not verification_token:
            return None

        return str(verification_token.user_id)

    async def mark_email_token_used(self, db: AsyncSession, token: str) -> bool:
        """Mark email verification token as used."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        result = await db.execute(
            select(EmailVerificationToken).filter(
                EmailVerificationToken.token_hash == token_hash
            )
        )

        verification_token = result.scalar_one_or_none()
        if verification_token:
            verification_token.used_at = datetime.utcnow()
            await db.commit()
            return True

        return False
    
    def create_verification_email(self, email: str, token: str, user_name: str = None) -> MIMEMultipart:
        """Create email verification email."""
        
        verification_url = f"{self.frontend_url}/verify-email?token={token}"
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Verify Your Email - Oxygen Supply Platform"
        msg['From'] = self.from_email
        msg['To'] = email
        
        # Create text version
        text_content = f"""
        Welcome to Oxygen Supply Platform!
        
        Please verify your email address by clicking the link below:
        {verification_url}
        
        This link will expire in {self.token_expire_hours} hours.
        
        If you didn't create an account, please ignore this email.
        
        Best regards,
        Oxygen Supply Platform Team
        """
        
        # Create HTML version
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Email Verification</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .button {{ 
                    display: inline-block; 
                    padding: 12px 24px; 
                    background-color: #28a745; 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    margin: 20px 0;
                }}
                .footer {{ padding: 20px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to Oxygen Supply Platform</h1>
                </div>
                <div class="content">
                    <h2>Verify Your Email Address</h2>
                    <p>Hello{' ' + user_name if user_name else ''},</p>
                    <p>Thank you for registering with Oxygen Supply Platform. To complete your registration, please verify your email address by clicking the button below:</p>
                    
                    <a href="{verification_url}" class="button">Verify Email Address</a>
                    
                    <p>Or copy and paste this link into your browser:</p>
                    <p><a href="{verification_url}">{verification_url}</a></p>
                    
                    <p><strong>This link will expire in {self.token_expire_hours} hours.</strong></p>
                    
                    <p>If you didn't create an account with us, please ignore this email.</p>
                </div>
                <div class="footer">
                    <p>© 2024 Oxygen Supply Platform. All rights reserved.</p>
                    <p>This is an automated message, please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Attach parts
        text_part = MIMEText(text_content, 'plain')
        html_part = MIMEText(html_content, 'html')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        return msg
    
    def create_password_reset_email(self, email: str, token: str, user_name: str = None) -> MIMEMultipart:
        """Create password reset email."""
        
        reset_url = f"{self.frontend_url}/reset-password?token={token}"
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Password Reset - Oxygen Supply Platform"
        msg['From'] = self.from_email
        msg['To'] = email
        
        # Create text version
        text_content = f"""
        Password Reset Request
        
        We received a request to reset your password for your Oxygen Supply Platform account.
        
        Click the link below to reset your password:
        {reset_url}
        
        This link will expire in 15 minutes.
        
        If you didn't request a password reset, please ignore this email.
        
        Best regards,
        Oxygen Supply Platform Team
        """
        
        # Create HTML version
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Password Reset</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #dc3545; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .button {{ 
                    display: inline-block; 
                    padding: 12px 24px; 
                    background-color: #dc3545; 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    margin: 20px 0;
                }}
                .footer {{ padding: 20px; text-align: center; color: #666; font-size: 12px; }}
                .warning {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Password Reset Request</h1>
                </div>
                <div class="content">
                    <h2>Reset Your Password</h2>
                    <p>Hello{' ' + user_name if user_name else ''},</p>
                    <p>We received a request to reset your password for your Oxygen Supply Platform account.</p>
                    
                    <a href="{reset_url}" class="button">Reset Password</a>
                    
                    <p>Or copy and paste this link into your browser:</p>
                    <p><a href="{reset_url}">{reset_url}</a></p>
                    
                    <div class="warning">
                        <p><strong>⚠️ Important:</strong> This link will expire in 15 minutes for security reasons.</p>
                    </div>
                    
                    <p>If you didn't request a password reset, please ignore this email. Your password will remain unchanged.</p>
                </div>
                <div class="footer">
                    <p>© 2024 Oxygen Supply Platform. All rights reserved.</p>
                    <p>This is an automated message, please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Attach parts
        text_part = MIMEText(text_content, 'plain')
        html_part = MIMEText(html_content, 'html')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        return msg
    
    async def send_email(self, msg: MIMEMultipart) -> bool:
        """Send email via SMTP."""
        try:
            # Skip actual email sending in development
            if not self.smtp_username or not self.smtp_password:
                print(f"📧 Email would be sent to: {msg['To']}")
                print(f"📧 Subject: {msg['Subject']}")
                print("📧 Email sending skipped (no SMTP credentials)")
                return True
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            print(f"📧 Email sent successfully to: {msg['To']}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send email: {str(e)}")
            return False
    
    async def send_verification_email(
        self, 
        db: AsyncSession, 
        user_id: str, 
        email: str, 
        user_name: str = None
    ) -> bool:
        """Send email verification email."""
        try:
            # Generate verification token
            token = await self.create_verification_token(db, user_id)
            
            # Create email
            msg = self.create_verification_email(email, token, user_name)
            
            # Send email
            return await self.send_email(msg)
            
        except Exception as e:
            print(f"❌ Failed to send verification email: {str(e)}")
            return False
    
    async def send_password_reset_email(
        self, 
        email: str, 
        token: str, 
        user_name: str = None
    ) -> bool:
        """Send password reset email."""
        try:
            # Create email
            msg = self.create_password_reset_email(email, token, user_name)
            
            # Send email
            return await self.send_email(msg)
            
        except Exception as e:
            print(f"❌ Failed to send password reset email: {str(e)}")
            return False


# Global email service instance
email_service = EmailService()
