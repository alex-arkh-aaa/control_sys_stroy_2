from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx

import logging
logger = logging.getLogger(__name__)

app = FastAPI(title="API Gateway")

# Конфигурация сервисов
SERVICE_URLS = {
    "users": "http://service_users:8000",
    "orders": "http://service_orders:8000"
}

@app.get("/health")
async def root():
    return {"message": "API Gateway is running"}

# ✅ ДОБАВЬ ПРОКСИ ДЛЯ USERS
@app.api_route("/api/v1/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_users(request: Request, path: str):
    return await proxy_request("users", request, path)

# ✅ ДОБАВЬ ПРОКСИ ДЛЯ ORDERS
@app.api_route("/api/v1/orders/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_orders(request: Request, path: str):
    return await proxy_request("orders", request, path)

async def proxy_request(service: str, request: Request, path: str):
    # ИСПРАВЛЯЕМ - добавляем префикс сервиса к пути
    target_url = f"{SERVICE_URLS[service]}/api/v1/{service}/{path}"
    # Теперь для /api/v1/users/health → 
    # http://service_users:8000/api/v1/users/health ✅
    
    # Прокидываем заголовки
    headers = {key: value for key, value in request.headers.items() 
               if key.lower() not in ['host', 'content-length']}
    
    # Получаем тело запроса
    body = await request.body()
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=request.query_params
            )
            
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code,
                headers=dict(response.headers)
            )
            
    except httpx.ConnectError:
        logger.error(f"Cannot connect to {service} service")
        raise HTTPException(status_code=503, detail=f"Service {service} unavailable")
    except Exception as e:
        logger.error(f"Error proxying to {service}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal gateway error")