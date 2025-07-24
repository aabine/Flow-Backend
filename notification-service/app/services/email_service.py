import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional, Dict, Any
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from app.core.config import get_settings

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        settings = get_settings()
        self.smtp_server = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_use_tls = True  # Default to True since we're using port 587
        self.smtp_from_email = settings.SMTP_USERNAME  # Use the username as from email if not specified
        self.smtp_from_name = "Oxygen Supply Platform"  # Default from name
        
        # Set up template environment
        template_path = Path(__file__).parent.parent / "templates" / "emails"
        self.template_env = Environment(
            loader=FileSystemLoader(template_path),
            autoescape=True
        )
        
        # Configure SMTP connection
        self.smtp_connection = None
    
    async def connect(self):
        """Establish SMTP connection."""
        try:
            self.smtp_connection = smtplib.SMTP(self.smtp_server, self.smtp_port)
            if self.smtp_use_tls:
                self.smtp_connection.starttls()
            if self.smtp_username and self.smtp_password:
                self.smtp_connection.login(self.smtp_username, self.smtp_password)
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            return False
    
    async def disconnect(self):
        """Close SMTP connection."""
        if self.smtp_connection:
            try:
                self.smtp_connection.quit()
            except Exception as e:
                logger.error(f"Error disconnecting from SMTP server: {e}")
            finally:
                self.smtp_connection = None
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str = None,
        text_content: str = None,
        template_name: str = None,
        template_context: Dict[str, Any] = None,
        from_email: str = None,
        from_name: str = None,
        reply_to: str = None,
        cc: List[str] = None,
        bcc: List[str] = None,
        attachments: List[Dict[str, Any]] = None
    ) -> bool:
        """
        Send an email with the given parameters.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text content of the email (fallback for non-HTML clients)
            template_name: Name of the template to use (without extension)
            template_context: Context variables for the template
            from_email: Sender email address (defaults to SMTP_FROM_EMAIL)
            from_name: Sender name (defaults to SMTP_FROM_NAME)
            reply_to: Reply-to email address
            cc: List of CC email addresses
            bcc: List of BCC email addresses
            attachments: List of attachments (each with 'filename' and 'content')
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        if not to_email:
            logger.error("No recipient email address provided")
            return False
        
        # Prepare email message
        from_email = from_email or self.smtp_from_email
        from_name = from_name or self.smtp_from_name
        
        # Create message container
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f'"{from_name}" <{from_email}>' if from_name else from_email
        msg['To'] = to_email
        
        if reply_to:
            msg['Reply-To'] = reply_to
        if cc:
            msg['Cc'] = ', '.join(cc)
        if bcc:
            msg['Bcc'] = ', '.join(bcc)
        
        # Render template if provided
        if template_name and not (html_content or text_content):
            try:
                # Try to load HTML template
                html_template = self.template_env.get_template(f"{template_name}.html")
                html_content = html_template.render(**(template_context or {}))
                
                # Try to load text template if it exists, otherwise use HTML with tags stripped
                try:
                    text_template = self.template_env.get_template(f"{template_name}.txt")
                    text_content = text_template.render(**(template_context or {}))
                except Exception:
                    # Fallback: strip HTML tags for text version
                    import re
                    text_content = re.sub(r'<[^>]+>', ' ', html_content)
                    text_content = re.sub(r'\s+', ' ', text_content).strip()
            except Exception as e:
                logger.error(f"Failed to render email template {template_name}: {e}")
                return False
        
        # Attach message parts
        if text_content:
            msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
        if html_content:
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        
        # Handle attachments
        if attachments:
            from email.mime.base import MIMEBase
            from email import encoders
            
            for attachment in attachments:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment['content'])
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{attachment["filename"]}"'
                )
                msg.attach(part)
        
        # Connect to SMTP server if not already connected
        if not self.smtp_connection:
            if not await self.connect():
                return False
        
        # Send the email
        try:
            recipients = [to_email]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)
            
            self.smtp_connection.send_message(
                from_addr=from_email,
                to_addrs=recipients,
                msg=msg
            )
            logger.info(f"Email sent to {to_email} with subject: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    async def send_template_email(
        self,
        to_email: str,
        template_name: str,
        template_context: Dict[str, Any],
        subject: str = None,
        **kwargs
    ) -> bool:
        """
        Send an email using a template.
        
        Args:
            to_email: Recipient email address
            template_name: Name of the template (without extension)
            template_context: Context variables for the template
            subject: Email subject (if None, will be taken from template context)
            **kwargs: Additional arguments to pass to send_email
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        subject = subject or template_context.get('subject', 'Notification')
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            template_name=template_name,
            template_context=template_context,
            **kwargs
        )

# Create a singleton instance
email_service = EmailService()
