"""Restore a SQLite backup into a NEW directory and verify media and relations."""
import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from time import perf_counter


def restore(source, destination):
    start = perf_counter()
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents:
        raise ValueError('Restore destination must be outside the backup directory')
    if destination.exists():
        raise ValueError('Restore destination must not exist; keep the current data untouched')
    if not (source / 'lumasupply.db').is_file():
        raise ValueError('Backup database not found')
    with sqlite3.connect(source / 'lumasupply.db') as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup integrity check failed')
        media = db.execute('SELECT id, path FROM media').fetchall()
        missing = [mid for mid, path in media if not (source / 'media' / Path(path.replace('\\', '/')).name).is_file()]
        if missing:
            raise ValueError(f'Backup has {len(missing)} missing media files; restore cancelled')
    shutil.copytree(source, destination)
    with sqlite3.connect(destination / 'lumasupply.db') as db:
        for mid, path in media:
            db.execute('UPDATE media SET path=? WHERE id=?', (str(destination / 'media' / Path(path.replace('\\', '/')).name), mid))
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Restored foreign key verification failed; do not switch service')
        counts = {name: db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in ['users', 'orders', 'order_lines', 'inquiries', 'media']}
        totals = db.execute('SELECT COALESCE(SUM(total),0) FROM orders').fetchone()[0]
    result = {'destination': str(destination), 'counts': counts, 'order_total_cents': totals,
              'media_verified': len(media), 'integrity': 'ok', 'elapsed_seconds': perf_counter() - start}
    (destination / 'restore-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(restore(args.source, args.destination), ensure_ascii=False))
