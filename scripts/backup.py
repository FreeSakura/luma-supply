"""Consistent SQLite backup plus immutable media/index copy; never overwrite source."""
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
from backend.db import RUNTIME, ROOT, DATABASE_URL


def run():
    if not DATABASE_URL.startswith('sqlite:///'):raise SystemExit('Use the database vendor backup tool for non-SQLite deployments.')
    target=ROOT/'local-only'/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f');target.mkdir(parents=True)
    with sqlite3.connect(DATABASE_URL.removeprefix('sqlite:///')) as source,sqlite3.connect(target/'lumasupply.db') as dest:source.backup(dest)
    for name in ['media','index']:
        if (RUNTIME/name).exists():shutil.copytree(RUNTIME/name,target/name)
    with sqlite3.connect(target/'lumasupply.db') as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        print('Backup verified:',target,'orders:',conn.execute('SELECT count(*) FROM orders').fetchone()[0])
    return target


if __name__=='__main__':run()
