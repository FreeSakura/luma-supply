"""Verify inquiry collaboration using the disposable market-check fixture."""
import argparse
import json
from pathlib import Path


def check(base_url, output):
    import httpx
    from playwright.sync_api import sync_playwright, expect
    from backend.db import RUNTIME
    password=json.loads((RUNTIME/'browser-credentials.json').read_text(encoding='utf-8'))['password']
    output.mkdir(parents=True,exist_ok=True)
    with httpx.Client(base_url=base_url) as client:
        auth=client.post('/api/auth/login',json={'username':'fixture-customer','password':password}).json()
        headers={'Authorization':'Bearer '+auth['token']}
        wishlist=client.get('/api/wishlist',headers=headers).json()
        ids=[]
        for title in ['沟通后转单','客户撤回样例','客服关闭样例']:
            r=client.post('/api/inquiries',headers=headers,json={'wishlist_ids':[w['id'] for w in wishlist],'requirements':{'project_name':title}})
            r.raise_for_status();ids.append(r.json()['id'])
    checks,errors=[],[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='msedge')
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)))
        def login(name):
            page.goto(base_url);page.wait_for_load_state('networkidle')
            page.get_by_label('用户名',exact=True).fill(name)
            page.get_by_label('密码',exact=True).fill(password)
            page.get_by_role('button',name='继续',exact=True).click()
            expect(page.locator('.sidebar')).to_be_visible()
            page.get_by_role('button',name='客户询价' if name=='fixture-admin' else '我的询价',exact=True).click()
            expect(page.locator('.inquiry-row').first).to_be_visible()
        def row(i):
            return page.locator('.inquiry-row').filter(has=page.get_by_text(f'INQUIRY #{ids[i]}',exact=True))
        def open_inquiry(i):
            row(i).get_by_role('button',name='查看与沟通',exact=True).click()
            expect(page.locator('.inquiry-dialog')).to_be_visible()
        def close_dialog():
            page.get_by_role('button',name='关闭询价详情',exact=True).click()
        def logout():
            page.get_by_role('button',name='退出登录',exact=True).click()
            expect(page.get_by_label('用户名',exact=True)).to_be_visible()
        try:
            login('fixture-customer')
            open_inquiry(0)
            page.get_by_label('补充需求或问题',exact=True).fill('请核对安装尺寸，先不要替换规格。')
            page.get_by_role('button',name='发送信息',exact=True).click()
            expect(page.locator('.inquiry-timeline')).to_contain_text('先不要替换规格')
            close_dialog();checks.append('Customer adds a message to the inquiry activity history')
            logout()
            login('fixture-admin');open_inquiry(0)
            expect(page.locator('.inquiry-timeline')).to_contain_text('先不要替换规格')
            page.get_by_label('回复客户',exact=True).fill('已记录，按原规格报价，安装尺寸会再向商家核对。')
            page.get_by_role('button',name='发送信息',exact=True).click()
            expect(page.locator('.inquiry-timeline')).to_contain_text('按原规格报价')
            page.screenshot(path=str(output/'conversation.png'))
            close_dialog();checks.append('Service sees customer context and replies in the same timeline')
            open_inquiry(2)
            page.get_by_role('button',name='关闭本次询价',exact=True).click()
            page.get_by_label('处理原因',exact=True).fill('本次安装条件暂不满足，请调整清单后重新询价。')
            page.get_by_role('button',name='确认关闭',exact=True).click()
            expect(page.locator('.inquiry-dialog > .badge')).to_have_text('已关闭')
            expect(page.locator('.inquiry-timeline')).to_contain_text('安装条件暂不满足')
            close_dialog();checks.append('Service closes an inquiry with a reason and retained history')
            logout()
            login('fixture-customer');open_inquiry(1)
            page.get_by_role('button',name='撤回本次询价',exact=True).click()
            page.get_by_label('处理原因',exact=True).fill('预算调整，本次暂不采购。')
            page.get_by_role('button',name='确认撤回',exact=True).click()
            expect(page.locator('.inquiry-dialog > .badge')).to_have_text('已撤回')
            expect(page.get_by_role('button',name='发送信息',exact=True)).to_have_count(0)
            close_dialog();page.get_by_label('询价状态筛选',exact=True).select_option('withdrawn')
            expect(page.locator('.inquiry-row')).to_have_count(1)
            expect(row(1)).to_be_visible();checks.append('Customer withdraws; terminal inquiry is read-only and filterable')
            page.get_by_label('询价状态筛选',exact=True).select_option('closed')
            open_inquiry(2);expect(page.locator('.inquiry-timeline')).to_contain_text('安装条件暂不满足');close_dialog()
            logout()
            login('fixture-admin')
            row(0).get_by_role('button',name='转为销售订单',exact=True).click()
            page.get_by_role('button',name='创建订单并通知客户',exact=True).click()
            expect(page.locator('.dialog')).to_have_count(0)
            logout()
            login('fixture-customer');open_inquiry(0)
            expect(page.locator('.inquiry-dialog > .badge')).to_have_text('已转订单')
            expect(page.locator('.inquiry-timeline')).to_contain_text('已创建销售订单')
            page.get_by_role('button',name='查看关联订单',exact=True).click()
            expect(page.get_by_role('heading',name='订单详情',exact=True)).to_be_visible()
            page.locator('.dialog .close').click()
            checks.append('Order conversion is recorded and the customer can open the linked order')
            page.set_viewport_size({'width':390,'height':844});open_inquiry(0)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(output/'mobile-history.png'))
            checks.append('Mobile inquiry history fits a 390px viewport')
        except Exception:
            page.screenshot(path=str(output/'failure.png'),full_page=True)
            raise
        finally:
            browser.close()
    result={'checks':checks,'javascript_errors':errors,'passed':not errors}
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not errors,errors
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--base-url',default='http://127.0.0.1:8014')
    parser.add_argument('--output',type=Path,default=Path('local-only/inquiry-browser'))
    args=parser.parse_args()
    if args.prepare:
        from scripts.browser_market_check import prepare
        prepare()
    else:check(args.base_url,args.output)
