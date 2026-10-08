"""Small additive 1.7 -> 2.0 migration; run once before accepting requests."""
from sqlalchemy import inspect, text


def upgrade(engine):
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "wishlist" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("wishlist")}
            if "version" not in columns:
                connection.execute(text("ALTER TABLE wishlist ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))


if __name__ == "__main__":
    from .db import Base, engine
    from . import models  # register all models
    Base.metadata.create_all(engine)
    upgrade(engine)
    print("Schema ready for LumaSupply 2.0.0")
