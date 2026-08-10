"""FastAPI entry point."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings, DEV_SECRET_KEY
from app.routers import auth, districts, sites, inspections, issues, reports, audit, pdf_report, courtyards, checklists

if settings.APP_ENV == "production" and settings.SECRET_KEY == DEV_SECRET_KEY:
    raise RuntimeError(
        "APP_ENV=production, но SECRET_KEY всё ещё равен dev-значению по умолчанию. "
        "Сгенерируйте реальный ключ (openssl rand -hex 32) и задайте его в SECRET_KEY."
    )

app = FastAPI(
    title="Журнал обхода площадок САО",
    version="0.1.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(districts.router, prefix="/api/v1/districts", tags=["districts"])
app.include_router(courtyards.router, prefix="/api/v1/courtyards", tags=["courtyards"])
app.include_router(sites.router, prefix="/api/v1/sites", tags=["sites"])
app.include_router(checklists.router, prefix="/api/v1/checklists", tags=["checklists"])
app.include_router(inspections.router, prefix="/api/v1/inspections", tags=["inspections"])
app.include_router(issues.router, prefix="/api/v1/issues", tags=["issues"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(pdf_report.router, prefix="/api/v1/reports/pdf", tags=["pdf"])

# Статические файлы (фото)
Path("uploads").mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/")
def root():
    return {"app": "Журнал обхода площадок САО", "version": "0.1.0"}
