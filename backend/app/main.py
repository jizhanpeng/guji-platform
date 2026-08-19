"""FastAPI 应用入口。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import annotations, crops, damage, exports, jobs, projects, stats, styles
from .db import init_db


def create_app() -> FastAPI:
    app = FastAPI(title="guji-platform", version="0.1.0")
    # 开发期 vite 端口跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(projects.router)
    app.include_router(jobs.router)
    app.include_router(annotations.router)
    app.include_router(exports.router)
    app.include_router(styles.router)
    app.include_router(crops.router)
    app.include_router(damage.router)
    app.include_router(stats.router)

    @app.on_event("startup")
    def _startup():
        init_db()

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
