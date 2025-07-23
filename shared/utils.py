import hashlib
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from geopy.distance import geodesic
import re


def generate_random_string(length: int = 32) -> str:
    """Generate a random string of specified length."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_order_reference() -> str:
    """Generate a unique order reference."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    random_suffix = generate_random_string(6).upper()
    return f"OXY-{timestamp}-{random_suffix}"


def generate_payment_reference() -> str:
    """Generate a unique payment reference."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    random_suffix = generate_random_string(8).upper()
    return f"PAY-{timestamp}-{random_suffix}"


def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers."""
    point1 = (lat1, lon1)
    point2 = (lat2, lon2)
    return geodesic(point1, point2).kilometers


def calculate_delivery_eta(distance_km: float, traffic_factor: float = 1.2) -> int:
    """Calculate estimated delivery time in minutes."""
    # Base speed: 30 km/h in city, adjusted for traffic
    base_speed_kmh = 30
    adjusted_speed = base_speed_kmh / traffic_factor
    
    # Add buffer time for loading/unloading
    travel_time_minutes = (distance_km / adjusted_speed) * 60
    buffer_minutes = 15  # Loading/unloading time
    
    return int(travel_time_minutes + buffer_minutes)


def validate_phone_number(phone: str) -> bool:
    """Validate Nigerian phone number format."""
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone)
    
    # Check if it's a valid Nigerian number
    if len(digits_only) == 11 and digits_only.startswith(('070', '080', '081', '090', '091')):
        return True
    elif len(digits_only) == 14 and digits_only.startswith('234'):
        return True
    elif len(digits_only) == 13 and digits_only.startswith('234'):
        return True
    
    return False


def format_phone_number(phone: str) -> str:
    """Format phone number to international format."""
    digits_only = re.sub(r'\D', '', phone)
    
    if len(digits_only) == 11 and digits_only.startswith('0'):
        return f"+234{digits_only[1:]}"
    elif len(digits_only) == 10:
        return f"+234{digits_only}"
    elif len(digits_only) == 13 and digits_only.startswith('234'):
        return f"+{digits_only}"
    elif len(digits_only) == 14 and digits_only.startswith('234'):
        return f"+{digits_only}"
    
    return phone


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def calculate_platform_fee(amount: float, fee_percentage: float = 5.0) -> tuple:
    """Calculate platform fee and vendor amount."""
    platform_fee = (amount * fee_percentage) / 100
    vendor_amount = amount - platform_fee
    return platform_fee, vendor_amount


def generate_invoice_number() -> str:
    """Generate a unique invoice number."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    random_suffix = generate_random_string(4).upper()
    return f"INV-{timestamp}-{random_suffix}"


def is_within_business_hours(dt: Optional[datetime] = None) -> bool:
    """Check if given datetime is within business hours (8 AM - 6 PM)."""
    if dt is None:
        dt = datetime.utcnow()
    
    # Convert to Nigerian time (UTC+1)
    nigerian_time = dt + timedelta(hours=1)
    hour = nigerian_time.hour
    
    return 8 <= hour < 18


def calculate_emergency_surcharge(base_amount: float, is_emergency: bool = False) -> float:
    """Calculate emergency surcharge if applicable."""
    if is_emergency:
        return base_amount * 0.15  # 15% emergency surcharge
    return 0.0


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    # Remove or replace dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:255-len(ext)-1] + '.' + ext if ext else name[:255]
    
    return filename


def generate_verification_code(length: int = 6) -> str:
    """Generate numeric verification code."""
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def mask_sensitive_data(data: str, mask_char: str = '*', visible_chars: int = 4) -> str:
    """Mask sensitive data showing only last few characters."""
    if len(data) <= visible_chars:
        return mask_char * len(data)
    
    masked_length = len(data) - visible_chars
    return mask_char * masked_length + data[-visible_chars:]


def calculate_cylinder_weight(size: str) -> float:
    """Calculate cylinder weight in kg based on size."""
    weights = {
        "small": 15.0,    # 10L cylinder
        "medium": 25.0,   # 20L cylinder  
        "large": 45.0,    # 40L cylinder
        "extra_large": 55.0  # 50L cylinder
    }
    return weights.get(size, 25.0)


def estimate_delivery_cost(distance_km: float, cylinder_count: int, is_emergency: bool = False) -> float:
    """Estimate delivery cost based on distance and cylinder count."""
    base_cost = 2000.0  # Base delivery cost in Naira
    distance_cost = distance_km * 50.0  # 50 Naira per km
    cylinder_cost = (cylinder_count - 1) * 500.0  # Additional cost per extra cylinder
    
    total_cost = base_cost + distance_cost + cylinder_cost
    
    if is_emergency:
        total_cost *= 1.5  # 50% surcharge for emergency deliveries
    
    return round(total_cost, 2)


def validate_coordinates(latitude: float, longitude: float) -> bool:
    """Validate if coordinates are within Nigeria's boundaries."""
    # Nigeria's approximate boundaries
    nigeria_bounds = {
        'min_lat': 4.0,
        'max_lat': 14.0,
        'min_lon': 2.5,
        'max_lon': 15.0
    }
    
    return (nigeria_bounds['min_lat'] <= latitude <= nigeria_bounds['max_lat'] and
            nigeria_bounds['min_lon'] <= longitude <= nigeria_bounds['max_lon'])


def format_currency(amount: float, currency: str = "NGN") -> str:
    """Format currency amount for display."""
    if currency == "NGN":
        return f"₦{amount:,.2f}"
    else:
        return f"{currency} {amount:,.2f}"


def get_cylinder_capacity(size: str) -> int:
    """Get cylinder capacity in liters."""
    capacities = {
        "small": 10,
        "medium": 20,
        "large": 40,
        "extra_large": 50
    }
    return capacities.get(size, 20)
