#!/usr/bin/env python3
"""
TikTok Affiliate AI Studio — Clean 9:16 Video + Multi-Variant Batch Generator + 1-Input URL/Name Crawler
- Không gắn sub, không gắn bảng giá/banner đè lên video (100% Clean 9:16 Video, center-crop 1.32x xóa sạch mọi góc thừa)
- Mỗi sản phẩm lưu vào 1 thư mục riêng biệt: ./output/<ma_san_pham>_<ten_san_pham>/
- Hỗ trợ tạo 5 Video biến thể khác nhau cho mỗi sản phẩm (5 góc kịch bản + thứ tự cảnh + nhịp cắt video khác nhau)
- Crawl Sản Phẩm Mới siêu gọn chỉ cần dán 1 ô duy nhất (Link TikTok / Shopee / hoặc Tên sản phẩm), AI Gemini tự điền thông số & kịch bản.
"""

from __future__ import annotations

import base64
import datetime as dt
import html as html_lib
import json
import math
import mimetypes
import os
import re
import shutil
import ssl
import subprocess
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import crawl_real_images
import crawl_real_videos

BASE_DIR = Path(__file__).resolve().parent
FEEDS_DIR = BASE_DIR / "feeds"
ASSETS_DIR = BASE_DIR / "assets"
REAL_ASSETS_DIR = ASSETS_DIR / "real"
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"
STATE_FILE = OUTPUT_DIR / "studio_state.json"
KEYS_FILE = OUTPUT_DIR / "api_keys.json"
VIDEO_RENDERER_BIN = BASE_DIR / "video_renderer"
ADAM_PITCH_BIN = BASE_DIR / "adam_pitch"

PORT = int(os.environ.get("PORT", "8088"))
ELEVENLABS_ADAM_VOICE_ID = "pNInz6obpgDQGcFmaJgB"

GEMINI_TTS_MODELS = [
    "gemini-2.5-flash-preview-tts",
    "gemini-3.8-flash-tts",
    "gemini-2.5-pro-preview-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-3.8-flash-lite-tts",
]
_TTS_MODEL_CURSOR = 0

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

PRODUCT_VIDEO_MAP = {
    "KALO-VN-882910": "case_video.mp4",
    "KALO-VN-774120": "fan_video.mp4",
    "KALO-VN-651092": "mic_video.mp4",
    "KALO-VN-540219": "bottle_video.mp4",
    "KALO-VN-492811": "stand_video.mp4",
}

VARIANT_STYLES = [
    {
        "index": 1,
        "name": "Biến thể #1: Hook Cảnh Báo & Soi Chi Tiết",
        "motions": ["zoom_in", "pan_detail", "zoom_out", "focus_center"],
        "img_order": [0, 1, 2, 3],
        "video_starts": [1.5, 6.0, 11.0, 15.5],
    },
    {
        "index": 2,
        "name": "Biến thể #2: Mở Hộp & Trải Nghiệm Cầm Tay",
        "motions": ["pan_detail", "zoom_in", "focus_center", "zoom_out"],
        "img_order": [1, 2, 3, 0],
        "video_starts": [3.5, 8.5, 13.5, 2.0],
    },
    {
        "index": 3,
        "name": "Biến thể #3: Giải Quyết Nỗi Đau & Test Thực Tế",
        "motions": ["zoom_out", "focus_center", "pan_detail", "zoom_in"],
        "img_order": [2, 0, 3, 1],
        "video_starts": [7.0, 12.0, 4.0, 16.0],
    },
    {
        "index": 4,
        "name": "Biến thể #4: Top Bán Chạy & So Sánh Chất Liệu",
        "motions": ["focus_center", "zoom_out", "zoom_in", "pan_detail"],
        "img_order": [3, 1, 0, 2],
        "video_starts": [10.0, 2.5, 14.5, 6.5],
    },
    {
        "index": 5,
        "name": "Biến thể #5: Review Nhanh Ưu Điểm Đáng Tiền",
        "motions": ["zoom_in", "zoom_out", "pan_detail", "focus_center"],
        "img_order": [1, 3, 2, 0],
        "video_starts": [5.0, 15.0, 9.5, 3.0],
    },
]


def slugify_vi(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    norm = unicodedata.normalize("NFKD", text)
    ascii_str = "".join(c for c in norm if not unicodedata.combining(c))
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_str.lower()).strip("_")
    return slug[:36] or "san_pham"


def get_product_folder_name(product: dict[str, Any]) -> str:
    ext = str(product.get("external_id", "SP")).lower().replace("-", "_")
    slug = slugify_vi(str(product.get("title", "san_pham")))
    return f"{ext}_{slug}"


def get_product_output_dir(product: dict[str, Any]) -> Path:
    folder = OUTPUT_DIR / get_product_folder_name(product)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def ensure_directories() -> None:
    FEEDS_DIR.mkdir(parents=True, exist_ok=True)
    REAL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)


def load_api_keys() -> dict[str, str]:
    keys = {
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "elevenlabs_api_key": os.environ.get("ELEVENLABS_API_KEY", ""),
        "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
        "perplexity_api_key": os.environ.get("PERPLEXITY_API_KEY", ""),
    }
    if KEYS_FILE.exists():
        try:
            saved = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            for k in keys:
                if saved.get(k):
                    keys[k] = str(saved[k]).strip()
        except Exception:
            pass
    return keys


