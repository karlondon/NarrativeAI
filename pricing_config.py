"""Pricing Tiers Configuration for NarrativeAI"""

PRICING_TIERS = {
    "audio_only": {
        "name": "🎵 Audio Only",
        "price": 1.00,
        "video": False,
        "description": "PDF to MP3"
    },
    "video_addon": {
        "name": "🎬 Audio + Video",
        "price": 5.00,
        "video": True,
        "description": "PDF to MP3 + AI Video"
    },
    "premium_bundle": {
        "name": "👑 Premium Bundle",
        "price": 8.00,
        "video": True,
        "description": "Monthly unlimited conversions"
    }
}

def is_valid_tier(tier_id):
    """Validate if tier exists"""
    return tier_id in PRICING_TIERS

def get_tier_info(tier_id):
    """Get tier information"""
    return PRICING_TIERS.get(tier_id, {})
