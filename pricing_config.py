"""Pricing Tiers Configuration for NarrativeAI - Audio Only Mode"""

PRICING_TIERS = {
    "audio_only": {
        "name": "🎵 Audio Only",
        "price": 1.00,
        "description": "PDF to MP3 Conversion"
    }
}

def is_valid_tier(tier_id):
    """Validate if tier exists"""
    return tier_id in PRICING_TIERS

def get_tier_info(tier_id):
    """Get tier information"""
    return PRICING_TIERS.get(tier_id, {})

