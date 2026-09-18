cat > /Users/karthiksankaran/PS-Scripts/NarrativeAI/add_square_endpoints.py << 'PYEOF'
#!/usr/bin/env python3
"""Add Square payment endpoints to main.py"""

# Read main.py
with open('main.py', 'r') as f:
    content = f.read()

# Check if already added
if '@app.post("/api/square-payment")' in content:
    print('✅ Square endpoints already integrated')
    exit(0)

# Square payment endpoints to add
square_endpoints = '''
# ===== SQUARE PAYMENT ENDPOINTS =====

@app.get("/api/square-config")
async def square_config():
    """Get Square Web Payments SDK configuration"""
    return {
        "applicationId": SQUARE_APPLICATION_ID,
        "locationId": SQUARE_LOCATION_ID,
        "priceGBP": DOWNLOAD_PRICE_GBP,
        "priceUSD": DOWNLOAD_PRICE_GBP * 1.27,  # Approximate conversion
        "environment": SQUARE_ENVIRONMENT,
        "squareAvailable": SQUARE_AVAILABLE
    }

@app.post("/api/square-payment")
async def create_square_payment(request: Request):
    """Process payment using Square"""
    try:
        user_id = get_client_id(request)
        body = await request.json()
        source_id = body.get("sourceId")
        job_id = body.get("jobId")
        
        if not source_id or not job_id:
            raise HTTPException(400, "Missing sourceId or jobId")
        
        client = get_square_client()
        if not client:
            raise HTTPException(503, "Payment service unavailable")
        
        # Create payment
        payment_body = {
            "source_id": source_id,
            "amount_money": {
                "amount": int(DOWNLOAD_PRICE_GBP * 100),
                "currency": "GBP"
            },
            "currency": "GBP",
            "idempotency_key": str(uuid.uuid4()),
            "reference_id": job_id,
            "note": f"NarrativeAI: {job_id}",
            "autocomplete": True
        }
        
        result = client.payments.create_payment(payment_body)
        
        if result.is_success():
            payment_id = result.result['payment']['id']
            logger.info(f"✅ Payment successful: {payment_id} for job {job_id}")
            
            # Grant extra conversion
            today = get_today()
            paid_key = f"{user_id}:paid:{today}"
            with sessions_lock:
                sessions[paid_key] = sessions.get(paid_key, 0) + 1
                save_sessions_to_disk(sessions)
            
            return {
                "success": True,
                "paymentId": payment_id,
                "message": "Payment successful! You can now download your audiobook.",
                "extraConversions": 1
            }
        elif result.is_client_error():
            error_msg = str(result.errors) if result.errors else "Client error"
            logger.error(f"❌ Payment error: {error_msg}")
            raise HTTPException(400, f"Payment failed: {error_msg}")
        else:
            logger.error(f"❌ Server error: {result.errors}")
            raise HTTPException(500, "Payment processing error")
    
    except Exception as e:
        logger.error(f"❌ Square payment error: {e}")
        raise HTTPException(500, f"Payment error: {str(e)}")

@app.post("/api/payment-webhook")
async def payment_webhook(request: Request):
    """Handle Square webhook for payment events"""
    try:
        body = await request.json()
        event_type = body.get("type")
        
        if event_type == "payment.created":
            payment_id = body.get("data", {}).get("object", {}).get("payment", {}).get("id")
            logger.info(f"✅ Webhook: Payment created {payment_id}")
        
        return {"success": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"success": False, "error": str(e)}
'''

# Find insertion point (before @app.get("/", response_class=HTMLResponse))
insertion_point = content.find('@app.get("/", response_class=HTMLResponse)')
if insertion_point > 0:
    content = content[:insertion_point] + square_endpoints + "\n\n" + content[insertion_point:]
    
    # Write back
    with open('main.py', 'w') as f:
        f.write(content)
    
    print('✅ Square payment endpoints added to main.py')
else:
    print('❌ Could not find insertion point in main.py')
    exit(1)
PYEOF

python3 add_square_endpoints.py
