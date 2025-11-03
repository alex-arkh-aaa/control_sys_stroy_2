from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import List, Dict

class OrderItem(BaseModel):
    product: str
    quantity: int
    price: int  # цена за единицу

class OrderCreate(BaseModel):
    items: List[OrderItem]
    total_amount: int

class OrderResponse(BaseModel):
    id: UUID
    user_id: UUID
    items: List[Dict]
    status: str
    total_amount: int
    created_at: datetime
    updated_at: datetime

class OrderUpdate(BaseModel):
    status: str  
    # "created", "in_progress", "completed", "cancelled"