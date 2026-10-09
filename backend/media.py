from io import BytesIO
from pathlib import Path
from uuid import uuid4
from typing import Literal
from PIL import Image, ImageOps, UnidentifiedImageError
import json
import struct
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import exists, select, func
from .db import RUNTIME, session
from .models import Media, User
from .security import current_user
from .common import get, expect

router = APIRouter(prefix="/api")
MEDIA_ROOT = RUNTIME / "media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
Image.MAX_IMAGE_PIXELS = 24_000_000


def owned_media(db, user, ids, purposes=None):
    expect(len(ids) <= 9, "附件最多 9 项")
    for mid in ids:
        m = get(db, Media, mid)
        expect(m.owner_id == user.id, "附件不属于当前账户", 403)
        if purposes: expect(m.purpose in purposes, "附件用途不符")


def json_contains(db, column, value):
    if db.bind.dialect.name == 'sqlite':
        items = func.json_each(column).table_valued('key', 'value')
        return exists(select(1).select_from(items).where(items.c.value == value))
    return func.json_contains(column, json.dumps(value)) == 1


def is_public(db, m):
    from .models import SKU, Product, Setting, Review
    allowed = False
    if m.purpose == "product":
        allowed = db.query(SKU.id).join(Product).filter(SKU.status == 'active', Product.status == 'active', json_contains(db, SKU.images, m.id)).first() is not None
    if m.purpose in ["product", "banner", "support"] and not allowed:
        allowed = any(any(row.get("image") == m.id for row in s.value) for s in db.query(Setting) if isinstance(s.value, list))
    if m.purpose == "review": allowed = db.query(Review.id).filter(Review.deleted.is_(False), json_contains(db, Review.media_ids, m.id)).first() is not None
    return allowed


@router.get("/public-media/{media_id}")
def public_media(media_id: str, db: Session = Depends(session, scope="function")):
    m = get(db, Media, media_id)
    expect(is_public(db, m), "素材尚未发布", 404)
    return FileResponse(m.path, media_type=m.mime, headers={"X-Content-Type-Options": "nosniff"})


def mp4_boxes(data):
    offset = 0
    while offset < len(data):
        if len(data) - offset < 8: raise ValueError('Truncated box')
        size, kind = struct.unpack('>I4s', data[offset:offset + 8]); header = 8
        if size == 1:
            if len(data) - offset < 16: raise ValueError('Truncated large box')
            size = struct.unpack('>Q', data[offset + 8:offset + 16])[0]; header = 16
        if size == 0: size = len(data) - offset
        if size < header or offset + size > len(data): raise ValueError('Invalid box size')
        yield kind, data[offset + header:offset + size]
        offset += size


def validate_mp4(content):
    try:
        boxes = dict(mp4_boxes(content))
        expect(len(boxes.get(b'ftyp', b'')) >= 8 and len(boxes.get(b'mdat', b'')) > 0, 'MP4缺少文件类型或视频数据')
        movie = list(mp4_boxes(boxes.get(b'moov', b'')))
        handlers = [payload for kind, track in movie if kind == b'trak'
                    for kind2, media in mp4_boxes(track) if kind2 == b'mdia'
                    for kind3, payload in mp4_boxes(media) if kind3 == b'hdlr']
        expect(any(len(h) >= 12 and h[8:12] == b'vide' for h in handlers), 'MP4不包含有效视频轨道')
    except (ValueError, struct.error):
        raise HTTPException(400, 'MP4结构不完整或损坏') from None


@router.post("/media", status_code=201)
async def upload(file: UploadFile = File(...), purpose: Literal["product", "query", "license", "proof", "review", "ticket", "banner", "support"] = Form(...), user=Depends(current_user), db: Session = Depends(session, scope="function")):
    if purpose in ["banner", "support"]:
        expect(user.role == "admin" or user.role == "staff" and "operations" in user.permissions, "无权上传运营素材", 403)
    if purpose == "product": expect(user.role in ["admin", "staff", "merchant"], "无权上传商品素材", 403)
    content = await file.read(20 * 1024 * 1024 + 1)
    expect(len(content) <= 20 * 1024 * 1024, "文件不得超过 20 MB", 413)
    mid = uuid4().hex
    if purpose in ["review", "ticket"] and len(content) >= 12 and content[4:8] == b"ftyp":
        validate_mp4(content)
        mime, suffix = "video/mp4", ".mp4"
    else:
        try:
            image = Image.open(BytesIO(content))
            expect(image.width * image.height <= 24_000_000, "图片像素过大")
            image = ImageOps.exif_transpose(image).convert("RGB")
            output = BytesIO(); image.save(output, format="JPEG", quality=90)
            content = output.getvalue(); mime, suffix = "image/jpeg", ".jpg"
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise HTTPException(400, "请上传可读取的图片或 MP4 视频")
    path = MEDIA_ROOT / (mid + suffix); path.write_bytes(content)
    db.add(Media(id=mid, owner_id=user.id, purpose=purpose, mime=mime, path=str(path)))
    return {"id": mid, "url": f"/api/media/{mid}", "mime": mime}


@router.get("/media/{media_id}")
def media_file(media_id: str, db: Session = Depends(session, scope="function"), user: User = Depends(current_user)):
    m = get(db, Media, media_id)
    permitted = m.owner_id == user.id or user.role == "admin"
    if user.role == "staff" and not permitted:
        needed = {'license': 'merchants', 'product': 'catalog', 'banner': 'operations',
                  'support': 'operations', 'review': 'operations', 'ticket': 'orders'}.get(m.purpose)
        permitted = bool(needed and needed in user.permissions)
        if m.purpose == 'proof':
            from .models import Procurement, Shipment
            permitted = ('procurement' in user.permissions and any(media_id in p.proof_media_ids for p in db.query(Procurement))) or ('orders' in user.permissions and any(media_id in s.proof_media_ids for s in db.query(Shipment)))
    if not permitted and m.purpose in ["product", "banner", "support", "review"]:
        return public_media(media_id, db)
    if not permitted and m.purpose == "proof":
        from .models import Shipment, Order
        for shipment in db.query(Shipment).join(Order).filter(Order.customer_id == user.id):
            if m.id in shipment.proof_media_ids: permitted = True; break
    expect(permitted, "无权访问附件", 403)
    return FileResponse(m.path, media_type=m.mime, headers={"X-Content-Type-Options": "nosniff"})
