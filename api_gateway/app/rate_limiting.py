from fastapi import Request, HTTPException
import time
from typing import Dict, Tuple
import logging
from collections import defaultdict

from fastapi.responses import JSONResponse
import os
import redis
logger = logging.getLogger(__name__)

# In-memory хранилище: { "ip:path": (count, window_start) }
request_counts: Dict[str, Tuple[int, float]] = {}
# Альтернатива с defaultdict для автоматической очистки
# request_counts = defaultdict(lambda: (0, 0))

r = redis.from_url(os.getenv('REDIS_URL'))

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
    key_reqs = f"{client_ip}:{path}:requests"
    key_blocking = f'{client_ip}:{path}:blocking'

    if not r.exists(key_blocking):
        r.set(key_reqs, 1, ex=100)
        r.set(key_blocking, '')

        print(f'set key_reqs = {key_reqs}, key_blocking = {key_blocking}')

    else:
        ttl_blocking = int(r.ttl(key_blocking))
        print(ttl_blocking)
        if ttl_blocking > 0: 
            print(f'block for {ttl_blocking} secs')

            return return_exept(ttl_blocking)

        
        else:
            print(f'r.ttl(key_reqs) = {r.ttl(key_reqs)}')
            if not r.ttl(key_reqs) > 0:
                r.set(key_reqs, 1, ex=100)
                print('no reqs yet, set key_reqs = 1')
            
            else:
                if int(r.get(key_reqs)) == 9:
                    r.expire(key_blocking, 60)
                    r.set(key_reqs, 0)
                    print(f'10th req, return exept')
                    return return_exept(ttl_blocking)

                else:
                    r.incr(key_reqs)
                    print(f'common incr reqs = {r.get(key_reqs)}')

    
    
    # Обрабатываем запрос
    response = await call_next(request)

    # # Добавляем заголовки с информацией о лимитах
    # reset_time = request_counts[key][1] + window
    # response.headers["X-RateLimit-Limit"] = str(limit)
    # response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
    # response.headers["X-RateLimit-Reset"] = str(int(reset_time))
    # response.headers["Retry-After"] = str(int(reset_time - current_time))
    
    #logger.warning(f"Request {count}/{limit} from {client_ip} on {path}")
    
    return response

# Функция для очистки устаревших записей (опционально)
# def cleanup_old_entries():
#     """Очищает записи старше 1 часа (для экономии памяти)"""
#     current_time = time.time()
#     expired_keys = [
#         key for key, (count, window_start) in request_counts.items()
#         if current_time - window_start > 3600  # 1 час
#     ]
#     for key in expired_keys:
#         del request_counts[key]
#     if expired_keys:
#         logger.warning(f"Cleaned up {len(expired_keys)} old rate limit entries")



def return_exept(remaining_time: int):
    return JSONResponse(
    status_code=429,
    content={
        "detail": f"Слишком много запросов. Лимит: 10 в 60 секунд. Попробуйте через {remaining_time} сек."
    },
    headers={
        "X-RateLimit-Limit": '10',
        "X-RateLimit-Remaining": "0",
        "Retry-After": str(remaining_time)
    }
)
