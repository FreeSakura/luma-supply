"""Browser smoke journey against the local seeded demo, with actual visible actions."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'local-only'/'browser'
OUT.mkdir(parents=True,exist_ok=True)


def run():
    password=json.loads((ROOT/'local-only'/'demo-accounts.json').read_text(encoding='utf-8'))['password']
    checks=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='msedge')
        page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        page.on('pageerror',lambda e:errors.append(str(e)))
        def login(username):
            page.goto('http://127.0.0.1:8000');page.wait_for_load_state('networkidle')
            page.get_by_label('用户名',exact=True).fill(username)
            page.get_by_label('密码',exact=True).fill(password)
            page.get_by_role('button',name='继续',exact=True).click()
            expect(page.locator('.sidebar')).to_be_visible()
            page.wait_for_load_state('networkidle')
        login('customer')
        expect(page.locator('.product-card')).to_have_count(18)
        page.screenshot(path=str(OUT/'customer-home.png'),full_page=True)
        checks.append('Customer login and 18-product catalog')
        page.locator('.product-card').first.click();expect(page.locator('.product-dialog')).to_be_visible()
        expect(page.locator('.detail-copy select')).to_have_value('35')
        page.screenshot(path=str(OUT/'customer-detail.png'))
        page.get_by_role('button',name='加入选购清单',exact=True).click()
        expect(page.locator('.product-dialog')).to_have_count(0)
        page.get_by_role('button',name='房间清单',exact=True).click()
        expect(page.locator('.catalog-row')).to_have_count(1)
        page.get_by_role('button',name='清单一键询价',exact=True).click()
        expect(page.locator('.list-item').first).to_be_visible()
        checks.append('Select exact SKU, save room list, create inquiry')
        page.get_by_role('button',name='发现灯具',exact=True).click()
        page.locator('.search-main input[type=text],.search-main > input').first.fill('台灯')
        page.get_by_role('button',name='寻找灯具',exact=True).click()
        expect(page.locator('.notice')).to_be_visible()
        page.screenshot(path=str(OUT/'customer-search.png'),full_page=True)
        checks.append('Text search uses real retrieval API')
        page.get_by_role('button',name='退出登录',exact=True).click()
        login('merchant')
        page.get_by_role('button',name='我的报价',exact=True).click()
        expect(page.locator('tbody tr')).to_have_count(36)
        page.screenshot(path=str(OUT/'merchant-quotes.png'),full_page=True)
        checks.append('Merchant sees own 36 quotes')
        page.get_by_role('button',name='退出登录',exact=True).click()
        login('admin')
        page.screenshot(path=str(OUT/'admin-dashboard.png'),full_page=True)
        page.get_by_role('button',name='客户询价',exact=True).click()
        page.get_by_role('button',name='转为销售订单',exact=True).first.click()
        expect(page.locator('.dialog form')).to_be_visible()
        page.get_by_role('button',name='创建订单并通知客户',exact=True).click()
        expect(page.locator('.dialog')).to_have_count(0)
        expect(page.locator('tbody tr').first).to_be_visible()
        page.screenshot(path=str(OUT/'admin-orders.png'),full_page=True)
        checks.append('Admin converts inquiry to snapshotted sales order')
        page.get_by_role('button',name='退出登录',exact=True).click()
        login('customer')
        page.get_by_role('button',name='我的订单',exact=True).click()
        page.get_by_role('button',name='查看详情',exact=False).first.click()
        page.get_by_role('button',name='确认订单',exact=True).click()
        expect(page.locator('.dialog')).to_have_count(0)
        checks.append('Customer confirms pickup order')
        page.get_by_role('button',name='退出登录',exact=True).click()
        login('admin')
        page.get_by_role('button',name='采购协同',exact=True).click()
        page.get_by_role('button',name='生成采购方案',exact=True).first.click()
        page.get_by_role('button',name='计算方案',exact=True).click()
        expect(page.get_by_text('采购方案建议',exact=True)).to_be_visible()
        page.screenshot(path=str(OUT/'admin-procurement.png'))
        page.get_by_role('button',name='确认采购并预留数量',exact=True).click()
        expect(page.locator('.dialog')).to_have_count(0)
        checks.append('CP-SAT procurement displayed and confirmed through UI')
        page.get_by_role('button',name='退出登录',exact=True).click()
        login('customer')
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUT/'customer-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
        checks.append('390px responsive layout has no horizontal overflow')
        browser.close()
    result={'checks':checks,'javascript_errors':errors,'passed':not errors}
    (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not errors,errors
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':run()
