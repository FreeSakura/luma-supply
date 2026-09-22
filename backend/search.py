import json
import os
import threading
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import numpy as np
from PIL import Image
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from .db import RUNTIME, SessionLocal, session
from .models import SKU, Product, Media, IndexTask, SearchLog, now
from .security import current_user, require, audit
from .common import get, expect, view
from .catalog import price_info, queue_index
from algorithms.retrieval import HandcraftedEncoder, ResNetEncoder, ChineseClipEncoder, rank

router = APIRouter(prefix="/api")
INDEX_ROOT = RUNTIME / "index"
INDEX_ROOT.mkdir(parents=True, exist_ok=True)
index_lock = threading.Lock()
_encoder = None
_loaded_version = None
_loaded_index = None


def encoder():
    global _encoder
    if _encoder is None:
        name = os.getenv("IMAGE_ENCODER", "handcrafted")
        if name == "handcrafted": _encoder = HandcraftedEncoder()
        elif name == "resnet18": _encoder = ResNetEncoder()
        elif name == "chinese-clip": _encoder = ChineseClipEncoder(os.getenv("CHINESE_CLIP_MODEL", "ViT-B-16"))
        else: raise ValueError("Unsupported IMAGE_ENCODER")
    return _encoder


def build_index(db):
    enc = encoder(); entries, vectors = [], []
    for sku in db.query(SKU).join(Product).filter(SKU.status == "active", Product.status == "active"):
        product = db.get(Product, sku.product_id)
        for mid in sku.images:
            media = get(db, Media, mid)
            with Image.open(media.path) as image: vector = enc.encode_image(image)
            vectors.append(vector)
            entries.append({"sku_id": sku.id, "product_id": product.id, "sku_code": sku.code, "product_name": product.name, "image_id": mid, "category": product.category, "attributes": {**sku.attributes, "color": sku.color}, "text": " ".join([product.name, product.title, product.category, sku.code, sku.color, sku.specification, json.dumps(sku.attributes, ensure_ascii=False)])})
    version = now().strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:8]
    matrix = np.vstack(vectors) if vectors else np.empty((0, 0), dtype=np.float32)
    np.savez_compressed(INDEX_ROOT / f"{version}.npz", vectors=matrix)
    (INDEX_ROOT / f"{version}.json").write_text(json.dumps({"version": version, "encoder": enc.version, "entries": entries}, ensure_ascii=False), encoding="utf-8")
    temporary = INDEX_ROOT / "current.tmp"
    temporary.write_text(version, encoding="utf-8")
    temporary.replace(INDEX_ROOT / "current")
    return {"version": version, "encoder": enc.version, "images": len(entries), "bytes": (INDEX_ROOT / f"{version}.npz").stat().st_size}


def process_pending():
    if not index_lock.acquire(blocking=False): return
    try:
        with SessionLocal() as db:
            tasks = db.query(IndexTask).filter_by(status="pending").all()
            if not tasks: return
            for t in tasks: t.status = "running"; t.attempts += 1
            db.commit()
            try:
                result = build_index(db)
                for t in tasks: t.status = "completed"; t.error = ""
            except Exception as exc:
                for t in tasks: t.status = "failed"; t.error = f"{type(exc).__name__}: {str(exc)[:400]}"
            db.commit()
    finally: index_lock.release()


def load_index():
    global _loaded_version, _loaded_index
    expect((INDEX_ROOT / "current").exists(), "检索索引尚未就绪，请稍后重试；文字商品搜索仍可用", 503)
    version = (INDEX_ROOT / "current").read_text(encoding="utf-8")
    if version != _loaded_version:
        metadata = json.loads((INDEX_ROOT / f"{version}.json").read_text(encoding="utf-8"))
        with np.load(INDEX_ROOT / f"{version}.npz") as data: vectors = data["vectors"].copy()
        _loaded_index, _loaded_version = (metadata, vectors), version
    return _loaded_index


class SearchIn(BaseModel):
    image_id: str | None = None
    text: str = Field(default="", max_length=500)
    crop: tuple[float, float, float, float] | None = None
    category: str = ""
    max_price: int | None = Field(default=None, ge=0)
    available_only: bool = False
    attributes: dict[str, str | int | float] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)
    provider: str = "local"


