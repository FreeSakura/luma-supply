"""Visual and interaction checks for the three-role UI, using disposable data."""
import argparse
import json
from datetime import timedelta
from pathlib import Path


def prepare():
    from scripts.browser_market_check import prepare as prepare_base
    prepare_base()
    from backend.db import SessionLocal, RUNTIME
    from backend.models import User, Merchant, Product, SKU, Media, Quote, Order, OrderLine, Procurement, now
    from backend.security import password_hash
    from backend.catalog import sku_view
    from backend.search import build_index
    from scripts.seed import draw_lamp, CATEGORIES, COLORS
    password=json.loads((RUNTIME/'browser-credentials.json').read_text(encoding='utf-8'))['password']
    with SessionLocal() as db:
        db.get(User,1).name='运营管理员';db.get(User,2).name='演示客户'
        db.add(User(id=3,username='fixture-merchant',name='云栖灯饰',role='merchant',password_hash=password_hash(password)))
        db.flush();db.add(Merchant(id=1,user_id=3,shop_name='云栖灯饰',status='approved'));db.flush()
        for index,pid in enumerate(range(126,102,-1)):
            kind=index%6;name,color=COLORS[(index//6)%4]
            product=db.get(Product,pid);sku=db.get(SKU,pid)
            product.name=f'{["弧光","拾野","云屿","暮色"][index//6]} {CATEGORIES[kind]}'
            product.title=f'{name} {CATEGORIES[kind]}';product.category=CATEGORIES[kind]
            sku.color=name;sku.specification=f'{18+index%3*6}W / {3000+index%2*1000}K'
            sku.attributes={'power_w':18+index%3*6,'cct_k':3000+index%2*1000}
            sku.initial_price=18900+index*1700;sku.size_mm='450 × 450'
            mid=f'ui-lamp-{pid}';path=RUNTIME/'media'/f'{mid}.png'
            draw_lamp(kind,color,index//6,path)
            db.add(Media(id=mid,owner_id=1,purpose='product',mime='image/png',path=str(path)))
            sku.images=[mid]
        db.flush()
        for index,status in enumerate(['approved','pending','rejected','approved']):
            db.add(Quote(id=index+1,merchant_id=1,sku_id=126-index,version=1,price=12500+index*2000,available_quantity=30,freight=1200,lead_days=3,status=status,reason='请补充准确的供货数量' if status=='rejected' else '',valid_until=now()+timedelta(days=-2 if index==3 else 30)))
        db.flush()
        for index,status in enumerate(['awaiting_confirmation','confirmed'],1):
            sku=db.get(SKU,126);snapshot=sku_view(db,sku);snapshot['product_name']=db.get(Product,126).name
            order=Order(number=f'UI-ORDER-{index:03}',customer_id=2,service_id=1,idempotency_key=f'ui-fixture-order-{index}',request_hash='ui-fixture',status=status,total=snapshot['price']*index,delivery_mode='pickup' if status=='confirmed' else None)
            db.add(order);db.flush()
            db.add(OrderLine(order_id=order.id,sku_id=126,quantity=index,unit_price=snapshot['price'],snapshot=snapshot))
            db.add(Procurement(order_id=order.id))
        db.commit();build_index(db)
    print('UI fixture ready: customer, supplier, admin; four offer states and two orders.')


def check(base_url,output):
    from playwright.sync_api import sync_playwright,expect
    from backend.db import RUNTIME
    password=json.loads((RUNTIME/'browser-credentials.json').read_text(encoding='utf-8'))['password']
    output.mkdir(parents=True,exist_ok=True)
    checks,errors=[],[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='msedge')
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)))
        def login(name):
            page.goto(base_url);page.wait_for_load_state('networkidle')
            page.get_by_label('用户名',exact=True).fill(name);page.get_by_label('密码',exact=True).fill(password)
            page.get_by_role('button',name='继续',exact=True).click()
            expect(page.locator('.workspace')).to_be_visible();page.wait_for_load_state('networkidle')
        def logout():
            page.get_by_role('button',name='退出登录',exact=True).click();expect(page.get_by_label('用户名',exact=True)).to_be_visible()
        try:
            login('fixture-customer')
            expect(page.locator('.product-card')).to_have_count(24)
            page.screenshot(path=str(output/'customer-desktop.png'))
            page.locator('.product-card').first.get_by_role('button',name='选规格',exact=True).click()
            expect(page.locator('.product-dialog')).to_have_attribute('role','dialog')
            page.locator('.product-dialog .close').focus();page.keyboard.press('Shift+Tab')
            assert page.evaluate('document.querySelector(".product-dialog").contains(document.activeElement)')
            page.keyboard.press('Escape');expect(page.locator('.product-dialog')).to_have_count(0)
            assert page.locator('.product-card').first.get_by_role('button',name='选规格',exact=True).evaluate('(el)=>el===document.activeElement')
            checks.append('Customer card opens variant directly; dialog traps focus, Esc closes and restores focus')
            page.keyboard.press('Control+k');expect(page.locator('.quick-navigator')).to_be_visible()
            page.get_by_label('搜索工作区',exact=True).fill('房间');page.keyboard.press('Enter')
            expect(page.locator('.planner-summary')).to_be_visible();expect(page.locator('.quick-navigator')).to_have_count(0)
            checks.append('Ctrl+K opens role-scoped quick navigation and Enter selects the page')
            page.set_viewport_size({'width':390,'height':844})
            expect(page.get_by_role('navigation',name='移动导航')).to_be_visible()
            page.get_by_role('navigation',name='移动导航').get_by_role('button',name='发现灯具',exact=True).click()
            expect(page.locator('.product-card')).to_have_count(24)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(output/'customer-mobile.png'))
            page.get_by_role('navigation',name='移动导航').get_by_role('button',name='我的订单',exact=True).click()
            expect(page.locator('tbody tr')).to_have_count(2)
            checks.append('Customer mobile bottom navigation keeps labeled destinations and no horizontal overflow')
            logout();page.set_viewport_size({'width':1440,'height':1000})
            login('fixture-merchant')
            expect(page.locator('.supplier-metrics')).to_be_visible()
            page.screenshot(path=str(output/'merchant-desktop.png'))
            page.locator('.supplier-metrics').get_by_role('button',name='需要修改',exact=False).click()
            expect(page.locator('tbody tr')).to_have_count(1)
            expect(page.locator('tbody tr')).to_contain_text('请补充准确的供货数量')
            expect(page.get_by_label('列表状态',exact=True)).to_have_value('rejected')
            page.get_by_label('列表状态',exact=True).select_option('expired')
            expect(page.locator('tbody tr')).to_have_count(1)
            expect(page.locator('tbody tr .badge')).to_have_text('已到期')
            checks.append('Supplier tasks open prefiltered own offers, including expired records')
            page.locator('.sidebar').get_by_role('button',name='供货选品',exact=True).click()
            expect(page.locator('.product-card')).to_have_count(24)
            page.locator('.product-card').first.get_by_role('button',name='立即报价',exact=True).click()
            expect(page.get_by_role('heading',name='提交供货报价',exact=True)).to_be_visible()
            page.get_by_label('供货单价 元',exact=True).fill('128')
            page.get_by_role('button',name='提交审核',exact=True).click()
            expect(page.locator('.dialog')).to_have_count(0)
            expect(page.locator('tbody tr')).to_have_count(5)
            checks.append('Supplier can submit an offer directly from a catalog card')
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_role('navigation',name='移动导航').get_by_role('button',name='供货选品',exact=True).click()
            expect(page.locator('.supplier-metrics')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(output/'merchant-mobile.png'))
            logout();page.set_viewport_size({'width':1440,'height':1000})
            login('fixture-admin')
            page.screenshot(path=str(output/'admin-desktop.png'))
            page.locator('.sidebar').get_by_role('button',name='销售订单',exact=True).click()
            expect(page.locator('tbody tr')).to_have_count(2)
            page.get_by_label('筛选当前列表',exact=True).fill('UI-ORDER-002')
            expect(page.locator('tbody tr')).to_have_count(1)
            page.get_by_role('button',name='清空列表搜索',exact=True).click()
            page.get_by_label('列表状态',exact=True).select_option('confirmed')
            expect(page.locator('tbody tr')).to_have_count(1)
            page.get_by_role('button',name='紧凑视图',exact=True).click()
            expect(page.locator('.workspace')).to_have_class('workspace role-admin is-compact')
            page.screenshot(path=str(output/'admin-orders.png'))
            checks.append('Admin list search, status filter and compact density work on real order data')
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_role('button',name='打开导航',exact=True).click()
            expect(page.locator('.sidebar')).to_have_class('sidebar is-open')
            page.locator('.sidebar').get_by_role('button',name='工作总览',exact=True).click()
            expect(page.locator('.sidebar')).not_to_have_class('sidebar is-open')
            expect(page.locator('.sidebar')).not_to_be_visible()
            expect(page.locator('.metric-grid')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(output/'admin-mobile.png'))
            checks.append('Admin mobile navigation drawer reaches the dashboard without squeezing the page')
        except Exception:
            page.screenshot(path=str(output/'failure.png'),full_page=True)
            print('Browser JavaScript errors:',json.dumps(errors,ensure_ascii=False))
            raise
        finally:
            browser.close()
    result={'checks':checks,'javascript_errors':errors,'passed':not errors,'native_validation':'source and JS checks only; no WeChat device claim'}
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not errors,errors
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--base-url',default='http://127.0.0.1:8015')
    parser.add_argument('--output',type=Path,default=Path('local-only/ui-browser'))
    args=parser.parse_args();prepare() if args.prepare else check(args.base_url,args.output)
