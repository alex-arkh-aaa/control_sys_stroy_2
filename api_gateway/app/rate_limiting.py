from fastapi import Request, HTTPException
import time
from typing import Dict, Tuple
import logging
from collections import defaultdict

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# In-memory хранилище: { "ip:path": (count, window_start) }
request_counts: Dict[str, Tuple[int, float]] = {}
# Альтернатива с defaultdict для автоматической очистки
# request_counts = defaultdict(lambda: (0, 0))

class RateLimitExceededException(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=429, detail=detail)

def get_client_ip(request: Request) -> str:
    """Получаем реальный IP клиента с учётом прокси"""
    if "x-forwarded-for" in request.headers:
        # Если за nginx/load balancer - берём первый IP из цепочки
        ip = request.headers["x-forwarded-for"].split(",")[0].strip()
    else:
        ip = request.client.host or "unknown"
    return ip

def should_rate_limit(request: Request) -> bool:
    """Определяем, нужно ли применять rate limiting к этому пути"""
    path = request.url.path
    
    # Не ограничиваем статические файлы и health checks
    excluded_paths = [
        '/health',
        '/api/health', 
        '/api/v1/users/health',
        '/api/v1/orders/health',
        '/static/',
        '/favicon.ico'
    ]
    
    return not any(path.startswith(excluded) for excluded in excluded_paths)

async def rate_limit_middleware(request: Request, call_next):
    """Middleware для ограничения запросов по IP"""
    
    # Пропускаем OPTIONS запросы (CORS preflight)
    if request.method == "OPTIONS":
        return await call_next(request)
    
    # Проверяем, нужно ли ограничивать этот путь
    if not should_rate_limit(request):
        return await call_next(request)
    
    client_ip = get_client_ip(request)
    path = request.url.path
    current_time = time.time()
    
    # Определяем лимиты в зависимости от пути
    limits_config = {
        "/api/v1/users/login": {"limit": 5, "window": 60},      # 5 попыток входа в минуту
        "/api/v1/users/register": {"limit": 3, "window": 300},  # 3 регистрации в 5 минут
        "/api/v1/orders": {"limit": 30, "window": 60},          # 30 операций с заказами в минуту
        "default": {"limit": 10, "window": 60}                 # 100 запросов в минуту
    }
    
    # Находим подходящий лимит
    limit_config = limits_config.get(path, limits_config["default"])
    limit = limit_config["limit"]
    window = limit_config["window"]
    
    # Ключ для хранения: IP + путь
    key = f"{client_ip}:{path}"
    
    # Получаем текущий счётчик
    if key in request_counts:
        count, window_start = request_counts[key]
        
        # Проверяем не истекло ли окно
        if current_time - window_start >= window:
            # Сбрасываем счётчик - новое окно
            count = 1
            request_counts[key] = (1, current_time)
            logger.warning(f"New window started for {key}")
        else:
            # Увеличиваем счётчик в текущем окне
            count += 1
            request_counts[key] = (count, window_start)
    else:
        # Первый запрос в новом окне
        count = 1
        request_counts[key] = (1, current_time)
        logger.warning(f"First request in window for {key}")
    
    # Проверяем лимит
    if count > limit:
        logger.warning(f"🚨 Rate limit exceeded for {client_ip} on {path}: {count}/{limit}")
        
        reset_time = request_counts[key][1] + window
        remaining_time = int(reset_time - current_time)
        
        # ВОЗВРАЩАЕМ JSONResponse вместо исключения
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"Слишком много запросов. Лимит: {limit} в {window} секунд. Попробуйте через {remaining_time} сек."
            },
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset_time)),
                "Retry-After": str(remaining_time)
            }
        )
    
    # Обрабатываем запрос
    response = await call_next(request)
    
    # Добавляем заголовки с информацией о лимитах
    reset_time = request_counts[key][1] + window
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
    response.headers["X-RateLimit-Reset"] = str(int(reset_time))
    response.headers["Retry-After"] = str(int(reset_time - current_time))
    
    logger.warning(f"Request {count}/{limit} from {client_ip} on {path}")
    
    return response

# Функция для очистки устаревших записей (опционально)
def cleanup_old_entries():
    """Очищает записи старше 1 часа (для экономии памяти)"""
    current_time = time.time()
    expired_keys = [
        key for key, (count, window_start) in request_counts.items()
        if current_time - window_start > 3600  # 1 час
    ]
    for key in expired_keys:
        del request_counts[key]
    if expired_keys:
        logger.warning(f"Cleaned up {len(expired_keys)} old rate limit entries")