@router.post("/search")
def search(body: SearchIn, user=Depends(current_user), db: Session = Depends(session)):
    start = perf_counter()
    expect(body.image_id or body.text.strip(), "请上传图片或输入搜索文字")
    query_vector, media = None, None
    if body.image_id:
        media = get(db, Media, body.image_id)
        expect(media.owner_id == user.id or media.purpose == "product", "无权使用该图片", 403)
        expect(media.mime.startswith("image/"), "仅支持图片检索")
    if body.provider == "aliyun":
        from .integrations import aliyun_search
        expect(media, "阿里云图片检索需要图片")
        result = aliyun_search(Path(media.path).read_bytes(), body.limit)
        # ProductId/PicName are SKU ID / media ID under our cloud import contract.
        hits = []
        for item in result:
            sku = db.get(SKU, item["sku_id"])
            if not sku or sku.status != "active": continue
            product = db.get(Product, sku.product_id)
            if product.status != "active": continue
            info = price_info(db, sku)
            if body.max_price is not None and info["price"] > body.max_price: continue
            if body.category and product.category != body.category: continue
            if body.available_only and sku.stock_status != "available": continue
            attrs = {**sku.attributes, "color": sku.color}
            if any(str(attrs.get(k)) != str(v) for k, v in body.attributes.items()): continue
            hits.append({**item, **info, "product_id": product.id, "product_name": product.name, "sku_code": sku.code, "image_id": sku.images[0] if sku.images else None})
        version = "aliyun-external"
    else:
        expect(body.provider == "local", "未知检索实现")
        metadata, vectors = load_index()
        enc = encoder()
        expect(metadata["encoder"] == enc.version, "模型版本已变更，请重建索引", 503)
        if media:
            try:
                with Image.open(media.path) as im: query_vector = enc.encode_image(im, body.crop)
            except ValueError as exc: raise HTTPException(400, str(exc))
        entries, positions = [], []
        for i, entry in enumerate(metadata["entries"]):
            sku = db.get(SKU, entry["sku_id"])
            if not sku or sku.status != "active": continue
            product = db.get(Product, sku.product_id)
            if product.status != "active": continue
            entries.append({**entry, **price_info(db, sku)}); positions.append(i)
        filtered_vectors = vectors[positions] if positions else np.empty((0, vectors.shape[1] if vectors.ndim == 2 else 0))
        text_vector = enc.encode_text(body.text) if body.text and hasattr(enc, "encode_text") else None
        hits = rank(query_vector, filtered_vectors, entries, text=body.text, image_weight=0.3, text_weight=0.7, filters={"category": body.category, "max_price": body.max_price, "available_only": body.available_only, "attributes": body.attributes}, limit=body.limit, clip_text_vector=text_vector, threshold=0.01 if query_vector is None else 0.15)
        version = metadata["version"] + "/" + metadata["encoder"]
    elapsed = int((perf_counter() - start) * 1000)
    log = SearchLog(user_id=user.id, query=body.text, results=[x["sku_id"] for x in hits], latency_ms=elapsed, model_version=version)
    db.add(log); db.flush()
    return {"query_id": log.id, "results": hits, "elapsed_ms": elapsed, "index_version": version, "notice": "外观候选不等于同款；请核对功率、色温与尺寸。" if hits else "没有满足条件的结果，请调整框选、条件或联系人工客服。"}


class FeedbackIn(BaseModel):
    sku_id: int | None = None
    issue: str = Field(min_length=1, max_length=200)


@router.post("/search/{query_id}/feedback")
def feedback(query_id: int, body: FeedbackIn, user=Depends(current_user), db: Session = Depends(session)):
    obj = get(db, SearchLog, query_id); expect(obj.user_id == user.id, "无权操作", 403)
    expect(body.sku_id is None or body.sku_id in obj.results, "反馈 SKU 不在该次搜索结果中")
    obj.feedback = obj.feedback + [body.model_dump()]
    return {"saved": True}


@router.get("/admin/index")
def index_status(user=Depends(require("admin", "staff", module="catalog")), db: Session = Depends(session)):
    try:
        metadata, vectors = load_index(); info = {"version": metadata["version"], "encoder": metadata["encoder"], "images": len(metadata["entries"]), "memory_bytes": vectors.nbytes}
    except HTTPException: info = {"version": None}
    return {**info, "tasks": [view(t) for t in db.query(IndexTask).order_by(IndexTask.id.desc()).limit(50)]}


@router.post("/admin/index/rebuild")
def rebuild(user=Depends(require("admin", "staff", module="catalog")), db: Session = Depends(session)):
    queue_index(db, "manual rebuild"); audit(db, user, "index.rebuild", "all")
    return {"queued": True}


@router.post("/admin/index/{task_id}/retry")
def retry(task_id: int, user=Depends(require("admin", "staff", module="catalog")), db: Session = Depends(session)):
    t = get(db, IndexTask, task_id); expect(t.status == "failed", "仅失败任务可重试")
    t.status = "pending"; t.error = ""; return view(t)
