"""Build legacy role projects and configure the unified native mini-program."""
import json
import shutil
import argparse
import os
import ipaddress
from urllib.parse import urlparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def build(base_url='http://127.0.0.1:8000', customer_appid='touristappid', merchant_appid='touristappid', unified_appid='touristappid', local_demo=False, unified_only=False):
    parsed=urlparse(base_url)
    loopback=parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost')
    private=False
    if parsed.scheme=='http' and local_demo:
        try: private=ipaddress.ip_address(parsed.hostname).is_private
        except ValueError: pass
    if not (parsed.scheme=='https' and parsed.hostname or loopback or private):
        raise ValueError('Use HTTPS, local loopback, or an explicit --local-demo private IP')
    shared=ROOT/'miniapps'/'shared'
    for role in ([] if unified_only else ['customer','merchant']):
        target=ROOT/'miniapps'/role
        for file in shared.rglob('*'):
            if file.is_file():
                dest=target/file.relative_to(shared);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
        (target/'config.js').write_text('module.exports = '+json.dumps({'role':role,'baseUrl':base_url.rstrip('/'),'version':'2.1.0'})+'\n',encoding='utf-8')
        config={'pages':['pages/home/index','pages/work/index','pages/profile/index','pages/detail/index','pages/login/index'],'window':{'navigationBarTitleText':'LumaSupply','navigationBarBackgroundColor':'#f6f6ef','navigationBarTextStyle':'black','backgroundColor':'#f6f6ef'},'tabBar':{'color':'#889578','selectedColor':'#2d4735','backgroundColor':'#ffffff','list':[{'pagePath':'pages/home/index','text':'选品' if role=='merchant' else '选灯'},{'pagePath':'pages/work/index','text':'供货工作台' if role=='merchant' else '选购与订单'},{'pagePath':'pages/profile/index','text':'商家资料' if role=='merchant' else '我的'}]},'style':'v2','sitemapLocation':'sitemap.json'}
        (target/'app.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
        (target/'sitemap.json').write_text(json.dumps({'rules':[{'action':'disallow','page':'*'}]}),encoding='utf-8')
        (target/'project.config.json').write_text(json.dumps({'appid':customer_appid if role=='customer' else merchant_appid,'projectname':'luma-'+role,'compileType':'miniprogram','setting':{'urlCheck':base_url.startswith('https://'),'es6':True,'enhance':True,'minified':True},'libVersion':'3.7.0'},indent=2),encoding='utf-8')
        for page in ['home','work','profile','detail','login']:
            page_config={'navigationBarTitleText':'LumaSupply'}
            if page=='home': page_config['enablePullDownRefresh']=True
            (target/'pages'/page/'index.json').write_text(json.dumps(page_config,separators=(',',':')),encoding='utf-8')
    target=ROOT/'miniapps'/'unified'
    (target/'config.js').write_text('module.exports = '+json.dumps({'role':'auto','baseUrl':base_url.rstrip('/'),'version':'2.1.0','demo':bool(local_demo or loopback)})+'\n',encoding='utf-8')
    project=json.loads((target/'project.config.json').read_text(encoding='utf-8'))
    project['appid']=unified_appid
    project['setting']['urlCheck']=parsed.scheme=='https'
    (target/'project.config.json').write_text(json.dumps(project,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Configured unified mini-program'+(' and rebuilt legacy role projects.' if not unified_only else '.'))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default=os.getenv('MINIAPP_API_URL','http://127.0.0.1:8000'))
    parser.add_argument('--customer-appid',default=os.getenv('WECHAT_APP_ID','touristappid'))
    parser.add_argument('--merchant-appid',default=os.getenv('WECHAT_MERCHANT_APP_ID','touristappid'))
    parser.add_argument('--unified-appid',default=os.getenv('WECHAT_UNIFIED_APP_ID','touristappid'))
    parser.add_argument('--local-demo',action='store_true')
    parser.add_argument('--unified-only',action='store_true')
    build(**vars(parser.parse_args()))
