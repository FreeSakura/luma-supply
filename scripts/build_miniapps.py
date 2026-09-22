"""Build both native WeChat projects from shared source; no external build service."""
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def build():
    shared=ROOT/'miniapps'/'shared'
    for role in ['customer','merchant']:
        target=ROOT/'miniapps'/role
        for file in shared.rglob('*'):
            if file.is_file():
                dest=target/file.relative_to(shared);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
        (target/'config.js').write_text(f"module.exports = {{ role: '{role}', baseUrl: 'http://127.0.0.1:8000' }}\n",encoding='utf-8')
        config={'pages':['pages/home/index','pages/work/index','pages/profile/index','pages/detail/index','pages/login/index'],'window':{'navigationBarTitleText':'LumaSupply','navigationBarBackgroundColor':'#f5f7f1','navigationBarTextStyle':'black','backgroundColor':'#f5f7f1'},'tabBar':{'color':'#889578','selectedColor':'#2d4735','backgroundColor':'#ffffff','list':[{'pagePath':'pages/home/index','text':'发现 Discover'},{'pagePath':'pages/work/index','text':'业务 Workspace'},{'pagePath':'pages/profile/index','text':'我的 Profile'}]},'style':'v2','sitemapLocation':'sitemap.json'}
        (target/'app.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
        (target/'sitemap.json').write_text(json.dumps({'rules':[{'action':'disallow','page':'*'}]}),encoding='utf-8')
        (target/'project.config.json').write_text(json.dumps({'appid':'touristappid','projectname':'luma-'+role,'compileType':'miniprogram','setting':{'urlCheck':False,'es6':True,'enhance':True,'minified':True},'libVersion':'3.7.0'},indent=2),encoding='utf-8')
        for page in ['home','work','profile','detail','login']:
            (target/'pages'/page/'index.json').write_text('{"navigationBarTitleText":"LumaSupply"}',encoding='utf-8')
    print('Built customer and merchant native mini-program projects.')


if __name__=='__main__': build()
