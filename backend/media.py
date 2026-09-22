from io import BytesIO
from pathlib import Path
from uuid import uuid4
from typing import Literal
from PIL import Image, UnidentifiedImageError
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
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


@router.post("/media", status_code=201)
async def upload(file: UploadFile = File(...), purpose: Literal["product", "query", "license", "proof", "review", "ticket", "banner", "support"] = Form(...), user=Depends(current_user), db: Session = Depends(session)):
    if purpose in ["banner", "support"]:
        expect(user.role == "admin" or user.role == "staff" and "operations" in user.permissions, "无权上传运营素材", 403)
    if purpose == "product": expect(user.role in ["admin", "staff", "merchant"], "无权上传商品素材", 403)
    content = await file.read(20 * 1024 * 1024 + 1)
    expect(len(content) <= 20 * 1024 * 1024, "文件不得超过 20 MB", 413)
    mid = uuid4().hex
    if purpose in ["review", "ticket"] and len(content) >= 12 and content[4:8] == b"ftyp":
        mime, suffix = "video/mp4", ".mp4"
    else:
        try:
            image = Image.open(BytesIO(content)); image.load()
            expect(image.width * image.height <= 24_000_000, "图片像素过大")
            image = image.convert("RGB")
            output = BytesIO(); image.save(output, format="JPEG", quality=90)
            content = output.getvalue(); mime, suffix = "image/jpeg", ".jpg"
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise HTTPException(400, "请上传可读取的图片或 MP4 视频")
    path = MEDIA_ROOT / (mid + suffix); path.write_bytes(content)
    db.add(Media(id=mid, owner_id=user.id, purpose=purpose, mime=mime, path=str(path)))
    return {"id": mid, "url": f"/api/media/{mid}", "mime": mime}


@router.get("/media/{media_id}")
def media_file(media_id: str, db: Session = Depends(session), user: User = Depends(current_user)):
    m = get(db, Media, media_id)
    permitted = m.owner_id == user.id or user.role == "admin"
    if user.role == "staff":
        needed = "merchants" if m.purpose == "license" else "orders"
        permitted = needed in user.permissions
    if m.purpose in ["product", "banner", "support", "review"]: permitted = True
    if not permitted and m.purpose == "proof":
        from .models import Shipment, Order
        for shipment in db.query(Shipment).join(Order).filter(Order.customer_id == user.id):
            if m.id in shipment.proof_media_ids: permitted = True; break
    expect(permitted, "无权访问附件", 403)
    return FileResponse(m.path, media_type=m.mime, headers={"X-Content-Type-Options": "nosniff"})
