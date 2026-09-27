"""Room-list editing and inquiry preview checks using an isolated database."""
import argparse
import json
from pathlib import Path


def prepare():
    from scripts.browser_market_check import prepare as base
    base()
    from backend.db import SessionLocal
    from backend.models import Wishlist
    with SessionLocal() as db:
        db.add(Wishlist(user_id=2, sku_id=1000, room='卧室', quantity=1))
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
        def room(name):
            return page.locator('.room-planner > section.panel').filter(has=page.get_by_role('heading', name=name, exact=True))
        try:
            page.goto(base_url); page.wait_for_load_state('networkidle')
            page.get_by_label('用户名', exact=True).fill('fixture-customer')
            page.get_by_label('密码', exact=True).fill(password)
            page.get_by_role('button', name='继续', exact=True).click()
            page.locator('.sidebar').get_by_role('button', name='房间清单', exact=True).click()
            expect(page.locator('.planner-line')).to_have_count(3)
            page.get_by_label('选择 NEW-2', exact=True).uncheck()
            room('客厅').get_by_role('button', name='编辑 ARCHIVE-UNIQUE', exact=True).click()
            page.get_by_label('采购数量', exact=True).fill('9')
            page.keyboard.press('Escape')
            expect(room('客厅')).to_contain_text('数量 × 2')
            expect(page.locator('.planner-summary')).to_contain_text('296.28')
            checks.append('Editing is a draft: cancel leaves quantities and selected totals unchanged')
            room('客厅').get_by_role('button', name='编辑 ARCHIVE-UNIQUE', exact=True).click()
            page.get_by_label('房间名称', exact=True).fill('卧室')
            page.get_by_role('button', name='保存清单修改', exact=True).click()
            expect(page.locator('.wish-editor .error')).to_contain_text('目标房间已有此规格')
            expect(page.get_by_label('房间名称', exact=True)).to_have_value('卧室')
            expect(page.locator('.planner-line')).to_have_count(3)
            checks.append('Duplicate room/SKU returns a visible conflict and retains the editable draft')
            page.get_by_label('房间名称', exact=True).fill('书房')
            page.get_by_label('采购数量', exact=True).fill('4')
            page.get_by_label('清单备注', exact=True).fill('靠窗阅读区，保留安装空间')
            page.get_by_label('关注供货变化', exact=True).check()
            page.get_by_role('button', name='保存清单修改', exact=True).click()
            expect(page.locator('.wish-editor')).to_have_count(0)
            expect(room('书房')).to_contain_text('数量 × 4')
            expect(room('书房')).to_contain_text('靠窗阅读区，保留安装空间')
            expect(page.get_by_label('选择 NEW-2', exact=True)).not_to_be_checked()
            expect(page.locator('.planner-summary')).to_contain_text('493.80')
            page.screenshot(path=str(output/'room-list.png'), full_page=True)
            checks.append('Saved move/quantity/note updates totals while keeping other selection choices')
            def fail_save(route):
                if route.request.method == 'PATCH': route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': '演示保存失败，请重试'}))
                else: route.continue_()
            page.route('**/api/wishlist/*', fail_save)
            room('书房').get_by_role('button', name='编辑 ARCHIVE-UNIQUE', exact=True).click()
            page.get_by_label('采购数量', exact=True).fill('8')
            page.get_by_role('button', name='保存清单修改', exact=True).click()
            expect(page.locator('.wish-editor .error')).to_contain_text('演示保存失败')
            expect(room('书房')).to_contain_text('数量 × 4')
            expect(page.locator('.planner-summary')).to_contain_text('493.80')
            page.keyboard.press('Escape'); page.unroute('**/api/wishlist/*', fail_save)
            checks.append('Failed save keeps server-confirmed quantity/total and preserves draft for retry')
            page.set_viewport_size({'width': 390, 'height': 844})
            room('书房').get_by_role('button', name='编辑 ARCHIVE-UNIQUE', exact=True).click()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(output/'mobile-editor.png'))
            page.keyboard.press('Escape')
            room('书房').get_by_role('button', name='只选这个房间', exact=True).click()
            page.get_by_role('button', name='清单一键询价', exact=True).click()
            page.get_by_label('商品预算 元（可选）', exact=True).fill('100')
            delayed = []
            page.route('**/api/inquiries/preview', lambda route: delayed.append(route))
            page.get_by_role('button', name='预览询价清单', exact=True).click()
            page.get_by_label('商品预算 元（可选）', exact=True).fill('500')
            assert len(delayed) == 1
            response = delayed[0].fetch(); delayed[0].fulfill(response=response)
            expect(page.locator('.inquiry-composer .error')).to_contain_text('需求已修改，请重新预览')
            expect(page.locator('.inquiry-preview')).to_have_count(0)
            page.unroute('**/api/inquiries/preview')
            checks.append('Mobile editor fits; late preview for older requirements cannot enable submission')
            page.get_by_role('button', name='预览询价清单', exact=True).click()
            expect(page.locator('.inquiry-preview')).to_contain_text('395.04')
            page.get_by_role('button', name='确认发送询价', exact=True).click()
            expect(page.locator('.inquiry-composer')).to_have_count(0)
            page.get_by_role('button', name='查看与沟通', exact=True).click()
            expect(page.locator('.inquiry-dialog')).to_contain_text('书房 × 4')
            expect(page.locator('.inquiry-dialog')).to_contain_text('靠窗阅读区，保留安装空间')
            checks.append('Fresh preview submits the saved edited item with its room/quantity/note snapshot')
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
    parser.add_argument('--base-url', default='http://127.0.0.1:8020')
    parser.add_argument('--output', type=Path, default=Path('local-only/wishlist-browser'))
    args = parser.parse_args()
    prepare() if args.prepare else check(args.base_url, args.output)