def save_api_keys(new_keys: dict[str, Any]) -> dict[str, str]:
    current = load_api_keys()
    for k in ("gemini_api_key", "elevenlabs_api_key", "openai_api_key", "perplexity_api_key"):
        if k in new_keys and new_keys[k] is not None:
            val = str(new_keys[k]).strip()
            if val and not val.startswith("••••"):
                current[k] = val
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return ""
    return f"••••{key[-4:]}"


def load_raw_products() -> list[dict[str, Any]]:
    feed_path = FEEDS_DIR / "kalodata_trending_vn.json"
    if not feed_path.exists():
        return []
    return json.loads(feed_path.read_text(encoding="utf-8"))


def compute_product_scores(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not products:
        return []
    max_sales_log = max(math.log10(max(int(p.get("sales_7d", 1)), 1)) for p in products) or 1.0
    scored: list[dict[str, Any]] = []
    for p in products:
        item = dict(p)
        sales = max(int(item.get("sales_7d", 0)), 1)
        growth = float(item.get("growth_7d_pct", 0.0))
        rating = float(item.get("rating", 0.0))
        commission = float(item.get("commission_rate", 0.0))

        s_norm = min(1.0, math.log10(sales) / max_sales_log)
        g_norm = min(1.0, max(0.0, growth / 100.0))
        r_norm = min(1.0, max(0.0, rating / 5.0))
        c_norm = min(1.0, max(0.0, commission / 25.0))

        item["score"] = round(100.0 * (0.45 * s_norm + 0.25 * g_norm + 0.15 * r_norm + 0.15 * c_norm), 1)
        item["product_folder"] = str(get_product_output_dir(item))
        scored.append(item)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"custom_products": [], "jobs": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_all_products() -> list[dict[str, Any]]:
    base_products = load_raw_products()
    state = load_state()
    custom_products = state.get("custom_products", [])
    return compute_product_scores(custom_products + base_products)


def build_affiliate_script(product: dict[str, Any], variant_index: int = 1) -> dict[str, Any]:
    title = product.get("title", "Sản phẩm")
    short_name = title[:36].strip()
    specs = product.get("verified_specs", [])
    gallery = product.get("image_Gallery", [])

    spec_1 = specs[0] if len(specs) > 0 else "Hoàn thiện cực kỳ sắc nét và chắc tay"
    spec_2 = specs[1] if len(specs) > 1 else "Thiết kế thông minh, dùng thực tế rất tiện"
    spec_3 = specs[2] if len(specs) > 2 else "Chống trầy xước và bền bỉ khi dùng lâu dài"

    v_idx = ((max(1, variant_index) - 1) % len(VARIANT_STYLES))
    style = VARIANT_STYLES[v_idx]
    order = style["img_order"]
    motions = style["motions"]

    def pick_img(pos: int) -> str:
        if not gallery:
            return ""
        target_idx = order[pos % len(order)] % len(gallery)
        return gallery[target_idx]["url"]

    variant_scripts = [
        [
            f"Đừng vội mua {short_name} nếu bạn chưa xem kỹ chi tiết thực tế này.",
            f"Điểm ăn tiền nhất chính là {spec_1.lower()}.",
            f"Đi kèm {spec_2.lower()} và {spec_3.lower()}.",
            "Một lựa chọn quá ngon trong tầm giá, mình để sẵn ở giỏ hàng góc trái nhé.",
        ],
        [
            f"Trên tay nhanh {short_name} đang bán cực chạy tuần qua xem có gì hot.",
            f"Cầm thực tế mới thấy {spec_1.lower()}, hoàn thiện rất chỉn chu.",
            f"Đặc biệt là {spec_2.lower()}, kết hợp cùng {spec_3.lower()}.",
            "Ai đang tìm món này chuẩn xịn thì bấm ngay vào giỏ hàng góc trái màn hình nha.",
        ],
        [
            f"Lý do hàng ngàn người chốt đơn {short_name} chỉ sau vài giây trải nghiệm.",
            f"Khác hẳn hàng rẻ tiền, bản này có {spec_1.lower()}.",
            f"Khi dùng hằng ngày thì {spec_2.lower()} và {spec_3.lower()}.",
            "Đang có ưu đãi cực hời, anh em tham khảo ngay ở giỏ hàng bên dưới nhé.",
        ],
        [
            f"Kiểm chứng thực tế {short_name} xem có thực sự đáng tiền như lời đồn.",
            f"Ấn tượng đầu tiên là {spec_1.lower()} cực kỳ sắc sảo.",
            f"Chưa kể {spec_2.lower()}, cộng thêm {spec_3.lower()} rất bền bỉ.",
            "Mức giá hiện tại quá tốt cho một món phụ kiện chất lượng, link ở góc trái nhé.",
        ],
        [
            f"Ba điểm mình ưng nhất sau khi dùng thử {short_name} suốt tuần qua.",
            f"Thứ nhất là {spec_1.lower()}.",
            f"Thứ hai là {spec_2.lower()}, và thứ ba là {spec_3.lower()}.",
            "Đáng đồng tiền bát gạo, mình gắn sẵn sản phẩm chính hãng ở góc trái cho bạn nhé.",
        ],
    ]

    chosen_lines = variant_scripts[v_idx]
    scenes = []
    for i in range(4):
        scenes.append(
            {
                "scene_index": i + 1,
                "image_url": pick_img(i),
                "narration": chosen_lines[i],
                "motion": motions[i],
                "video_start_sec": style["video_starts"][i],
            }
        )

    caption = f"[{style['name']}] Review thực tế {title} #TikTokShop #ReviewThucTe #XuHuong"
    return {
        "product_id": product.get("external_id"),
        "product_title": title,
        "variant_index": v_idx + 1,
        "variant_name": style["name"],
        "scenes": scenes,
        "caption": caption,
    }


def extract_product_info_from_input(raw_input: str, keys: dict[str, str]) -> dict[str, Any]:
    """
    Nhận 1 ô input duy nhất: có thể là Link TikTok / Shopee / Web hoặc Tên sản phẩm.
    Tự động bóc tách tiêu đề + gọi Gemini AI để sinh thông số chuẩn mà người dùng không cần nhập tay.
    """
    raw = raw_input.strip()
    extracted_title = raw
    og_image_url = ""

    if raw.startswith("http://") or raw.startswith("https://"):
        try:
            req = urllib.request.Request(
                raw,
                headers={
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=12, context=SSL_CTX) as resp:
                final_url = resp.geturl()
                html = resp.read().decode("utf-8", errors="ignore")

            og_title = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if not og_title:
                og_title = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
            if og_title:
                cand = html_lib.unescape(og_title.group(1)).strip()
                cand = re.sub(r"\s*[-|]\s*(TikTok|Shopee|Lazada).*$", "", cand, flags=re.I)
                if len(cand) > 5 and "tiktok - make your day" not in cand.lower():
                    extracted_title = cand

            og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if og_img:
                og_image_url = html_lib.unescape(og_img.group(1)).strip()

            if extracted_title == raw:
                path_slug = urllib.parse.unquote(urllib.parse.urlparse(final_url).path)
                slug_parts = [p for p in re.split(r"[/\-_]", path_slug) if len(p) > 2 and not p.isdigit()]
                if slug_parts:
                    extracted_title = " ".join(slug_parts[-6:])
        except Exception as e:
            print(f"[Warn] Không đọc được trực tiếp HTML từ link ({e}), dùng phân tích URL/AI...")
            path_slug = urllib.parse.unquote(urllib.parse.urlparse(raw).path)
            slug_parts = [p for p in re.split(r"[/\-_]", path_slug) if len(p) > 2 and not p.isdigit()]
            if slug_parts:
                extracted_title = " ".join(slug_parts[-6:])

    gem_key = keys.get("gemini_api_key", "")
    if gem_key:
        for text_model in ("gemini-2.5-flash", "gemini-2.5-pro"):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{text_model}:generateContent?key={gem_key}"
                prompt = (
                    f"Người dùng nhập thông tin hoặc link sản phẩm: '{raw}' (Tiêu đề trích xuất: '{extracted_title}').\n"
                    "Hãy đóng vai chuyên gia TikTok Shop Affiliate Việt Nam, trả về đúng 1 JSON object (không bọc markdown) gồm:\n"
                    '{"title": "Tên sản phẩm tiếng Việt chuẩn xác, giữ nguyên Tên Hãng và Mã Model (ví dụ: Sạc Dự Phòng CUKTECH 15 SE PB200 85W 20000mAh)", '
                    '"exact_model_query": "Cụm từ khóa ngắn gọn chỉ gồm Tên Hãng + Mã Model để tìm đúng 100% ảnh/video sản phẩm (ví dụ: CUKTECH 15 SE PB200)", '
                    '"search_keyword_en": "Cụm từ khóa ngắn gọn tìm video review/unboxing trên YouTube Shorts (ví dụ: CUKTECH 15 SE power bank review)", '
                    '"price_vnd": 690000, '
                    '"sales_7d": 11200, '
                    '"verified_specs": ["Đặc điểm kỹ thuật thật số 1 của đúng model này (dưới 15 từ)", "Đặc điểm kỹ thuật thật số 2 của đúng model này (dưới 15 từ)", "Đặc điểm kỹ thuật thật số 3 của đúng model này (dưới 15 từ)"]}'
                )
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=18, context=SSL_CTX) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                txt = res_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed_ai = json.loads(txt)
                if parsed_ai.get("title"):
                    parsed_ai["og_image_url"] = og_image_url
                    return parsed_ai
            except Exception as e:
                print(f"[Warn] Gemini auto-spec ({text_model}) fallback: {e}")

    short_queries = crawl_real_videos.simplify_product_query(extracted_title)
    clean_title = extracted_title if len(extracted_title) >= 4 else "Sản Phẩm Hot Trend TikTok Shop"
    return {
        "title": clean_title,
        "exact_model_query": short_queries[0],
        "search_keyword_en": short_queries[0],
        "price_vnd": 159000,
        "sales_7d": 10500,
        "verified_specs": [
            f"Thiết kế thực tế của {short_queries[0]} sắc nét từng chi tiết",
            "Chất liệu cao cấp hoàn thiện chắc chắn, cầm đầm tay",
            "Đang nằm trong top sản phẩm bán chạy nhất tuần qua",
        ],
        "og_image_url": og_image_url,
    }


def measure_audio_duration(audio_path: Path) -> float:
    try:
        proc = subprocess.run(
            ["/usr/bin/afinfo", str(audio_path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        match = re.search(r"estimated duration:\s*([0-9.]+)\s*sec", proc.stdout)
        if match:
            return round(float(match.group(1)), 2)
    except Exception:
        pass
    return 14.0


def get_video_duration(video_path: Path) -> float:
    try:
        proc = subprocess.run(
            ["mdls", "-name", "kMDItemDurationSeconds", str(video_path)],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        match = re.search(r"kMDItemDurationSeconds\s*=\s*([0-9.]+)", proc.stdout)
        if match:
            return float(match.group(1))
    except Exception:
        pass
    try:
        proc = subprocess.run(
            ["/usr/bin/afinfo", str(video_path)],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        match = re.search(r"estimated duration:\s*([0-9.]+)\s*sec", proc.stdout)
        if match:
            return round(float(match.group(1)), 2)
    except Exception:
        pass
    return 20.0


def resolve_local_image_path(image_url: str) -> str:
    if image_url.startswith("/assets/"):
        rel = image_url[len("/assets/") :]
        return str((ASSETS_DIR / rel).resolve())
    return str((BASE_DIR / image_url.lstrip("/")).resolve())


def resolve_product_video_path(product: dict[str, Any], variant_index: int = 1) -> str | None:
    ext_id = str(product.get("external_id", ""))
    prefix_custom = f"custom_{ext_id.lower()}"

    # 1. Kiểm tra video nguồn riêng biệt cho biến thể này: {prefix}_video_{variant_index}.mp4
    custom_variant_vp = REAL_ASSETS_DIR / f"{prefix_custom}_video_{variant_index}.mp4"
    if custom_variant_vp.exists() and custom_variant_vp.stat().st_size > 50_000:
        return str(custom_variant_vp.resolve())

    # 2. Nếu là sản phẩm có sẵn trong PRODUCT_VIDEO_MAP (stand, case, fan, mic, bottle)
    if ext_id in PRODUCT_VIDEO_MAP:
        base_name = PRODUCT_VIDEO_MAP[ext_id].replace(".mp4", "")
        # Thử tìm file biến thể tương ứng, ví dụ stand_video_2.mp4
        mapped_variant_vp = REAL_ASSETS_DIR / f"{base_name}_{variant_index}.mp4"
        if mapped_variant_vp.exists() and mapped_variant_vp.stat().st_size > 50_000:
            return str(mapped_variant_vp.resolve())
        mapped_legacy_vp = REAL_ASSETS_DIR / PRODUCT_VIDEO_MAP[ext_id]
        if mapped_legacy_vp.exists() and mapped_legacy_vp.stat().st_size > 50_000:
            return str(mapped_legacy_vp.resolve())

    # 3. Kiểm tra real_video_path được lưu trong sản phẩm
    if product.get("real_video_path"):
        raw_vp = Path(str(product["real_video_path"]))
        variant_vp = raw_vp.parent / f"{raw_vp.stem.rstrip('_12345')}_{variant_index}.mp4"
        if variant_vp.exists() and variant_vp.stat().st_size > 50_000:
            return str(variant_vp.resolve())
        if raw_vp.exists() and raw_vp.stat().st_size > 50_000:
            return str(raw_vp.resolve())

    # 4. Fallback về video đơn {prefix}_video.mp4
    custom_vp = REAL_ASSETS_DIR / f"{prefix_custom}_video.mp4"
    if custom_vp.exists() and custom_vp.stat().st_size > 50_000:
        return str(custom_vp.resolve())

    return None


def synthesize_full_script_voice(full_text: str, out_m4a: Path, keys: dict[str, str]) -> str:
    el_key = keys.get("elevenlabs_api_key", "")
    if el_key:
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_ADAM_VOICE_ID}"
            payload = {
                "text": full_text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.42,
                    "similarity_boost": 0.82,
                    "style": 0.30,
                    "use_speaker_boost": True,
                },
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "xi-api-key": el_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                method="POST",
            )
            mp3_temp = out_m4a.with_suffix(".mp3")
            with urllib.request.urlopen(req, timeout=25, context=SSL_CTX) as resp:
                mp3_temp.write_bytes(resp.read())
            subprocess.run(
                ["/usr/bin/afconvert", "-f", "m4af", "-d", "aac", str(mp3_temp), str(out_m4a)],
                check=True,
                timeout=10,
            )
            mp3_temp.unlink(missing_ok=True)
            if out_m4a.exists():
                return "ElevenLabs Adam (Chuẩn Quốc Tế)"
        except Exception as e:
            print(f"[Warn] ElevenLabs trả về lỗi ({e}), tự động chuyển sang Google Gemini TTS...")

    gem_key = keys.get("gemini_api_key", "")
    if gem_key:
        global _TTS_MODEL_CURSOR
        start_idx = _TTS_MODEL_CURSOR
        _TTS_MODEL_CURSOR = (_TTS_MODEL_CURSOR + 1) % len(GEMINI_TTS_MODELS)
        ordered_models = [
            GEMINI_TTS_MODELS[(start_idx + i) % len(GEMINI_TTS_MODELS)]
            for i in range(len(GEMINI_TTS_MODELS))
        ]
        for model_name in ordered_models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gem_key}"
                payload = {
                    "contents": [{"parts": [{"text": full_text}]}],
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {"voiceName": "Charon"}
                            }
                        },
                    },
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                b64_pcm = res_json["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
                pcm_bytes = base64.b64decode(b64_pcm)

                wav_raw = out_m4a.with_suffix(".raw.wav")
                with wave.open(str(wav_raw), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(24000)
                    wf.writeframes(pcm_bytes)

                wav_fast = out_m4a.with_suffix(".fast.wav")
                if ADAM_PITCH_BIN.exists():
                    subprocess.run(
                        [str(ADAM_PITCH_BIN), str(wav_raw), str(wav_fast), "-45", "1.16"],
                        check=False,
                        timeout=15,
                    )
                target_wav = wav_fast if wav_fast.exists() else wav_raw
                subprocess.run(
                    ["/usr/bin/afconvert", "-f", "m4af", "-d", "aac", str(target_wav), str(out_m4a)],
                    check=True,
                    timeout=10,
                )
                wav_raw.unlink(missing_ok=True)
                wav_fast.unlink(missing_ok=True)
                if out_m4a.exists():
                    return f"Google Gemini AI Voice (Charon Male • {model_name})"
            except Exception as e:
                print(f"[Warn] Model {model_name} bận ({e}), thử model TTS tiếp theo...")

    say_bin = shutil.which("say")
    raw_m4a = out_m4a.with_suffix(".raw.m4a")
    if say_bin:
        subprocess.run(
            [say_bin, "-v", "Linh", "-r", "210", "-o", str(raw_m4a), "--data-format=aac", full_text],
            check=False,
            timeout=15,
        )
        if raw_m4a.exists() and ADAM_PITCH_BIN.exists():
            temp_wav = out_m4a.with_suffix(".adam.wav")
            subprocess.run([str(ADAM_PITCH_BIN), str(raw_m4a), str(temp_wav)], check=False, timeout=15)
            raw_m4a.unlink(missing_ok=True)
            if temp_wav.exists():
                subprocess.run(
                    ["/usr/bin/afconvert", "-f", "m4af", "-d", "aac", str(temp_wav), str(out_m4a)],
                    check=False,
                    timeout=10,
                )
                temp_wav.unlink(missing_ok=True)
            if out_m4a.exists():
                return "Adam Fast Male DSP (Local)"
    return "Local Fast TTS"


def ensure_product_source_videos(product: dict[str, Any]) -> None:
    """
    Đảm bảo sản phẩm có đủ 5 video nguồn thực tế khác nhau trong assets/real/.
    Nếu chưa có, tự động tải 5 YouTube Shorts thực tế tương ứng.
    """
    ext_id = str(product.get("external_id", ""))
    prefix_custom = f"custom_{ext_id.lower()}"

    # Kiểm tra xem đã có video_5 chưa
    if ext_id in PRODUCT_VIDEO_MAP:
        base_name = PRODUCT_VIDEO_MAP[ext_id].replace(".mp4", "")
        if (REAL_ASSETS_DIR / f"{base_name}_5.mp4").exists():
            return
        prefix = base_name
    else:
        if (REAL_ASSETS_DIR / f"{prefix_custom}_video_5.mp4").exists():
            return
        prefix = prefix_custom

    queries = crawl_real_videos.simplify_product_query(product.get("title", ""))
    try:
        crawl_real_videos.download_multiple_short_mp4s(queries, prefix, count=5)
    except Exception as e:
        print(f"[Warn] Lỗi tự động tải 5 video nguồn cho {product.get('title')}: {e}")


def generate_real_mp4_job(
    product: dict[str, Any],
    scenes: list[dict[str, Any]],
    caption: str,
    variant_index: int = 1,
    visual_mode: str = "hybrid",
    fixed_job_id: str | None = None,
    use_veo_if_available: bool = False,
) -> dict[str, Any]:
    """
    Lưu toàn bộ các video của cùng 1 sản phẩm vào ĐÚNG 1 THƯ MỤC RIÊNG của sản phẩm đó:
      ./output/<ma_sp>_<slug_ten_sp>/
        ├── video_1.mp4
        ├── voice_1.m4a
        ├── script_1.txt
        ├── video_2.mp4 ...
    visual_mode:
      - "real_video": Sử dụng 100% các phân đoạn video quay thật (mỗi biến thể lấy các mốc thời gian & góc zoom khác nhau)
      - "hybrid": Xen kẽ cảnh video quay thật + cảnh cận cảnh ảnh sản phẩm 3D Handheld để vừa có review động vừa soi rõ chi tiết ảnh
      - "photos_motion": Dựng hoàn toàn từ bộ ảnh thật của sản phẩm với 5 kịch bản chuyển động 3D Handheld khác nhau
    """
    prod_folder_name = get_product_folder_name(product)
    prod_dir = OUTPUT_DIR / prod_folder_name
    prod_dir.mkdir(parents=True, exist_ok=True)

    v_idx = max(1, int(variant_index))
    style = VARIANT_STYLES[(v_idx - 1) % len(VARIANT_STYLES)]
    job_id = fixed_job_id or f"{prod_folder_name}__v{v_idx}"

    keys = load_api_keys()
    full_texts = [str(sc.get("narration", "")).strip() for sc in scenes if str(sc.get("narration", "")).strip()]
    joined_script = " ".join(full_texts)

    full_audio_path = prod_dir / f"voice_{v_idx}.m4a"
    script_file = prod_dir / f"script_{v_idx}.txt"
    caption_file = prod_dir / f"caption_{v_idx}.txt"
    new_script_txt = "\n\n".join(full_texts)

    # Tận dụng lại file voice cũ nếu có ở thư mục pro_adam_* khi nâng cấp sang cấu trúc thư mục mới (cho biến thể #1)
    legacy_voice = OUTPUT_DIR / f"pro_adam_{product['external_id'].lower().replace('-', '_')}" / "voice.m4a"
    if v_idx == 1 and not full_audio_path.exists() and legacy_voice.exists() and legacy_voice.stat().st_size > 20_000:
        shutil.copy2(legacy_voice, full_audio_path)
        script_file.write_text(new_script_txt, encoding="utf-8")

    if (
        full_audio_path.exists()
        and full_audio_path.stat().st_size > 20_000
        and script_file.exists()
        and script_file.read_text(encoding="utf-8").strip() == new_script_txt.strip()
    ):
        voice_engine_used = "Google Gemini AI Voice (Charon Male • Đã đồng bộ)"
    else:
        voice_engine_used = synthesize_full_script_voice(joined_script, full_audio_path, keys)

    total_audio_sec = max(8.0, measure_audio_duration(full_audio_path))
    total_chars = max(1, sum(len(str(sc.get("narration", ""))) for sc in scenes))

    manifest_scenes: list[dict[str, Any]] = []
    updated_scenes: list[dict[str, Any]] = []
    real_video_path = resolve_product_video_path(product, v_idx)

    # Tính toán thời lượng clip nguồn và độ dịch chuyển video_start thông minh
    # Bỏ qua đoạn mở hộp/cắt băng dính ban đầu (skip 12% - 18% đầu) để vào NGAY cảnh cầm hàng thật
    src_video_dur = get_video_duration(Path(real_video_path)) if (real_video_path and Path(real_video_path).exists()) else 20.0
    safe_lead_sec = max(1.5, min(6.0, src_video_dur * 0.15))
    usable_video_span = max(4.0, src_video_dur - safe_lead_sec - 1.5)
    scene_step = usable_video_span / max(1, len(scenes))

    for s_i, sc in enumerate(scenes):
        narration = str(sc.get("narration", "")).strip()
        weight = max(0.15, len(narration) / total_chars)
        scene_dur = round(total_audio_sec * weight, 2)
        img_url = str(sc.get("image_url", ""))
        img_local_path = resolve_local_image_path(img_url)

        # Tính toán điểm cắt video động vào giữa lúc người dùng thao tác / review sản phẩm thực tế
        if real_video_path and Path(real_video_path).exists():
            dyn_v_start = round(safe_lead_sec + scene_step * s_i, 2)
            dyn_v_start = min(dyn_v_start, max(0.0, src_video_dur - scene_dur - 0.5))
            v_start = dyn_v_start
        else:
            v_start = float(sc.get("video_start_sec", style["video_starts"][s_i % len(style["video_starts"])]))

        # Quyết định cảnh nào dùng video quay thật, cảnh nào dùng ảnh thật chuyển động 3D
        scene_video_path: str | None = None
        if visual_mode == "photos_motion":
            scene_video_path = None
        else:
            # 100% video quay review thật liền mạch từ đầu tới cuối, tuyệt đối không chèn ảnh tĩnh vào giữa
            scene_video_path = real_video_path

        manifest_scenes.append(
            {
                "image_path": img_local_path,
                "video_path": scene_video_path,
                "video_start_sec": v_start,
                "audio_path": None,
                "motion": str(sc.get("motion", style["motions"][s_i % 4])),
                "duration_sec": scene_dur,
            }
        )

        sc_copy = dict(sc)
        sc_copy["duration_sec"] = scene_dur
        sc_copy["video_start_sec"] = v_start
        updated_scenes.append(sc_copy)

    script_file.write_text(new_script_txt, encoding="utf-8")
    caption_file.write_text(caption, encoding="utf-8")

    output_mp4_path = prod_dir / f"video_{v_idx}.mp4"
    manifest_data = {
        "audio_path": str(full_audio_path),
        "output_mp4_path": str(output_mp4_path),
        "scenes": manifest_scenes,
    }
    manifest_path = prod_dir / f"render_manifest_{v_idx}.json"
    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")

    subprocess.run(
        [str(VIDEO_RENDERER_BIN), str(manifest_path)],
        check=True,
        timeout=95,
    )

    size_mb = round(output_mp4_path.stat().st_size / (1024 * 1024), 2) if output_mp4_path.exists() else 0.0

    job_record = {
        "job_id": job_id,
        "product_id": product["external_id"],
        "product_title": product["title"],
        "variant_index": v_idx,
        "variant_name": style["name"],
        "visual_mode": visual_mode,
        "created_at": dt.datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
        "total_duration_sec": round(total_audio_sec, 1),
        "voice_engine": voice_engine_used,
        "video_url": f"/output/{prod_folder_name}/video_{v_idx}.mp4",
        "audio_url": f"/output/{prod_folder_name}/voice_{v_idx}.m4a",
        "script_url": f"/output/{prod_folder_name}/script_{v_idx}.txt",
        "caption_url": f"/output/{prod_folder_name}/caption_{v_idx}.txt",
        "output_dir": str(prod_dir),
        "video_file_name": f"video_{v_idx}.mp4",
        "video_size_mb": size_mb,
        "scenes": updated_scenes,
        "caption": caption,
    }

    state = load_state()
    jobs = [j for j in state.get("jobs", []) if j.get("job_id") != job_id]
    jobs.insert(0, job_record)
    state["jobs"] = jobs[:60]
    save_state(state)

    return job_record


def get_product_jobs(product_id: str) -> list[dict[str, Any]]:
    state = load_state()
    matched = []
    for j in state.get("jobs", []):
        if j.get("product_id") == product_id:
            rel_video = str(j.get("video_url", "")).lstrip("/")
            if rel_video and (BASE_DIR / rel_video).exists():
                matched.append(j)
    matched.sort(key=lambda x: int(x.get("variant_index", 1)))
    return matched


class StudioRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[Studio] {self.address_string()} - {fmt % args}", flush=True)

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route == "/api/bootstrap":
            products = get_all_products()
            state = load_state()
            keys = load_api_keys()
            self._send_json(
                {
                    "ok": True,
                    "products": products,
                    "jobs": state.get("jobs", []),
                    "keys_status": {
                        "has_gemini": bool(keys.get("gemini_api_key")),
                        "has_elevenlabs": bool(keys.get("elevenlabs_api_key")),
                        "has_openai": bool(keys.get("openai_api_key")),
                        "gemini_masked": mask_key(keys.get("gemini_api_key", "")),
                        "elevenlabs_masked": mask_key(keys.get("elevenlabs_api_key", "")),
                    },
                }
            )
            return

        if route.startswith("/assets/"):
            rel = route[len("/assets/") :]
            target = (ASSETS_DIR / rel).resolve()
            if target.is_file() and str(target).startswith(str(ASSETS_DIR)):
                self._serve_file(target)
                return
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if route.startswith("/output/"):
            rel = route[len("/output/") :]
            target = (OUTPUT_DIR / rel).resolve()
            if target.is_file() and str(target).startswith(str(OUTPUT_DIR)):
                self._serve_file(target)
                return
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if route == "/" or route == "/index.html":
            self._serve_file(STATIC_DIR / "index.html")
            return

        static_target = (STATIC_DIR / route.lstrip("/")).resolve()
        if static_target.is_file() and str(static_target).startswith(str(STATIC_DIR)):
            self._serve_file(static_target)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route == "/api/save-keys":
            body = self._read_json_body()
            keys = save_api_keys(body)
            self._send_json(
                {
                    "ok": True,
                    "keys_status": {
                        "has_gemini": bool(keys.get("gemini_api_key")),
                        "has_elevenlabs": bool(keys.get("elevenlabs_api_key")),
                        "has_openai": bool(keys.get("openai_api_key")),
                        "gemini_masked": mask_key(keys.get("gemini_api_key", "")),
                        "elevenlabs_masked": mask_key(keys.get("elevenlabs_api_key", "")),
                    },
                }
            )
            return

        if route == "/api/prepare-product":
            body = self._read_json_body()
            product_id = body.get("product_id")
            variant_index = int(body.get("variant_index", 1))
            products = get_all_products()
            product = next((p for p in products if p["external_id"] == product_id), None)
            if not product:
                self._send_json({"ok": False, "error": "Không tìm thấy sản phẩm."}, HTTPStatus.NOT_FOUND)
                return

            script_pack = build_affiliate_script(product, variant_index=variant_index)
            product_jobs = get_product_jobs(str(product_id))
            latest_job = next(
                (j for j in product_jobs if int(j.get("variant_index", 1)) == variant_index),
                product_jobs[0] if product_jobs else None,
            )
            self._send_json(
                {
                    "ok": True,
                    "product": product,
                    "script_pack": script_pack,
                    "latest_job": latest_job,
                    "product_jobs": product_jobs,
                }
            )
            return

        if route == "/api/render-mp4":
            body = self._read_json_body()
            product_id = body.get("product_id")
            scenes = body.get("scenes", [])
            caption = str(body.get("caption", ""))
            variant_index = int(body.get("variant_index", 1))
            visual_mode = str(body.get("visual_mode", "real_video"))

            products = get_all_products()
            product = next((p for p in products if p["external_id"] == product_id), None)
            if not product:
                self._send_json({"ok": False, "error": "Không tìm thấy sản phẩm."}, HTTPStatus.NOT_FOUND)
                return

            if not scenes:
                pack = build_affiliate_script(product, variant_index=variant_index)
                scenes = pack["scenes"]
                caption = pack["caption"]

            try:
                job = generate_real_mp4_job(
                    product=product,
                    scenes=scenes,
                    caption=caption,
                    variant_index=variant_index,
                    visual_mode=visual_mode,
                )
                self._send_json(
                    {
                        "ok": True,
                        "job": job,
                        "product_jobs": get_product_jobs(str(product_id)),
                    }
                )
            except Exception as e:
                self._send_json({"ok": False, "error": f"Lỗi dựng MP4: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/render-batch-5":
            body = self._read_json_body()
            product_id = body.get("product_id")
            visual_mode = str(body.get("visual_mode", "hybrid"))

            products = get_all_products()
            product = next((p for p in products if p["external_id"] == product_id), None)
            if not product:
                self._send_json({"ok": False, "error": "Không tìm thấy sản phẩm."}, HTTPStatus.NOT_FOUND)
                return

            # Đảm bảo có đủ 5 video nguồn thực tế khác nhau cho 5 biến thể
            try:
                ensure_product_source_videos(product)
            except Exception as e:
                print(f"[Warn] Lỗi đảm bảo 5 video nguồn: {e}")

            created_jobs = []
            try:
                for v_idx in range(1, 6):
                    pack = build_affiliate_script(product, variant_index=v_idx)
                    # 100% video review quay thật cho toàn bộ 5 biến thể
                    mode_for_v = visual_mode if visual_mode not in ("auto_diverse", "hybrid") else "real_video"
                    j = generate_real_mp4_job(
                        product=product,
                        scenes=pack["scenes"],
                        caption=pack["caption"],
                        variant_index=v_idx,
                        visual_mode=mode_for_v,
                    )
                    created_jobs.append(j)
                self._send_json(
                    {
                        "ok": True,
                        "jobs": created_jobs,
                        "product_jobs": get_product_jobs(str(product_id)),
                    }
                )
            except Exception as e:
                self._send_json({"ok": False, "error": f"Lỗi tạo 5 video: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/crawl-new-product":
            body = self._read_json_body()
            raw_query = str(body.get("query") or body.get("title") or "").strip()

            if len(raw_query) < 3:
                self._send_json(
                    {"ok": False, "error": "Vui lòng dán Link sản phẩm (TikTok/Shopee) hoặc nhập Tên sản phẩm."},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            keys = load_api_keys()
            ai_info = extract_product_info_from_input(raw_query, keys)
            title = str(ai_info.get("title", raw_query)).strip()
            exact_model_q = str(ai_info.get("exact_model_query") or title).strip()
            price_vnd = int(ai_info.get("price_vnd", 159000))
            sales_7d = int(ai_info.get("sales_7d", 10500))
            specs = list(ai_info.get("verified_specs", []))
            search_kw_en = str(ai_info.get("search_keyword_en", exact_model_q))
            og_image_url = str(ai_info.get("og_image_url", ""))

            ext_id = f"KALO-{uuid.uuid4().hex[:6].upper()}"
            prefix = f"custom_{ext_id.lower()}"
            crawled_urls = crawl_real_images.crawl_images_for_query(
                prefix,
                [exact_model_q, title],
                count=4,
                primary_og_image=og_image_url,
            )

            # Tự động tải trọn bộ 5 video nguồn thực tế khác nhau từ YouTube Shorts
            video_out_path = REAL_ASSETS_DIR / f"{prefix}_video.mp4"
            try:
                crawled_vids = crawl_real_videos.download_multiple_short_mp4s(
                    [search_kw_en, exact_model_q, title],
                    prefix,
                    count=5,
                )
                if crawled_vids and crawled_vids[0].exists():
                    video_out_path = crawled_vids[0]
            except Exception as e:
                print(f"[Warn] Không tải được video Shorts cho {title}: {e}")

            if not crawled_urls:
                self._send_json({"ok": False, "error": "Không crawl được hình ảnh từ mạng."}, HTTPStatus.BAD_REQUEST)
                return

            gallery = []
            for idx in range(4):
                img_url = crawled_urls[idx % len(crawled_urls)]
                gallery.append(
                    {
                        "id": f"{prefix}_{idx + 1}",
                        "label": f"Ảnh thực tế #{idx + 1}",
                        "caption_tag": specs[min(idx, len(specs) - 1)][:38] if specs else "Ảnh thực tế",
                        "url": img_url,
                    }
                )

            new_prod = {
                "external_id": ext_id,
                "source": "kalodata_crawled",
                "kalodata_rank": 1,
                "title": title,
                "category": "Sản phẩm Crawl Tự Động",
                "shop_name": "TikTok Shop VN",
                "price_vnd": price_vnd,
                "original_price_vnd": int(price_vnd * 1.4),
                "sales_7d": sales_7d,
                "gmv_7d_vnd": price_vnd * sales_7d,
                "growth_7d_pct": 85.0,
                "rating": 4.9,
                "review_count": 2400,
                "commission_rate": 18.0,
                "verified_specs": specs,
                "forbidden_claims": [],
                "image_Gallery": gallery,
                "real_video_path": str(video_out_path) if video_out_path.exists() else "",
            }

            state = load_state()
            state.setdefault("custom_products", []).insert(0, new_prod)
            save_state(state)

            all_prods = get_all_products()
            scored_prod = next((p for p in all_prods if p["external_id"] == ext_id), new_prod)
            script_pack = build_affiliate_script(scored_prod, variant_index=1)
            job = generate_real_mp4_job(
                product=scored_prod,
                scenes=script_pack["scenes"],
                caption=script_pack["caption"],
                variant_index=1,
                visual_mode="real_video" if video_out_path.exists() else "photos_motion",
            )
            self._send_json(
                {
                    "ok": True,
                    "product": scored_prod,
                    "products": all_prods,
                    "job": job,
                    "product_jobs": get_product_jobs(ext_id),
                }
            )
            return

        if route == "/api/upload-scene-image":
            body = self._read_json_body()
            data_url = str(body.get("data_url", ""))
            if not data_url.startswith("data:image/"):
                self._send_json({"ok": False, "error": "File ảnh không hợp lệ."}, HTTPStatus.BAD_REQUEST)
                return
            _, b64 = data_url.split(",", 1)
            fname = f"upload_{uuid.uuid4().hex[:8]}.jpg"
            dest = REAL_ASSETS_DIR / fname
            dest.write_bytes(base64.b64decode(b64))
            subprocess.run(
                ["/usr/bin/sips", "-s", "format", "jpeg", str(dest), "--out", str(dest)],
                capture_output=True,
                timeout=5,
                check=False,
            )
            self._send_json({"ok": True, "image_url": f"/assets/real/{fname}"})
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def _serve_file(self, file_path: Path) -> None:
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        ctype, _ = mimetypes.guess_type(str(file_path))
        if not ctype:
            ctype = "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype = f"{ctype}; charset=utf-8"

        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    ensure_directories()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), StudioRequestHandler)
    print("============================================================", flush=True)
    print(f" TikTok Affiliate AI Studio đang chạy tại: http://127.0.0.1:{PORT}", flush=True)
    print("============================================================", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
