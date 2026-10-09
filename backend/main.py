import os
import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, OperationalError
from .db import Base, engine, ROOT
from . import accounts, catalog, media, orders, operations, search, inquiries, wechat


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    from .migrations import upgrade
    upgrade(engine)
    async def worker():
        while True:
            try: await asyncio.to_thread(search.process_pending)
            except (OperationalError, OSError) as exc:
                logging.getLogger(__name__).warning('Index worker will retry after %s', type(exc).__name__)
            await asyncio.sleep(2)
    task = asyncio.create_task(worker())
    try: yield
    finally:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass


app = FastAPI(title="LumaSupply API", version="2.1.0", description="灯具商城、SKU 多模态检索与采购协同。金额单位为分。", lifespan=lifespan)
for module in [accounts, catalog, media, orders, operations, search, inquiries, wechat]: app.include_router(module.router)


@app.middleware("http")
async def trace(request: Request, call_next):
    trace_id = uuid4().hex[:16]
    request.state.request_id = trace_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = trace_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(IntegrityError)
async def integrity(request, exc):
    return error_response(request, 409, 'conflict', '数据已存在或发生并发变更，请刷新后重试')


def error_response(request, status, code, message, detail=None, headers=None):
    return JSONResponse(status_code=status, headers=headers, content={
        'code': code, 'message': message, 'detail': message if detail is None else detail,
        'request_id': getattr(request.state, 'request_id', '')})


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    codes = {400:'invalid_request',401:'unauthenticated',403:'forbidden',404:'not_found',409:'conflict',429:'rate_limited',502:'provider_failure',503:'service_unavailable'}
    detail = exc.detail
    return error_response(request, exc.status_code,
        detail.get('code', codes.get(exc.status_code, 'request_failed')) if isinstance(detail, dict) else codes.get(exc.status_code, 'request_failed'),
        detail.get('message', '请求失败') if isinstance(detail, dict) else detail, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return error_response(request, 422, 'validation_error', '请检查填写内容', jsonable_encoder(exc.errors()))


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.1.0", "environment": os.getenv("APP_ENV", "development"), "integrations": {"aliyun": bool(os.getenv("ALIYUN_IMAGESEARCH_INSTANCE") and os.getenv("ALIYUN_ACCESS_KEY_ID")), "wechat": bool(os.getenv("WECHAT_APP_ID") and os.getenv("WECHAT_APP_SECRET")), "sms": bool(os.getenv("SMS_ENDPOINT")), "encoder": os.getenv("IMAGE_ENCODER", "handcrafted")}}


def mount_frontend():
    dist = ROOT / "web" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"): return JSONResponse(status_code=404, content={"detail": "Not found"})
            return FileResponse(dist / "index.html")


mount_frontend()
