from fastapi import FastAPI, Header, responses, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db, create_tables
from . import crud
from .schemas import *
from contextlib import asynccontextmanager
from .security import *
from sqlalchemy import select
from .models import *
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi.responses import HTMLResponse
import sys

import logging
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔄 Начинаем создание таблицы users...-----------------------"
    "-------------------------------------------------------------------------------------", file=sys.stderr)
    try:
        await create_tables()
        print("✅ Таблица users созданы/проверены", file=sys.stderr)
    except Exception as e:
        print(f"❌ Ошибка при создании таблиц: {e}", file=sys.stderr)
    yield



app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory="app/templates")