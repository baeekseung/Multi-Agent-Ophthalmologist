from datetime import datetime

def get_current_time() -> str:
    """Get current date in a human-readable format."""
    return datetime.now().strftime("%b %-d, %Y %H:%M:%S (%A)")