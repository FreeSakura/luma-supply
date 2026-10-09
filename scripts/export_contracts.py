"""Export the API and database contracts from the actual 2.0 implementation."""
import argparse
import json
from pathlib import Path
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import sqlite, mysql
from backend.main import app
from backend.db import Base


def export(target):
    target = Path(target); target.mkdir(parents=True, exist_ok=True)
    (target / 'openapi.json').write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding='utf-8')
    for name, dialect in [('sqlite', sqlite.dialect()), ('mysql', mysql.dialect())]:
        statements = [str(CreateTable(t).compile(dialect=dialect)) + ';' for t in Base.metadata.sorted_tables]
        statements += [str(CreateIndex(i).compile(dialect=dialect)) + ';' for t in Base.metadata.sorted_tables for i in sorted(t.indexes, key=lambda i: i.name)]
        sql = '-- LumaSupply 2.1.0 generated from SQLAlchemy models\n\n' + '\n\n'.join(statements)
        (target / f'schema-{name}.sql').write_text('\n'.join(line.rstrip() for line in sql.splitlines()) + '\n', encoding='utf-8')
    print(f'Exported {len(Base.metadata.tables)} tables and OpenAPI to {target}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('local-only/contracts'))
    export(parser.parse_args().output)
