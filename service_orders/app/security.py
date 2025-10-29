from fastapi import HTTPException
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from config import settings

# Настраиваем контекст для хеширования паролей
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Функция для хеширования пароля
def get_password_hash(password):
    try:
        result = pwd_context.hash(password)
        print("✅ Хеширование успешно")
        return result
    except Exception as e:
        print(f"❌ Ошибка хеширования: {e}")
        raise

# Функция для проверки пароля
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta = settings.ACCESS_TOKEN_EXPIRE_MINUTES):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})  # Добавляем время истечения
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str):
    try:
            
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None  # Если токен недействителен или истёк
    
    
# Функция для проверки валидности токена (для зависимостей)
def verify_token(token: str):
    return decode_token(token) is not None

def check_create_order_permission(current_user):
    """Проверяет право на создание проекта"""
    if current_user.roles not in ["manager", "seo"]:
        raise HTTPException(
            status_code=403, 
            detail="Только менеджеры и руководители могут создавать проекты"
        )

def check_edit_defect_permission(current_user, defect):
    """Проверяет право на редактирование дефекта"""
    if current_user.roles == "seo":
        return True  # Руководитель может всё
        
    if defect.author_id == current_user.id:
        return True  # Автор может редактировать свой дефект
        
    if defect.assignee_id == current_user.id:
        return True  # Исполнитель может менять статус
        
    raise HTTPException(
        status_code=403, 
        detail="Нет прав для редактирования этого дефекта"
    )

async def check_order_access(db, order_id: int, current_user):
    """Проверяет доступ пользователя к проекту"""
    from . import crud
    project = await crud.get_order(db, order_id)
    if not project:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return True