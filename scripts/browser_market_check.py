"""Verify the research-derived room planning workflow in a disposable database."""
import argparse
import json
from datetime import timedelta
from pathlib import Path


def prepare():
    from scripts.browser_discovery_check import prepare as seed_fixture
    seed_fixture()
    from backend.db import SessionLocal
    from backend.models import SKU, Wishlist
    with SessionLocal() as db:
        warm = db.get(SKU, 1000)
        warm.attributes = {'power_w': 18, 'cct_k': 3000}
        warm.specification = '18W / 3000K'
        warm.size_mm = '300 × 300'
        db.get(SKU, 1).attributes = {'cct_k': 4000}
        db.get(SKU, 2).attributes = {'cct_k': 4000}
        db.add_all([Wishlist(user_id=2, sku_id=1000, room='客厅', quantity=2),
                    Wishlist(user_id=2, sku_id=2, room='卧室', quantity=3)])
        db.commit()


def check(base_url, output):
    from playwright.sync_api import sync_playwright, expect
    from backend.db import RUNTIME
    from backend.models import now
    password = json.loads((RUNTIME / 'browser-credentials.json').read_text(encoding='utf-8'))['password']
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='msedge')
        page = browser.new_page(viewport={'width':1440, 'height':1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        def login(username):
            page.goto(base_url); page.wait_for_load_state('networkidle')
            page.get_by_label('用户名', exact=True).fill(username)
            page.get_by_label('密码', exact=True).fill(password)
            page.get_by_role('button', name='继续', exact=True).click()
            expect(page.locator('.sidebar')).to_be_visible()
        try:
            login('fixture-customer')
            page.get_by_label('色温筛选', exact=True).select_option('3000')
            expect(page.locator('.product-card')).to_have_count(1)
            expect(page.locator('.product-card')).to_contain_text('ARCHIVE-UNIQUE')
            expect(page.locator('.product-card')).to_contain_text('98.76')
            page.locator('.lighting-guide summary').click()
            expect(page.locator('.lighting-guide')).to_contain_text('不能直接代表亮度')
            checks.append('Actual CCT facet selects matching SKU with readable parameter guidance')
            page.get_by_role('button', name='房间清单', exact=True).click()
            expect(page.locator('.planner-line')).to_have_count(2)
            expect(page.locator('.planner-summary')).to_contain_text('227.52')
            page.locator('.room-planner > section.panel').filter(
                has=page.get_by_role('heading', name='客厅', exact=True)
            ).get_by_role('button', name='只选这个房间', exact=True).click()
            expect(page.locator('.planner-summary')).to_contain_text('197.52')
            expect(page.get_by_label('选择 NEW-2', exact=True)).not_to_be_checked()
            page.screenshot(path=str(output / 'room-planner.png'), full_page=True)
            checks.append('Room-only selection changes amount and excludes unselected bedroom')
            page.get_by_role('button', name='清单一键询价', exact=True).click()
            page.get_by_label('项目名称', exact=True).fill('客厅改造研究用例')
            page.get_by_label('商品预算 元（可选）', exact=True).fill('100')
            deadline = (now() + timedelta(days=14)).date().isoformat()
            page.get_by_label('期望到货日期', exact=True).fill(deadline)
            page.get_by_label('配送城市或区域', exact=True).fill('上海')
            page.get_by_label('可以向我推荐替代款，须经我确认', exact=True).check()
            page.get_by_role('button', name='预览询价清单', exact=True).click()
            expect(page.locator('.inquiry-preview')).to_contain_text('97.52')
            expect(page.get_by_role('button', name='确认发送询价', exact=True)).to_be_enabled()
            page.screenshot(path=str(output / 'inquiry-preview.png'))
            checks.append('Structured preview shows over-budget difference without promising delivery')
            page.get_by_role('button', name='确认发送询价', exact=True).click()
            expect(page.locator('.inquiry-composer')).to_have_count(0)
            expect(page.locator('main')).to_contain_text('客厅改造研究用例')
            expect(page.locator('main')).to_contain_text('197.52')
            checks.append('Only chosen room is submitted with a reference snapshot')
            page.get_by_role('button', name='退出登录', exact=True).click()
            login('fixture-admin')
            page.get_by_role('button', name='客户询价', exact=True).click()
            expect(page.locator('main')).to_contain_text('期望到货')
            expect(page.locator('main')).to_contain_text('上海')
            expect(page.locator('main')).to_contain_text('可协商替代款')
            page.get_by_role('button', name='转为销售订单', exact=True).first.click()
            expect(page.locator('.order-entry input').last).to_have_value('98.76')
            assert '客户商品预算' in page.locator('.dialog textarea').input_value()
            page.get_by_role('button', name='创建订单并通知客户', exact=True).click()
            expect(page.locator('.dialog')).to_have_count(0)
            expect(page.locator('tbody tr').first).to_contain_text('197.52')
            checks.append('Service sees buyer brief and converts snapshot to reviewable order')
            page.get_by_role('button', name='退出登录', exact=True).click()
            login('fixture-customer')
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_role('button', name='房间清单', exact=True).click()
            expect(page.locator('.planner-line')).to_have_count(2)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(output / 'mobile-planner.png'), full_page=True)
            checks.append('Mobile room planner is usable without horizontal overflow')
        except Exception:
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
            raise
        finally:
            browser.close()
    result = {'checks':checks, 'javascript_errors':errors, 'passed':not errors}
    (output / 'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not errors, errors
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--base-url',default='http://127.0.0.1:8013')
    parser.add_argument('--output',type=Path,default=Path('local-only/market-browser'))
    args=parser.parse_args()
    prepare() if args.prepare else check(args.base_url,args.output)
