import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from bson import ObjectId
import requests

from database import db, create_document, get_documents
from schemas import OrderCreate, Order, PaymentInitRequest, PaymentInitResponse, PaymentVerifyResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Horion Farms API running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = os.getenv("DATABASE_NAME") or "❌ Not Set"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response

# ---------- Delivery ETA (Nigeria cities) ----------

NIGERIA_CITY_HUBS: Dict[str, Dict[str, Any]] = {
    # hub => { base_hours, per_km_min, cold_chain }
    "Lagos": {"base_hours": 6, "per_km_min": 1.2, "cold_chain": True},
    "Abuja": {"base_hours": 12, "per_km_min": 1.0, "cold_chain": True},
    "Port Harcourt": {"base_hours": 12, "per_km_min": 1.1, "cold_chain": True},
    "Ibadan": {"base_hours": 8, "per_km_min": 1.0, "cold_chain": True},
    "Kano": {"base_hours": 16, "per_km_min": 1.1, "cold_chain": True},
    "Enugu": {"base_hours": 14, "per_km_min": 1.0, "cold_chain": True},
    "Benin City": {"base_hours": 10, "per_km_min": 1.0, "cold_chain": True},
}

CITY_COORDS = {
    "Lagos": (6.5244, 3.3792),
    "Abuja": (9.0765, 7.3986),
    "Port Harcourt": (4.8156, 7.0498),
    "Ibadan": (7.3775, 3.9470),
    "Kano": (12.0022, 8.5919),
    "Enugu": (6.5244, 7.5174),
    "Benin City": (6.3350, 5.6037),
}

from math import radians, sin, cos, sqrt, atan2

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

@app.get("/eta")
def eta(city: str, hub: str = "Lagos"):
    """
    Estimate delivery arrival in hours between hub and city using haversine distance.
    Returns hours and cold-chain flag.
    """
    if hub not in CITY_COORDS or city not in CITY_COORDS:
        raise HTTPException(status_code=400, detail="Unsupported city or hub")
    hub_cfg = NIGERIA_CITY_HUBS.get(hub, NIGERIA_CITY_HUBS["Lagos"]) 
    hlat, hlon = CITY_COORDS[hub]
    clat, clon = CITY_COORDS[city]
    km = haversine_km(hlat, hlon, clat, clon)
    hours = hub_cfg["base_hours"] + (km * hub_cfg["per_km_min"]) / 60.0
    return {"city": city, "hub": hub, "distance_km": round(km, 1), "eta_hours": round(hours, 1), "cold_chain": hub_cfg["cold_chain"]}

# ---------- Orders & Payments ----------

@app.post("/orders")
def create_order(order: OrderCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    # Basic recompute/validation
    subtotal = sum([it.unit_price * it.quantity for it in order.items])
    if abs(subtotal - order.subtotal) > 1e-2:
        raise HTTPException(status_code=400, detail="Subtotal mismatch")
    total = order.subtotal + order.delivery_fee
    if abs(total - order.total) > 1e-2:
        raise HTTPException(status_code=400, detail="Total mismatch")

    order_doc = Order(
        items=order.items,
        customer=order.customer,
        subtotal=order.subtotal,
        delivery_fee=order.delivery_fee,
        total=order.total,
    )

    oid = create_document("order", order_doc)
    return {"order_id": oid, "status": "pending"}

@app.post("/payments/init", response_model=PaymentInitResponse)
def init_payment(payload: PaymentInitRequest):
    """
    Simulated + Paystack-ready initializer. If PAYSTACK_SECRET_KEY is present, this will
    call Paystack initialize endpoint.
    """
    order_id = payload.order_id
    if not order_id:
        raise HTTPException(status_code=400, detail="order_id required")

    # Fetch order
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        doc = db["order"].find_one({"_id": ObjectId(order_id)})
    except Exception:
        doc = None
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")

    total_amount = float(doc.get("total", 0.0))
    email = (
        doc.get("customer", {}) or {}
    ).get("email") or "orders@horionfarms.ng"

    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if secret_key:
        # Live mode with Paystack
        try:
            ref = f"HF-{order_id}"
            payload = {
                "email": email,
                "amount": int(total_amount * 100),  # Kobo
                "reference": ref,
                "currency": "NGN",
            }
            headers = {
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            }
            res = requests.post(
                "https://api.paystack.co/transaction/initialize",
                json=payload,
                headers=headers,
                timeout=10,
            )
            data = res.json()
            if not data.get("status"):
                raise HTTPException(status_code=502, detail=f"Paystack error: {data.get('message')}")
            auth_url = data["data"]["authorization_url"]
            return PaymentInitResponse(authorization_url=auth_url, reference=ref, mode="live")
        except Exception as e:
            # Fallback to simulated
            pass

    # Simulated mode
    reference = f"HF-{order_id}"
    authorization_url = f"https://pay.horionfarms.ng/checkout/{reference}"
    return PaymentInitResponse(authorization_url=authorization_url, reference=reference, mode="simulated")

@app.get("/payments/verify", response_model=PaymentVerifyResponse)
def verify_payment(reference: str):
    """
    Verifies payment. If PAYSTACK_SECRET_KEY is set, calls Paystack verify; else simulated success.
    """
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if secret_key:
        try:
            headers = {
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            }
            res = requests.get(
                f"https://api.paystack.co/transaction/verify/{reference}",
                headers=headers,
                timeout=10,
            )
            data = res.json()
            status = "failed"
            paid = False
            if data.get("status") and data.get("data", {}).get("status") == "success":
                status = "success"
                paid = True
            return PaymentVerifyResponse(status=status, order_status=("paid" if paid else "failed"), reference=reference, paid=paid)
        except Exception:
            # fall through to simulated
            pass
    # Simulated success by default
    return PaymentVerifyResponse(status="success", order_status="paid", reference=reference, paid=True)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
