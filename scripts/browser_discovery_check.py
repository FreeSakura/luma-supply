"""Exercise discovery with an isolated 126-product fixture (requires Playwright).

Set DATA_DIR and DATABASE_URL to a fresh disposable directory, run --prepare,
start uvicorn against that same environment, then run with --base-url.
This script never resets an existing database or uses production credentials.
"""
import argparse
import json
import os
import secrets
from pathlib import Path


def prepare():
    if not os.getenv('DATA_DIR') or not os.getenv('DATABASE_URL'):
        raise SystemExit('Set explicit disposable DATA_DIR and DATABASE_URL first.')
    from PIL import Image
    from backend.db import Base, engine, SessionLocal, RUNTIME
    from backend.models import User, Product, SKU, Media
    from backend.security import password_hash
    from backend.search import build_index
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(User).count(): raise SystemExit('Fixture requires an empty database.')
        password = secrets.token_urlsafe(18)
        db.add_all([User(id=1, username='fixture-admin', name='Fixture admin', role='admin', password_hash=password_hash(password)),
                    User(id=2, username='fixture-customer', name='Fixture customer', role='customer', password_hash=password_hash(password))])
        db.flush()
        path = RUNTIME / 'lamp.png'
        Image.new('RGB', (200, 200), '#d0b477').save(path)
        db.add(Media(id='fixture-lamp', owner_id=1, purpose='product', mime='image/png', path=str(path)))
        for i in range(1, 127):
            db.add(Product(id=i, name='归档灯具' if i == 1 else f'扩容灯具 {i}', title='ARCHIVE-UNIQUE' if i == 1 else '新品', category='归档分类' if i == 1 else '扩容分类'))
            db.flush()
            db.add(SKU(id=i, product_id=i, code=f'NEW-{i}', initial_price=1000,
                       images=[] if i == 1 else ['fixture-lamp']))
        # The matching SKU costs more than the SPU minimum, and is outside page 1.
        db.add(SKU(id=1000, product_id=1, code='ARCHIVE-UNIQUE', initial_price=9876,
                   specification='4000K', images=['fixture-lamp']))
        db.commit()
        build_index(db)
    (RUNTIME / 'browser-credentials.json').write_text(json.dumps({'password': password}), encoding='utf-8')
    print('Prepared isolated catalog: 126 products, 127 SKUs.')


def check(base_url, output):
    from playwright.sync_api import sync_playwright, expect
    from backend.db import RUNTIME
    password = json.loads((RUNTIME / 'browser-credentials.json').read_text(encoding='utf-8'))['password']
    output.mkdir(parents=True, exist_ok=True)
    errors, checks, requests = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='msedge')
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: requests.append(r.url))
        try:
            page.goto(base_url)
            page.wait_for_load_state('networkidle')
            page.get_by_label('用户名', exact=True).fill('fixture-customer')
            page.get_by_label('密码', exact=True).fill(password)
            page.get_by_role('button', name='继续', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(24)
            expect(page.locator('.catalog-pagination')).to_contain_text('24 / 126')
            expect(page.locator('.hero-image img')).to_have_attribute('src', '/api/public-media/fixture-lamp')
            page.get_by_role('button', name='加载更多', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(48)
            expect(page.locator('.catalog-pagination')).to_contain_text('48 / 126')
            checks.append('126-product catalog loads 24 then 48 unique cards')

            page.locator('.category-pills').get_by_role('button', name='归档分类', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(1)
            expect(page.locator('.catalog-pagination')).to_contain_text('1 / 1')
            expect(page.get_by_role('button', name='加载更多', exact=True)).to_have_count(0)
            checks.append('Category filters server-side and resets pagination')

            page.locator('.category-pills').get_by_role('button', name='全部', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(24)
            requests.clear()
            page.locator('.search-main > input').fill('ARCHIVE-UNIQUE')
            page.get_by_role('button', name='寻找灯具', exact=True).click()
            expect(page.locator('.product-card').first).to_contain_text('ARCHIVE-UNIQUE')
            expect(page.locator('.product-card').first).to_contain_text('98.76')
            assert not any('/api/catalog/products/' in url for url in requests)
            checks.append('Search includes old SKU outside initial 100 without per-hit detail requests')
            page.screenshot(path=str(output / 'search-result.png'))
            page.locator('.product-card').first.click()
            expect(page.locator('.detail-copy select')).to_have_value('1000')
            expect(page.locator('.detail-price')).to_contain_text('98.76')
            page.locator('.product-dialog').get_by_role('button', name='加入对比', exact=True).click()
            page.locator('.product-dialog .close').click()
            page.get_by_role('button', name='开始对比', exact=False).click()
            expect(page.locator('.dialog')).to_contain_text('ARCHIVE-UNIQUE')
            expect(page.locator('.dialog')).to_contain_text('98.76')
            page.locator('.dialog .close').click()
            checks.append('Matched variant, displayed price and compare selection stay consistent')

            page.get_by_role('button', name='清除搜索', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(24)
            expect(page.locator('.catalog-pagination')).to_contain_text('24 / 126')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(output / 'mobile-pagination.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            checks.append('Clear search restores page one; 390px layout does not overflow')
            # Rapid category changes must not append an older page into the newer filter.
            page.locator('.category-pills').get_by_role('button', name='扩容分类', exact=True).click()
            page.locator('.category-pills').get_by_role('button', name='归档分类', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(1)
            expect(page.locator('.product-card')).to_contain_text('归档灯具')
            checks.append('Latest category selection wins over in-flight requests')
        except Exception:
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
            raise
        finally:
            browser.close()
    result = {'checks': checks, 'javascript_errors': errors, 'passed': not errors}
    (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not errors, errors
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--base-url', default='http://127.0.0.1:8012')
    parser.add_argument('--output', type=Path, default=Path('local-only/discovery-browser'))
    args = parser.parse_args()
    prepare() if args.prepare else check(args.base_url, args.output)
