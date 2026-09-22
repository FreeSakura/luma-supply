"""Reproducible multi-view retrieval with image, character TF-IDF and hard filters.

The default encoder is deliberately transparent. Optional pretrained encoders are
explicitly selected, never silently substituted for the reported model.
"""
from collections import Counter
from pathlib import Path
import math
import re
import numpy as np
from PIL import Image, ImageOps

VERSION = "luma-handcrafted-v1"


def normalize(x):
    return x / max(float(np.linalg.norm(x)), 1e-12)


def prepare(image, crop=None):
    image = ImageOps.exif_transpose(image).convert("RGB")
    if crop is not None:
        x, y, w, h = crop
        if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x + w <= 1.00001 and y + h <= 1.00001):
            raise ValueError("Crop must be normalized x,y,width,height inside image")
        image = image.crop((round(x * image.width), round(y * image.height), round((x + w) * image.width), round((y + h) * image.height)))
    return image


def features(image, crop=None, color_only=False):
    image = prepare(image, crop).resize((96, 96))
    rgb = np.asarray(image, dtype=np.float32) / 255.0
    gray = np.asarray(image.convert("L"), dtype=np.float32) / 255.0
    hsv = np.asarray(image.convert("HSV"), dtype=np.float32) / 255.0
    # Foreground estimation uses border color, avoiding a mandatory white backdrop.
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    background = np.median(border, axis=0)
    foreground = np.linalg.norm(rgb - background, axis=2) > 0.16
    foreground_pixels = hsv[foreground] if foreground.sum() > 30 else hsv.reshape(-1, 3)
    hist = np.concatenate([np.histogram(foreground_pixels[:, c], bins=16, range=(0, 1))[0] for c in range(3)]).astype(np.float32)
    hist = normalize(np.sqrt(hist))
    if color_only: return hist
    dy, dx = np.gradient(gray)
    mag = np.sqrt(dx ** 2 + dy ** 2)
    angle = (np.arctan2(dy, dx) + np.pi) % np.pi
    hog = []
    for iy in range(4):
        for ix in range(4):
            sl = np.s_[iy * 24:(iy + 1) * 24, ix * 24:(ix + 1) * 24]
            hog.extend(normalize(np.histogram(angle[sl], bins=9, range=(0, np.pi), weights=mag[sl])[0]))
    occupancy = foreground.reshape(12, 8, 12, 8).mean(axis=(1, 3)).ravel()
    silhouette = np.concatenate([foreground.mean(axis=0).reshape(12, 8).mean(axis=1), foreground.mean(axis=1).reshape(12, 8).mean(axis=1)])
    return normalize(np.concatenate([hist * 0.35, normalize(np.asarray(hog)) * 0.25, normalize(occupancy) * 0.30, normalize(silhouette) * 0.10]).astype(np.float32))


class HandcraftedEncoder:
    version = VERSION
    def encode_image(self, image, crop=None): return features(image, crop)


class ResNetEncoder:
    version = "torchvision-resnet18-imagenet1k-v1"
    def __init__(self):
        import torch
        from torchvision.models import resnet18, ResNet18_Weights
        self.torch = torch
        weights = ResNet18_Weights.IMAGENET1K_V1
        self.preprocess = weights.transforms()
        self.model = resnet18(weights=weights).eval()
        self.model.fc = torch.nn.Identity()
    def encode_image(self, image, crop=None):
        with self.torch.inference_mode():
            x = self.model(self.preprocess(prepare(image, crop)).unsqueeze(0))[0].numpy()
        return normalize(x).astype(np.float32)


class ChineseClipEncoder:
    def __init__(self, model_name="ViT-B-16", model_root="data/models"):
        import torch
        import cn_clip.clip as clip
        self.torch, self.clip = torch, clip
        self.model, self.preprocess = clip.load_from_name(model_name, device="cpu", download_root=model_root)
        self.model.eval()
        self.version = "chinese-clip-" + model_name
    def encode_image(self, image, crop=None):
        with self.torch.inference_mode():
            x = self.model.encode_image(self.preprocess(prepare(image, crop)).unsqueeze(0))[0].float().numpy()
        return normalize(x).astype(np.float32)
    def encode_text(self, text):
        with self.torch.inference_mode():
            x = self.model.encode_text(self.clip.tokenize([text]))[0].float().numpy()
        return normalize(x).astype(np.float32)


def tokens(text):
    clean = re.sub(r"\s+", "", text.lower())
    return Counter([clean[i:i + n] for n in (1, 2) for i in range(len(clean) - n + 1)])


def text_scores(query, documents):
    if not query.strip(): return np.zeros(len(documents), dtype=np.float32)
    counts = [tokens(d) for d in documents]
    q = tokens(query)
    df = Counter(term for terms in counts for term in terms)
    idf = {term: math.log((1 + len(counts)) / (1 + df.get(term, 0))) + 1 for term in set(df) | set(q)}
    def weight(terms): return {t: (1 + math.log(c)) * idf[t] for t, c in terms.items()}
    query_vec = weight(q); qnorm = math.sqrt(sum(v * v for v in query_vec.values()))
    output = []
    for terms in counts:
        vec = weight(terms); norm = math.sqrt(sum(v * v for v in vec.values()))
        output.append(sum(v * vec.get(t, 0) for t, v in query_vec.items()) / max(qnorm * norm, 1e-12))
    return np.asarray(output)


def rank(query_vector, vectors, entries, text="", image_weight=0.7, text_weight=0.3, filters=None, limit=20, multi_view=True, threshold=0.0, clip_text_vector=None):
    filters = filters or {}
    image_scores = vectors @ query_vector if query_vector is not None and len(vectors) else np.zeros(len(entries))
    documents = [entry["text"] for entry in entries]
    semantic = text_scores(text, documents)
    if clip_text_vector is not None and len(vectors): semantic = vectors @ clip_text_vector
    weight_image = image_weight if query_vector is not None else 0
    weight_text = text_weight if text.strip() else 0
    scale = weight_image + weight_text
    if scale == 0: return []
    grouped = {}
    seen = set()
    for idx, entry in enumerate(entries):
        if not multi_view and entry["sku_id"] in seen: continue
        seen.add(entry["sku_id"])
        if filters.get("category") and entry["category"] != filters["category"]: continue
        if filters.get("max_price") is not None and entry["price"] > filters["max_price"]: continue
        if filters.get("available_only") and entry.get("stock_status") != "available": continue
        if any(str(entry.get("attributes", {}).get(k, "")).lower() != str(v).lower() for k, v in filters.get("attributes", {}).items()): continue
        score = float((weight_image * image_scores[idx] + weight_text * semantic[idx]) / scale)
        if score < threshold: continue
        result = {**entry, "score": score, "image_score": float(image_scores[idx]), "text_score": float(semantic[idx]), "match_type": "外观候选，规格需确认", "explanation": {"image_weight": weight_image / scale, "text_weight": weight_text / scale, "hard_filters": filters}}
        if entry["sku_id"] not in grouped or score > grouped[entry["sku_id"]]["score"]: grouped[entry["sku_id"]] = result
    return sorted(grouped.values(), key=lambda x: (-x["score"], x["sku_id"]))[:limit]
