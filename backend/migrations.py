"""Additive upgrades; preserve business records and require fresh management auth."""
from sqlalchemy import inspect, text


def upgrade(engine):
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "wishlist" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("wishlist")}
            if "version" not in columns:
                connection.execute(text("ALTER TABLE wishlist ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))
        if "sessions" in inspector.get_table_names():
            columns = {c['name'] for c in inspector.get_columns('sessions')}
            for name, definition in [('last_seen_at', 'DATETIME'), ('authenticated_at', 'DATETIME'),
                                     ('mfa_verified', 'BOOLEAN NOT NULL DEFAULT 0')]:
                if name not in columns:
                    connection.execute(text(f'ALTER TABLE sessions ADD COLUMN {name} {definition}'))
            connection.execute(text('UPDATE sessions SET last_seen_at=CURRENT_TIMESTAMP WHERE last_seen_at IS NULL'))
            connection.execute(text("UPDATE sessions SET authenticated_at='2000-01-01 00:00:00' WHERE authenticated_at IS NULL"))
        from .db import Base
        tables = set(inspector.get_table_names())
        for table in Base.metadata.tables.values():
            if table.name in tables:
                for index in table.indexes: index.create(connection, checkfirst=True)


if __name__ == "__main__":
    from .db import Base, engine
    from . import models  # register all models
    Base.metadata.create_all(engine)
    upgrade(engine)
    print("Schema ready for LumaSupply 2.1.0")
