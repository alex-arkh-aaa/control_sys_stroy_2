from sqlalchemy import UUID, select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Orders

async def create_order(db: AsyncSession, user_id: UUID, items: list, total_amount: int):
    order = Orders(user_id=user_id, items=items, total_amount=total_amount, status="created")
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order

async def get_user_orders(db: AsyncSession, user_id: UUID, skip: int = 0, limit: int = 100):
    result = await db.execute(select(Orders).where(Orders.user_id == user_id).offset(skip).limit(limit))
    return result.scalars().all()

async def get_order(db: AsyncSession, order_id: UUID):
    result = await db.execute(select(Orders).where(Orders.id == order_id))
    return result.scalar_one_or_none()

async def update_order_status(db: AsyncSession, order_id: UUID, status: str):
    order = await get_order(db, order_id)
    if order:
        order.status = status
        await db.commit()
        await db.refresh(order)
    return order

async def delete_order(db: AsyncSession, order_id: UUID):
    order = await get_order(db, order_id)
    if order:
        await db.delete(order)
        await db.commit()
    return order