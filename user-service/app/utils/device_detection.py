"""
Device detection utilities for session management.
Parses user agent strings to identify device types and browsers.
"""

import re
from typing import Dict, Optional


class DeviceDetector:
    """Device and browser detection from user agent strings."""
    
    # Browser patterns
    BROWSER_PATTERNS = {
        'Chrome': r'Chrome/(\d+)',
        'Firefox': r'Firefox/(\d+)',
        'Safari': r'Safari/(\d+)',
        'Edge': r'Edg/(\d+)',
        'Opera': r'Opera/(\d+)',
        'Internet Explorer': r'MSIE (\d+)',
    }
    
    # Operating system patterns
    OS_PATTERNS = {
        'Windows': r'Windows NT (\d+\.\d+)',
        'macOS': r'Mac OS X (\d+[._]\d+)',
        'Linux': r'Linux',
        'Android': r'Android (\d+)',
        'iOS': r'OS (\d+[._]\d+)',
    }
    
    # Device type patterns
    DEVICE_PATTERNS = {
        'Mobile': r'Mobile|Android|iPhone',
        'Tablet': r'Tablet|iPad',
        'Desktop': r'Windows|Macintosh|Linux',
    }
    
    @classmethod
    def parse_user_agent(cls, user_agent: str) -> Dict[str, Optional[str]]:
        """
        Parse user agent string to extract device information.
        Returns dict with browser, os, device_type, and version info.
        """
        if not user_agent:
            return {
                'browser': 'Unknown',
                'browser_version': None,
                'os': 'Unknown',
                'os_version': None,
                'device_type': 'Unknown',
                'is_mobile': False,
                'is_bot': False
            }
        
        result = {
            'browser': 'Unknown',
            'browser_version': None,
            'os': 'Unknown',
            'os_version': None,
            'device_type': 'Desktop',  # Default to desktop
            'is_mobile': False,
            'is_bot': False
        }
        
        # Check if it's a bot
        bot_patterns = [
            r'bot', r'crawler', r'spider', r'scraper',
            r'Googlebot', r'Bingbot', r'facebookexternalhit'
        ]
        
        for pattern in bot_patterns:
            if re.search(pattern, user_agent, re.IGNORECASE):
                result['is_bot'] = True
                result['browser'] = 'Bot'
                return result
        
        # Detect browser
        for browser, pattern in cls.BROWSER_PATTERNS.items():
            match = re.search(pattern, user_agent)
            if match:
                result['browser'] = browser
                result['browser_version'] = match.group(1)
                break
        
        # Detect operating system
        for os_name, pattern in cls.OS_PATTERNS.items():
            match = re.search(pattern, user_agent)
            if match:
                result['os'] = os_name
                if len(match.groups()) > 0:
                    result['os_version'] = match.group(1).replace('_', '.')
                break
        
        # Detect device type
        for device_type, pattern in cls.DEVICE_PATTERNS.items():
            if re.search(pattern, user_agent, re.IGNORECASE):
                result['device_type'] = device_type
                break
        
        # Set mobile flag
        result['is_mobile'] = result['device_type'] in ['Mobile', 'Tablet']
        
        return result
    
    @classmethod
    def get_device_description(cls, user_agent: str) -> str:
        """
        Get a human-readable device description.
        Example: "Chrome 91 on Windows 10" or "Safari on iPhone"
        """
        info = cls.parse_user_agent(user_agent)
        
        if info['is_bot']:
            return "Bot/Crawler"
        
        parts = []
        
        # Add browser info
        if info['browser'] != 'Unknown':
            browser_part = info['browser']
            if info['browser_version']:
                browser_part += f" {info['browser_version']}"
            parts.append(browser_part)
        
        # Add OS info
        if info['os'] != 'Unknown':
            os_part = info['os']
            if info['os_version']:
                # Simplify version for common OS
                if info['os'] == 'Windows':
                    version_map = {
                        '10.0': '10',
                        '6.3': '8.1',
                        '6.2': '8',
                        '6.1': '7'
                    }
                    os_part += f" {version_map.get(info['os_version'], info['os_version'])}"
                elif info['os'] == 'macOS':
                    os_part = f"macOS {info['os_version']}"
                else:
                    os_part += f" {info['os_version']}"
            parts.append(os_part)
        
        if parts:
            description = " on ".join(parts)
        else:
            description = "Unknown Device"
        
        # Add device type indicator for mobile
        if info['is_mobile']:
            description += f" ({info['device_type']})"
        
        return description
    
    @classmethod
    def get_device_icon(cls, user_agent: str) -> str:
        """
        Get an appropriate icon/emoji for the device type.
        """
        info = cls.parse_user_agent(user_agent)
        
        if info['is_bot']:
            return "🤖"
        
        if info['device_type'] == 'Mobile':
            return "📱"
        elif info['device_type'] == 'Tablet':
            return "📱"  # Could use tablet emoji if available
        else:
            # Desktop - differentiate by OS
            if info['os'] == 'Windows':
                return "🖥️"
            elif info['os'] == 'macOS':
                return "💻"
            elif info['os'] == 'Linux':
                return "🐧"
            else:
                return "💻"
    
    @classmethod
    def is_suspicious_user_agent(cls, user_agent: str) -> bool:
        """
        Check if user agent might be suspicious or automated.
        """
        if not user_agent:
            return True
        
        # Very short user agents are suspicious
        if len(user_agent) < 20:
            return True
        
        # Check for common automation tools
        suspicious_patterns = [
            r'curl', r'wget', r'python', r'requests',
            r'postman', r'insomnia', r'httpie',
            r'automation', r'selenium', r'phantomjs'
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, user_agent, re.IGNORECASE):
                return True
        
        return False


# Utility functions
def get_device_info(user_agent: str) -> Dict[str, str]:
    """Get device information for session display."""
    detector = DeviceDetector()
    info = detector.parse_user_agent(user_agent)
    
    return {
        'description': detector.get_device_description(user_agent),
        'icon': detector.get_device_icon(user_agent),
        'device_type': info['device_type'],
        'browser': info['browser'],
        'os': info['os'],
        'is_mobile': info['is_mobile'],
        'is_suspicious': detector.is_suspicious_user_agent(user_agent)
    }


def format_session_info(session_data: dict, user_agent: str = None) -> dict:
    """Format session information for display."""
    device_info = get_device_info(user_agent or "")
    
    return {
        **session_data,
        'device_description': device_info['description'],
        'device_icon': device_info['icon'],
        'device_type': device_info['device_type'],
        'is_mobile': device_info['is_mobile'],
        'is_suspicious': device_info['is_suspicious']
    }
