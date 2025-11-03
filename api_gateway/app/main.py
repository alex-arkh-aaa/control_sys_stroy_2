# from fastapi import FastAPI, Request, HTTPException
# from fastapi.responses import JSONResponse
# import httpx

# import logging
# logger = logging.getLogger(__name__)

# app = FastAPI(title="API Gateway")

# # Конфигурация сервисов
# SERVICE_URLS = {
#     "users": "http://service_users:8000",
#     "orders": "http://service_orders:8000"
# }

# @app.get("/health")
# async def root():
#     return {"message": "API Gateway is running"}

# # ✅ ДОБАВЬ ПРОКСИ ДЛЯ USERS
# @app.api_route("/api/v1/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
# async def proxy_users(request: Request, path: str):
#     return await proxy_request("users", request, path)

# # ✅ ДОБАВЬ ПРОКСИ ДЛЯ ORDERS
# @app.api_route("/api/v1/orders/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
# async def proxy_orders(request: Request, path: str):
#     return await proxy_request("orders", request, path)

# async def proxy_request(service: str, request: Request, path: str):
#     # ИСПРАВЛЯЕМ - добавляем префикс сервиса к пути
#     target_url = f"{SERVICE_URLS[service]}/api/v1/{service}/{path}"
#     # Теперь для /api/v1/users/health → 
#     # http://service_users:8000/api/v1/users/health ✅
    
#     # Прокидываем заголовки
#     headers = {key: value for key, value in request.headers.items() 
#                if key.lower() not in ['host', 'content-length']}
    
#     # Получаем тело запроса
#     body = await request.body()
    
#     try:
#         async with httpx.AsyncClient() as client:
#             response = await client.request(
#                 method=request.method,
#                 url=target_url,
#                 headers=headers,
#                 content=body,
#                 params=request.query_params
#             )
            
#             return JSONResponse(
#                 content=response.json(),
#                 status_code=response.status_code,
#                 headers=dict(response.headers)
#             )
            
#     except httpx.ConnectError:
#         logger.error(f"Cannot connect to {service} service")
#         raise HTTPException(status_code=503, detail=f"Service {service} unavailable")
#     except Exception as e:
#         logger.error(f"Error proxying to {service}: {str(e)}")
#         raise HTTPException(status_code=500, detail="Internal gateway error")



from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
import logging
from typing import Optional
from jose import JWTError, jwt
import os

logger = logging.getLogger(__name__)

app = FastAPI(title="API Gateway")

# Конфигурация сервисов
SERVICE_URLS = {
    "users": "http://service_users:8000",
    "orders": "http://service_orders:8000"
}

# ================== MIDDLEWARE ==================
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Выполняется на КАЖДЫЙ запрос"""
    
    # 1. Публичные пути (пропускаем без проверки JWT)
    public_paths = [
        '/', 
        '/api/v1/users/login', '/api/v1/users/register', '/api/v1/users/health',
        '/api/v1/orders/health'
    ]

    if request.url.path in public_paths:
        logger.warning(f"🟢 Public path: {request.url.path}")
        return await call_next(request)
    
    # 2. Для защищённых путей - проверяем JWT из cookie
    token = request.cookies.get("access_token")
    
    if not token:
        logger.warning("❌ No token found")
        # Нет токена - редирект на логин или 401
        if request.url.path.startswith('/api/'):
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})
        else:
            return RedirectResponse(url="/login")
        
    # 3. Проверяем JWT
    # user = verify_token(token)
    # logger.warning(user)

    try:
        payload = jwt.decode(
            token, 
            os.getenv('JWT_SECRET_KEY'), 
            algorithms=[os.getenv('JWT_ALGORITHM')]
        )
        logger.info(f"✅ Valid JWT for user: {payload.get('sub')}")
        
    except jwt.ExpiredSignatureError:
        logger.warning("❌ JWT token expired")
        if request.url.path.startswith('/api/'):
            return JSONResponse(status_code=401, content={"error": "Token expired"})
        else:
            return RedirectResponse(url="/login")
            
    except jwt.JWTError as e:
        logger.error(f"❌ JWT validation error: {e}")
        if request.url.path.startswith('/api/'):
            return JSONResponse(status_code=401, content={"error": "Invalid token"})
        else:
            return RedirectResponse(url="/login")
    
    # 4. Сохраняем пользователя в запросе
    request.state.user = payload
    logger.warning(f"✅ Authenticated user: {payload.get('sub')}")
    
    # 5. Передаём запрос дальше в роутеры
    response = await call_next(request)
    return response



# ================== ПРОКСИРОВАНИЕ ==================
@app.get("/")
async def root():
    return {"message": "API Gateway is running"}

@app.api_route("/api/v1/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_users(request: Request, path: str):
    return await proxy_request("users", request, path)

@app.api_route("/api/v1/orders/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_orders(request: Request, path: str):
    logger.warning('orders')
    return await proxy_request("orders", request, path)

async def proxy_request(service: str, request: Request, path: str):
    """Проксирует запрос в указанный сервис"""
    target_url = f"{SERVICE_URLS[service]}/api/v1/{service}/{path}"
    logger.warning(f"🔄 Proxying to: {target_url}")
    
    # Подготавливаем заголовки
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in ['host', 'content-length']
    }
    
    # 👇 ПРОКИДЫВАЕМ USER_ID ЕСЛИ ЕСТЬ
    if hasattr(request.state, 'user'):
        user_data = request.state.user
        headers["X-User-ID"] = user_data.get("user_id", "")
        headers["X-User-Email"] = user_data.get("sub", "")
        headers["X-User-Roles"] = ",".join(user_data.get("roles", []))
        logger.warning(f"👤 Adding user headers: {user_data.get('sub')}")
    
    # Получаем тело запроса
    body = await request.body()
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=request.query_params,
                timeout=30.0
            )
            logger.warning(response)
            return JSONResponse(
                content=response.json() if response.content else {},
                status_code=response.status_code,
                headers=dict(response.headers)
            )
            
    except httpx.ConnectError:
        logger.error(f"❌ Cannot connect to {service} service")
        raise HTTPException(status_code=503, detail=f"Service {service} unavailable")
    except Exception as e:
        logger.error(f"❌ Error proxying to {service}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal gateway error")

# ================== HEALTH CHECK ==================
@app.get("/health")
async def health():
    return {"status": "API Gateway is healthy"}

@app.get("/api/health")
async def api_health():
    return {"status": "API Gateway API is healthy"}