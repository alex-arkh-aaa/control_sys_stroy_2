from sqlalchemy import Column, String, DateTime, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from .database import Base
 


class Orders(Base):
    __tablename__ = 'orders'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID)
    items = Column(JSON)
    status = Column(String, default="created")
    total_amount = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)