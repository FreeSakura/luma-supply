from fastapi import HTTPException
from sqlalchemy import inspect


def get(db, cls, object_id):
    obj = db.get(cls, object_id)
    if not obj:
        raise HTTPException(404, "记录不存在 / Not found")
    return obj


def view(obj, exclude=()):
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs if c.key not in exclude}


def expect(condition, message, status=400):
    if not condition:
        raise HTTPException(status, message)
