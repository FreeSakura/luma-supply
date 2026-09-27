"""Catalog filtering checks; run --prepare only with a fresh disposable database."""
import argparse
import json
from pathlib import Path


def prepare():
    from scripts.browser_ui_check import prepare as base
    base()
    from backend.db import SessionLocal
    from backend.models import SKU
    with SessionLocal() as db:
        for sku in db.query(SKU):
            if sku.id != 1000:
                sku.initial_price = sku.id * 100
                sku.attributes = {'cct_k': 3000}
        db.get(SKU, 1).stock_status = 'unavailable'
        db.get(SKU, 1000).attributes = {'cct_k': 4000}
        db.commit()


def check(base_url, output):
    from playwright.sync_api import sync_playwright, expect
    from backend.db import RUNTIME
    password = json.loads((RUNTIME/'browser-credentials.json').read_text(encoding='utf-8'))['password']
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='msedge')
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        def login(name):
            page.goto(base_url); page.wait_for_load_state('networkidle')
            page.get_by_label('用户名', exact=True).fill(name)
            page.get_by_label('密码', exact=True).fill(password)
            page.get_by_role('button', name='继续', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(24)
        def budget(value):
            page.get_by_label('最高预算', exact=True).fill(value)
            page.get_by_label('最高预算', exact=True).press('Tab')
        try:
            login('fixture-customer')
            budget('3')
            expect(page.locator('.product-card')).to_have_count(3)
            page.get_by_label('仅有货', exact=True).check()
            expect(page.locator('.product-card')).to_have_count(2)
            page.get_by_label('商品排序', exact=True).select_option('price_desc')
            expect(page.locator('.product-card').first).to_contain_text('NEW-3')
            expect(page.locator('.catalog-pagination')).to_contain_text('2 / 2')
            checks.append('Budget-only browsing, available-only and price sort apply without text/image')
            page.screenshot(path=str(output/'budget-and-stock.png'))
            page.get_by_role('button', name='清除搜索', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(24)
            expect(page.get_by_label('最高预算', exact=True)).to_have_value('')
            expect(page.get_by_label('仅有货', exact=True)).not_to_be_checked()
            expect(page.get_by_label('商品排序', exact=True)).to_have_value('newest')
            page.get_by_label('商品排序', exact=True).select_option('price_asc')
            expect(page.locator('.product-card').first).to_contain_text('NEW-1')
            page.get_by_role('button', name='加载更多', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(48)
            codes = page.locator('.product-copy > small').all_text_contents()
            assert codes == [f'NEW-{i}' for i in range(1, 49)], codes
            checks.append('Global price order brings oldest product to page one and remains ordered across pages')
            page.get_by_label('灯具分类', exact=True).select_option('归档分类')
            page.get_by_label('色温筛选', exact=True).select_option('4000')
            budget('50')
            expect(page.locator('.product-card')).to_have_count(0)
            budget('100')
            expect(page.locator('.product-card')).to_have_count(1)
            expect(page.locator('.product-card')).to_contain_text('ARCHIVE-UNIQUE')
            expect(page.locator('.product-card')).to_contain_text('98.76')
            page.get_by_role('button', name='选规格', exact=True).click()
            expect(page.locator('.detail-copy select')).to_have_value('1000')
            expect(page.locator('.detail-price')).to_contain_text('98.76')
            page.keyboard.press('Escape')
            checks.append('Combined CCT/budget filters select one eligible SKU and preserve detail price')
            page.get_by_role('button', name='清除搜索', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(24)
            budget('0')
            expect(page.locator('.product-card')).to_have_count(0)
            page.get_by_role('button', name='清除搜索', exact=True).click()
            expect(page.locator('.product-card')).to_have_count(24)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.get_by_label('商品排序', exact=True).select_option('price_desc')
            expect(page.locator('.product-card').first).to_contain_text('NEW-126')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(output/'mobile-sort.png'))
            checks.append('Zero budget is applied; reset restores filters; mobile sort has no horizontal overflow')
            page.get_by_role('button', name='清除搜索', exact=True).click()
            page.locator('.search-main > input').fill('ARCHIVE-UNIQUE')
            page.get_by_role('button', name='寻找灯具', exact=True).click()
            expect(page.get_by_label('商品排序', exact=True)).to_have_value('relevance')
            expect(page.get_by_label('商品排序', exact=True)).to_be_disabled()
            expect(page.locator('.product-card').first).to_contain_text('ARCHIVE-UNIQUE')
            checks.append('Multimodal/text ranked results are explicitly labeled relevance, not price order')
            page.get_by_role('button', name='退出登录', exact=True).click()
            page.set_viewport_size({'width': 1440, 'height': 1000})
            login('fixture-merchant')
            page.get_by_label('灯具分类', exact=True).select_option('归档分类')
            page.get_by_label('色温筛选', exact=True).select_option('4000')
            budget('100')
            expect(page.locator('.product-card')).to_have_count(1)
            page.get_by_role('button', name='立即报价', exact=True).click()
            expect(page.locator('.dialog')).to_contain_text('ARCHIVE-UNIQUE')
            checks.append('Merchant sourcing shares the same eligible variant and opens its quote form')
        except Exception:
            page.screenshot(path=str(output/'failure.png'), full_page=True)
            raise
        finally:
            browser.close()
    result = {'checks': checks, 'javascript_errors': errors, 'passed': not errors}
    (output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not errors, errors
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--base-url', default='http://127.0.0.1:8018')
    parser.add_argument('--output', type=Path, default=Path('local-only/filter-browser'))
    args = parser.parse_args()
    prepare() if args.prepare else check(args.base_url, args.output)
