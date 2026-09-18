# Complete Square Payment Integration Routes
# Add these to your main.py after the blog routes

import uuid as uuid_lib
from squareup.client import Client
from squareup.api.payments_api import PaymentsApi

# ===== SQUARE PAYMENT ENDPOINTS =====

@app.post("/api/square-payment")
async def create_square_payment(request: Request, data: dict):
    """
    Create a payment using Square Web Payments SDK
    Expects: { "sourceId": "...", "jobId": "..." }
    """
    try:
        user_id = get_client_id(request)
        source_id = data.get("sourceId")
        job_id = data.get("jobId")
        
        if not source_id or not job_id:
            raise HTTPException(400, "Missing sourceId or jobId")
        
        # Initialize Square client
        client = Client(
            access_token=os.getenv('SQUARE_ACCESS_TOKEN'),
            environment=os.getenv('SQUARE_ENVIRONMENT', 'production')
        )
        
        # Create payment
        payments_api = client.payments
        
        amount_money = {
            "amount": int(DOWNLOAD_PRICE_GBP * 100),  # Convert £1 to 100 pence
            "currency": "GBP"
        }
        
        payment_body = {
            "source_id": source_id,
            "amount_money": amount_money,
            "currency": "GBP",
            "idempotency_key": str(uuid_lib.uuid4()),
            "reference_id": job_id,
            "note": f"PDF to Audiobook: {job_id}",
            "customer_id": None
        }
        
        result = payments_api.create_payment(payment_body)
        
        if result.is_success():
            logger.info(f"✅ Payment successful for job {job_id}")
            return {
                "success": True,
                "payment_id": result.result['payment']['id'],
                "amount": DOWNLOAD_PRICE_GBP,
                "currency": "GBP"
            }
        elif result.is_client_error():
            logger.error(f"❌ Payment error: {result.errors}")
            raise HTTPException(400, f"Payment failed: {result.errors}")
        else:
            logger.error(f"❌ Server error: {result.errors}")
            raise HTTPException(500, "Payment processing error")
    
    except Exception as e:
        logger.error(f"❌ Square payment error: {e}")
        raise HTTPException(500, f"Payment error: {str(e)}")

@app.get("/api/square-config")
async def square_config():
    """Get Square Web Payments SDK configuration"""
    return {
        "applicationId": os.getenv('SQUARE_APPLICATION_ID'),
        "locationId": os.getenv('SQUARE_LOCATION_ID'),
        "priceGBP": DOWNLOAD_PRICE_GBP,
        "environment": os.getenv('SQUARE_ENVIRONMENT', 'production')
    }

@app.post("/api/payment-success")
async def payment_success(request: Request, data: dict):
    """Handle successful payment - allow extra conversion"""
    try:
        user_id = get_client_id(request)
        payment_id = data.get("paymentId")
        job_id = data.get("jobId")
        
        if not payment_id:
            raise HTTPException(400, "Missing paymentId")
        
        # Grant one extra conversion for this user
        today = get_today()
        key = f"{user_id}:paid:{today}"
        
        with sessions_lock:
            sessions[key] = sessions.get(key, 0) + 1
            save_sessions_to_disk(sessions)
        
        logger.info(f"✅ Payment recorded: User {user_id[:8]}... gained 1 extra conversion")
        
        return {
            "success": True,
            "message": "Payment recorded. You can now download your audiobook!",
            "extraConversions": 1
        }
    except Exception as e:
        logger.error(f"❌ Payment success handler error: {e}")
        raise HTTPException(500, str(e))
