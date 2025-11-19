from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import httpx
import logging
from typing import Optional
from jose import JWTError, jwt
import os
from fastapi.middleware.cors import CORSMiddleware
from .rate_limiting import rate_limit_middleware


logger = logging.getLogger(__name__)

app = FastAPI(title="API Gateway")
templates = Jinja2Templates(directory="app/templates")



# Конфигурация сервисов
SERVICE_URLS = {
    "users": "http://service_users:8000",
    "orders": "http://service_orders:8000"
}


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://127.0.0.1:3000", 
        "http://localhost:8000",  # FastAPI itself
        "http://127.0.0.1:8000",
        "null"
        # Добавь другие домены по необходимости
    ],
    allow_credentials=True,  # Разрешает cookies, authorization headers
    allow_methods=["*"],     # Разрешает все методы: GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],     # Разрешает все заголовки
)

# Rate Limiting Middleware
@app.middleware("http")
async def add_rate_limiting(request: Request, call_next):
    return await rate_limit_middleware(request, call_next)

# ================== MIDDLEWARE ==================
@app.middleware("http")
async def auth_middleware(request: Request, call_next): 
    """Выполняется на КАЖДЫЙ запрос"""
    

    # Пропускаем CORS preflight запросы (OPTIONS)
    if request.method == "OPTIONS":
        return await call_next(request)
    # 1. Публичные пути (пропускаем без проверки JWT)
    public_paths = [
        '/', 
        '/login', '/register', '/api/v1/users/health',
        '/api/v1/orders/health', '/api/v1/users/login',
        '/api/v1/users/register'
    ]

    logger.warning(request.url.path)
    if request.url.path in public_paths:
        # logger.warning(f"🟢 Public path: {request.url.path}")
        return await call_next(request)
    
    # 2. Для защищённых путей - проверяем JWT из cookie
    token = request.cookies.get("access_token")
    
    if not token:
        # logger.warning("❌ No token found")
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
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)  
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    return templates.TemplateResponse("profile.html", {"request": request})

@app.get("/orders", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("orders.html", {"request": request})

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