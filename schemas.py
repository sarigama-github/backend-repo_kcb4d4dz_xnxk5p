"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal

# Example schemas (replace with your own):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in naira")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Horion Farms — Orders & Payments

class OrderItem(BaseModel):
    name: str
    unit_price: float = Field(..., ge=0)
    quantity: int = Field(..., ge=1)

class CustomerInfo(BaseModel):
    name: str
    email: EmailStr
    phone: str
    address: str
    city: str

class OrderCreate(BaseModel):
    items: List[OrderItem]
    customer: CustomerInfo
    subtotal: float = Field(..., ge=0)
    delivery_fee: float = Field(..., ge=0)
    total: float = Field(..., ge=0)

class Order(BaseModel):
    items: List[OrderItem]
    customer: CustomerInfo
    subtotal: float
    delivery_fee: float
    total: float
    currency: str = Field("NGN", description="Currency code")
    status: str = Field("pending", description="Order status: pending|paid|failed|cancelled|fulfilled")
    payment_reference: Optional[str] = None

class PaymentInitRequest(BaseModel):
    order_id: str
    payment_method: Literal['card', 'bank_transfer'] = 'card'

class PaymentInitResponse(BaseModel):
    mode: str = Field(..., description="live|simulated|manual")
    reference: str
    payment_method: Literal['card', 'bank_transfer']
    authorization_url: Optional[str] = None
    account_number: Optional[str] = None
    account_name: Optional[str] = None
    bank_name: Optional[str] = None
    instructions: Optional[str] = None

class PaymentVerifyResponse(BaseModel):
    status: str
    order_status: str
    reference: str
    paid: bool

# Note: The Flames database viewer will automatically:
# 1. Read these schemas from GET /schema endpoint
# 2. Use them for document validation when creating/editing
# 3. Handle all database operations (CRUD) directly
# 4. You don't need to create any database endpoints!
