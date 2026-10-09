"""Build both native WeChat projects from shared source; no external build service."""
import json
import shutil
import argparse
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def build(base_url='http://127.0.0.1:8000', customer_appid='touristappid', merchant_appid='touristappid'):
    if not base_url.startswith(('http://127.0.0.1:', 'http://localhost:', 'https://')):
        raise ValueError('Use a local development URL or a trusted HTTPS API URL')
    shared=ROOT/'miniapps'/'shared'
    for role in ['customer','merchant']:
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
    print('Built customer and merchant native mini-program projects.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default=os.getenv('MINIAPP_API_URL','http://127.0.0.1:8000'))
    parser.add_argument('--customer-appid',default=os.getenv('WECHAT_APP_ID','touristappid'))
    parser.add_argument('--merchant-appid',default=os.getenv('WECHAT_MERCHANT_APP_ID','touristappid'))
    build(**vars(parser.parse_args()))
