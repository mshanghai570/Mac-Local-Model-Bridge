from local_ai_gateway.auth import *

def mask_api_key(key):
    if not key:
        return "<none>"
    if len(key) <= 6:
        return "***"
    return f"{key[:2]}***{key[-2:]}"
