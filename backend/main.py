import os
import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from .db import Base, engine, ROOT
from . import accounts, catalog, media, orders, operations, search


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    from .db import SessionLocal
    from .models import IndexTask
    with SessionLocal() as db:
        db.query(IndexTask).filter_by(status="running").update({"status": "pending", "error": "interrupted worker recovered"})
        db.commit()
    async def worker():
        while True:
            await asyncio.to_thread(search.process_pending)
            await asyncio.sleep(2)
    task = asyncio.create_task(worker())
    try: yield
    finally:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass


app = FastAPI(title="LumaSupply API", version="1.0.0", description="灯具商城、SKU 多模态检索与采购协同。金额单位为分。", lifespan=lifespan)
for module in [accounts, catalog, media, orders, operations, search]: app.include_router(module.router)


@app.middleware("http")
async def trace(request: Request, call_next):
    trace_id = uuid4().hex[:16]
    response = await call_next(request)
    response.headers["X-Request-ID"] = trace_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(IntegrityError)
async def integrity(request, exc):
    return JSONResponse(status_code=409, content={"detail": "数据已存在或发生并发变更，请刷新后重试"})


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0", "environment": os.getenv("APP_ENV", "development"), "integrations": {"aliyun": bool(os.getenv("ALIYUN_IMAGESEARCH_INSTANCE") and os.getenv("ALIYUN_ACCESS_KEY_ID")), "wechat": bool(os.getenv("WECHAT_APP_ID") and os.getenv("WECHAT_APP_SECRET")), "sms": bool(os.getenv("SMS_ENDPOINT")), "encoder": os.getenv("IMAGE_ENCODER", "handcrafted")}}


def mount_frontend():
    dist = ROOT / "web" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"): return JSONResponse(status_code=404, content={"detail": "Not found"})
            return FileResponse(dist / "index.html")
