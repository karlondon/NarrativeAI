# Freemium Integration Routes for main.py
# Add these routes to your main.py FastAPI app

import hashlib, time, json
from fastapi import Request
from fastapi.responses import JSONResponse

FREE_CONVERSIONS_PER_DAY = 5
DOWNLOAD_PRICE_GBP = 1.0

def get_client_id(request: Request) -> str:
    """Create unique ID from user's IP + User Agent"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    raw = f"{client_ip}:{user_agent}"
    return hashlib.md5(raw.encode()).hexdigest()

def get_today() -> str:
    """Get today's date (resets daily at midnight UTC)"""
    return time.strftime("%Y-%m-%d", time.gmtime())

def check_free_tier(user_id: str, sessions: dict) -> tuple:
    """
    Check if user has free conversions left
    Returns: (is_free, used_today, remaining)
    """
    today =     today =     today =     today =     today =     today =ons.get(key, 0)
    remaining = max(0, FREE_CONVERSIONS_PER_DAY - used)
    return remaining > 0, used, remaining

def count_conversion(user_id: str, sessions: dict, session_file: Path):
    """Add 1 to user's daily conversion count"""
    today = get_today()
    key = f"{user_id}:{today}"
    sessions[key] = sessions.get(key, 0) + 1
    try:
        with open(session_file, 'w') as f:
            json.dump(sessions, f)
    except Exception as e:
        print(f"Error saving sessions: {e}")

# ROUTES TO ADD TO MAIN.PY:

# @app.get("/api/free-tier")
# async def free_tier_status(request: Request):
#     """Check user's free tier status"""
#     user_id = get_client_id(request)
#     is_free, used, remaining = check_free_tier(user_id, sessions)
#     
#     return {
#         "is_free_tier": is_free,
#         "used": used,
#         "remaining": remaining,
#         "limit": FREE_CONVERSIONS_PER_DAY
#     }

# Add this to your /upload endpoint:
# user_id = get_client_id(request)
# is_free, used, remaining = check_free_tier(user_id, sessions)
# 
# if not is_free:
#     return JSONResponse(
#         status_code=402,
#         content={
#             "error": "free_tier_exhausted",
#             "message": f"You've used all {FREE_CONVERSIONS_PER_DAY} free conversions today",
#             "used": used,
#             "limit": FREE_CONVERSIONS_PER_DAY,
#             "price_gbp": DOWNLOAD_PRICE_GBP
#         }
#     )
# 
# # After processing succeeds:
# count_conversion(user_id, sessions, SESSION_DB_FILE)
# logger.info(f"✅ Free conversion #{used+1}/{FREE_CONVERSIONS_PER_DAY} for user {user_id}")
