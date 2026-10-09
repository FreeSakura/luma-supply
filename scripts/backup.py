"""Consistent SQLite backup plus immutable media/index copy; never overwrite source."""
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
import json
import hashlib
from contextlib import closing
from backend.db import RUNTIME, ROOT, DATABASE_URL
from backend.filelocks import try_lock


def run():
    if not DATABASE_URL.startswith('sqlite:///'):raise SystemExit('Use the database vendor backup tool for non-SQLite deployments.')
    target=ROOT/'local-only'/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f');target.mkdir(parents=True)
    marker=target/'.backup-in-progress';marker.write_text('2.1',encoding='utf-8')
    with closing(sqlite3.connect(DATABASE_URL.removeprefix('sqlite:///'))) as source,closing(sqlite3.connect(target/'lumasupply.db')) as dest:source.backup(dest)
    (target/'media').mkdir()
    with closing(sqlite3.connect(target/'lumasupply.db')) as conn:
        for (name,) in conn.execute('SELECT path FROM media'):
            shutil.copy2(name,target/'media'/Path(name).name)
    index_state='rebuild_required'
    if (RUNTIME/'index').exists():
        with try_lock(RUNTIME/'index/.publisher.lock') as locked:
            if locked:
                shutil.copytree(RUNTIME/'index',target/'index',ignore=shutil.ignore_patterns('*.tmp','.publisher.lock'))
                index_state='copied'
    with closing(sqlite3.connect(target/'lumasupply.db')) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        print('Backup verified:',target,'orders:',conn.execute('SELECT count(*) FROM orders').fetchone()[0])
    files=[{'path':p.relative_to(target).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(target.rglob('*')) if p.is_file() and p!=marker]
    (target/'backup-manifest.json').write_text(json.dumps({'version':'2.1.0','index':index_state,'files':files},indent=2),encoding='utf-8')
    marker.unlink()
    return target


if __name__=='__main__':run()
