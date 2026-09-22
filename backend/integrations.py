"""Optional real external provider. No success-shaped mocks in production paths."""
import os
import base64
from fastapi import HTTPException


def aliyun_search(image_bytes: bytes, limit: int):
    required = ["ALIYUN_ACCESS_KEY_ID", "ALIYUN_ACCESS_KEY_SECRET", "ALIYUN_IMAGESEARCH_ENDPOINT", "ALIYUN_IMAGESEARCH_INSTANCE"]
    if not all(os.getenv(k) for k in required):
        raise HTTPException(503, "阿里云图像搜索未配置，当前可使用本地检索")
    try:
        from alibabacloud_imagesearch20201214.client import Client
        from alibabacloud_imagesearch20201214 import models
        from alibabacloud_tea_openapi.models import Config
        config = Config(access_key_id=os.environ[required[0]], access_key_secret=os.environ[required[1]], endpoint=os.environ[required[2]])
        client = Client(config)
        request = models.SearchImageRequest(instance_name=os.environ[required[3]], pic_content=base64.b64encode(image_bytes).decode(), num=limit, type=0)
        response = client.search_image(request).body.to_map()
        if not response.get("Success", True): raise RuntimeError("SearchImage rejected")
        return [{"sku_id": int(x["ProductId"]), "score": float(x["Score"]), "image_id": x["PicName"]} for x in response.get("Auctions", [])]
    except ImportError as exc:
        raise HTTPException(503, "请安装 requirements-optional.txt 中阿里云 SDK") from exc
    except Exception as exc:
        # Do not echo SDK messages which can contain signed request URLs.
        raise HTTPException(502, f"阿里云检索调用失败（{type(exc).__name__}），请检查实例与索引") from exc
