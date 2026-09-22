"""Import an explicitly licensed image dataset from a manifest (local files only)."""
import argparse
import json
import shutil
from pathlib import Path
from uuid import uuid4
from PIL import Image
from backend.db import SessionLocal,RUNTIME
from backend.models import Media, Product, SKU, IndexTask


def run(manifest_path):
    manifest_path=Path(manifest_path).resolve();data=json.loads(manifest_path.read_text(encoding='utf-8'))
    with SessionLocal() as db:
        for row in data['products']:
            if not row.get('source') or not row.get('license'):raise ValueError('Each product requires source and license metadata')
            if db.query(SKU).filter_by(code=row['sku_code']).first():continue
            product=Product(name=row['name'],title=row['title'],category=row['category'],description=row.get('description',''),owner_id=data['admin_user_id'])
            db.add(product);db.flush();ids=[]
            for image_path in row['images']:
                path=(manifest_path.parent/image_path).resolve()
                with Image.open(path) as im:im.verify()
                mid=uuid4().hex;target=RUNTIME/'media'/(mid+path.suffix.lower());target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
                db.add(Media(id=mid,owner_id=data['admin_user_id'],purpose='product',mime=Image.MIME.get(Image.open(path).format,'image/jpeg'),path=str(target)));ids.append(mid)
            db.add(SKU(product_id=product.id,code=row['sku_code'],color=row.get('color',''),size_mm=row.get('size_mm',''),specification=row.get('specification',''),attributes={**row.get('attributes',{}),'data_source':row['source'],'usage_license':row['license']},images=ids,initial_price=row['initial_price_cents'],stock_status=row.get('stock_status','unconfirmed')))
        db.add(IndexTask(reason='licensed dataset import'));db.commit()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('manifest');run(parser.parse_args().manifest)
