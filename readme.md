docker-compose up --build



Таблицы юзеров и пользователей можно посмореть через Docker Desktop: 
psql -U admin -d users_db

Другие команды:
\d table_name
\dt
\c orders_db
\l



Браузер
    ↓
NGINX (порт 80)
    ↓
API Gateway (порт 8000) ← 👈 JWT, безопасность, логи
    ↓
Service Users (порт 8000) ← 👈 Только бизнес-логика
Service Orders (порт 8000) ← 👈 Только бизнес-логика


API Gateway: проверка токенов и прав доступа
Service Users: создание токенов, хеширование паролей
Service Orders: бизнес-логика (получает user_id из заголовков)



-------ENDPOINTS--------
1. api_gateway (HTML-страницы):
    GET /                 → index.html
    GET /login            → login.html
    GET /register         → register.html
    GET /orders           → orders.html (JWT) + данные orders/
    GET /orders/{id}      → order_detail.html (JWT) + данные orders/{id}

    Прокси API (Gateway → сервисы)
    /api/v1/users/*    → service_users:8000/api/v1/users/*
    /api/v1/orders/*   → service_orders:8000/api/v1/orders/*


2. Service Users:
    POST /api/v1/users/register
    Body: {user_model}

    POST /api/v1/users/login  
    Body: {email, password}
    Response: Set-Cookie: access_token=...

    POST /api/v1/users/logout
    Response: Clear cookie

    GET /api/v1/users/me
    Headers: Cookie: access_token=...



3. Service Orders:
    GET    /api/v1/orders
    Headers: X-User-ID: ... (из API Gateway)
    Query: ?status=created&skip=0&limit=50

    POST   /api/v1/orders
    Headers: X-User-ID: ...
    Body: {order model}

    GET    /api/v1/orders/{order_id}
    Headers: X-User-ID: ...

    PUT    /api/v1/orders/{order_id}
    Headers: X-User-ID: ...
    Body: {items, total_amount, status}

    DELETE /api/v1/orders/{order_id}
    Headers: X-User-ID: ...