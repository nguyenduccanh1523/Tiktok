#!/usr/bin/env python3
"""
Crawler tải ảnh sản phẩm THẬT (JPG/PNG độ phân giải cao) từ Internet
cho các sản phẩm đang bán chạy trên TikTok Shop / Kalodata VN.
Hỗ trợ tìm kiếm ảnh thực tế theo từ khóa sản phẩm và lưu trực tiếp vào ./assets/real/
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REAL_ASSETS_DIR = BASE_DIR / "assets" / "real"
FEEDS_FILE = BASE_DIR / "feeds" / "kalodata_trending_vn.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def fetch_bing_image_urls(query: str, max_results: int = 12) -> list[str]:
    """Crawl danh sách URL ảnh sản phẩm thực tế từ Bing Images."""
    encoded = urllib.parse.quote(query)
    url = f"https://www.bing.com/images/search?q={encoded}&form=HDRSC2&first=1"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=12, context=SSL_CTX) as resp:
        html_text = resp.read().decode("utf-8", errors="ignore")

    # Trích xuất murl (Media URL gốc độ phân giải cao) trong trang kết quả
    matches = re.findall(r"murl&quot;:&quot;(https?://[^&]+?)&quot;", html_text)
    if not matches:
        matches = re.findall(r'"murl":"(https?://[^"]+?)"', html_text)

    cleaned: list[str] = []
    for m in matches:
        if any(bad in m.lower() for bad in (".svg", ".gif", "logo", "icon", "avatar")):
            continue
        if m not in cleaned:
            cleaned.append(m)
        if len(cleaned) >= max_results:
            break
    return cleaned


def download_image_file(url: str, dest_path: Path) -> bool:
    """Tải file ảnh thực tế và kiểm tra dung lượng hợp lệ (> 8KB)."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Referer": "https://www.bing.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            data = resp.read()
            if len(data) < 8192:
                return False
            if "html" in ctype or data[:15].lower().startswith(b"<!doctype"):
                return False
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(data)
            return True
    except Exception:
        return False


def clean_brackets_preserve_brand(raw_title: str) -> str:
    promo_pattern = r"\[\s*(quà tặng|freeship|hàng mới|mua \d+|giảm \d+|hot|sale|chính hãng|bảo hành|mã|voucher|đã bán).*?\]"
    cleaned = re.sub(promo_pattern, " ", raw_title, flags=re.I)
    cleaned = re.sub(r"\(\s*(quà tặng|freeship|hàng mới|mua \d+|giảm \d+|hot|sale|chính hãng|bảo hành).*?\)", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\[([^\]]+)\]", r" \1 ", cleaned)
    cleaned = re.sub(r"\(([^\)]+)\)", r" \1 ", cleaned)
    return cleaned


def extract_exact_product_queries(raw_title: str) -> tuple[list[str], list[str]]:
    """
    Tách tên thương hiệu/model chính xác và danh sách câu truy vấn ngắn gọn từ tên sản phẩm dài.
    Trả về (queries, must_match_tokens).
    """
    cleaned = clean_brackets_preserve_brand(raw_title)
    parts = [p.strip() for p in re.split(r"[|•\-–—/]+", cleaned) if p.strip()]
    first_seg = parts[0] if parts else cleaned.strip()

    # Tìm các từ tiếng Anh / Model thương hiệu (VD: CUKTECH, TRANYOO, PB200, MagSafe, Enchen, Ulanzi...)
    ascii_words = re.findall(r"\b[A-Za-z][A-Za-z0-9]{1,15}\b", cleaned)
    stop_words = {
        "max", "min", "mah", "pro", "new", "hot", "led", "usb", "type",
        "cho", "voi", "kem", "cua", "anh", "chup", "that", "san", "pham",
        "shopee", "tiktok", "chinh", "hang", "bao", "hanh", "thang", "cong",
        "suat", "dung", "luong", "sac", "phong", "tai", "nghe", "day", "nhet",
        "binh", "giu", "nhiet", "op", "lung", "quat", "mini", "gia", "do",
        "chong", "on", "chat", "luong", "cao", "da", "dang", "ket", "noi",
        "earphone", "headphone", "gaming", "laptop"
    }
    brand_tokens = []
    for w in ascii_words:
        wl = w.lower()
        if wl not in stop_words and wl not in brand_tokens:
            brand_tokens.append(wl)

    model_nums = re.findall(r"\b(?:[A-Za-z]{1,4}\d{1,5}[A-Za-z0-9]*|\d{1,3}\s*SE|\d{1,3}\s*Pro|\d{1,3}\s*Ultra)\b", cleaned, flags=re.I)
    model_str = " ".join(m.strip() for m in model_nums[:2]).strip()
    brand_str = " ".join(brand_tokens[:2]).strip()

    raw_lower = raw_title.lower()
    is_wired = any(k in raw_lower for k in ("tai nghe dây", "có dây", "tai nghe có dây", "dây nhét tai", "cắm dây", "jack 3.5"))

    queries = []
    if is_wired:
        if brand_str and model_str:
            queries.append(f"tai nghe có dây {brand_str} {model_str}")
            queries.append(f"{brand_str} {model_str} có dây")
        elif brand_str:
            queries.append(f"tai nghe có dây {brand_str}")
        queries.append(f"tai nghe có dây {first_seg}")
    else:
        if brand_str and model_str:
            queries.append(f"{brand_str} {model_str}")
            queries.append(f"{first_seg} {model_str}")
        if first_seg:
            queries.append(first_seg)
            queries.append(f"{first_seg} thực tế")
        if brand_str:
            queries.append(f"{brand_str} {first_seg}")

    dedup_q = []
    for q in queries:
        qn = re.sub(r"\s+", " ", q).strip()
        if qn and qn not in dedup_q:
            dedup_q.append(qn)

    return dedup_q or [raw_title[:45]], brand_tokens[:2]


def crawl_images_for_query(
    prefix: str,
    queries: list[str],
    count: int = 4,
    primary_og_image: str = "",
) -> list[str]:
    """Tải đủ `count` ảnh thật cho một sản phẩm, ưu tiên ảnh gốc từ link và lọc đúng thương hiệu."""
    REAL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    saved_urls: list[str] = []

    raw_first = queries[0] if queries else prefix
    smart_queries, brand_tokens = extract_exact_product_queries(raw_first)

    candidate_urls: list[str] = []
    if primary_og_image and primary_og_image.startswith("http"):
        candidate_urls.append(primary_og_image)

    all_search_queries = smart_queries + [q for q in queries if q not in smart_queries]
    for q in all_search_queries[:4]:
        try:
            urls = fetch_bing_image_urls(q, max_results=14)
            for u in urls:
                if u not in candidate_urls:
                    candidate_urls.append(u)
        except Exception as e:
            print(f"[Warn] Lỗi tìm ảnh cho '{q}': {e}")

    # Lọc bỏ các URL chứa tên hãng đối thủ không nằm trong brand_tokens của sản phẩm
    competitor_brands = {"ugreen", "anker", "baseus", "remax", "hoco", "romoss", "pisen", "cuktech", "xiaomi"}
    allowed_brands = set(brand_tokens)
    forbidden_brands = competitor_brands - allowed_brands if allowed_brands else set()

    filtered_urls = []
    for u in candidate_urls:
        ul = u.lower()
        if any(fb in ul for fb in forbidden_brands):
            continue
        filtered_urls.append(u)

    if len(filtered_urls) < count:
        filtered_urls = candidate_urls

    idx = 1
    for img_url in filtered_urls:
        if idx > count:
            break
        filename = f"{prefix}_{idx}.jpg"
        dest = REAL_ASSETS_DIR / filename
        if download_image_file(img_url, dest):
            try:
                import subprocess
                subprocess.run(
                    ["/usr/bin/sips", "-s", "format", "jpeg", str(dest), "--out", str(dest)],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            except Exception:
                pass
            print(f"  [OK] Đã tải ảnh thật: {filename} ({dest.stat().st_size // 1024} KB) <- {img_url[:70]}")
            saved_urls.append(f"/assets/real/{filename}")
            idx += 1

    return saved_urls


def crawl_all_default_products() -> None:
    product_queries = {
        "KALO-VN-882910": (
            "case",
            [
                "ốp lưng magsafe nhám mờ chống sốc iphone chụp thật",
                "matte magsafe shockproof iphone case product photo closeup",
                "ốp lưng chống sốc viền đệm khí bảo vệ camera iphone",
            ],
        ),
        "KALO-VN-774120": (
            "fan",
            [
                "quạt cầm tay mini phản lực turbo 100 cấp độ gió màn hình led",
                "portable handheld turbo fan 100 speed led display product photo",
                "quạt mini cầm tay phản lực tích điện",
            ],
        ),
        "KALO-VN-651092": (
            "mic",
            [
                "bộ 2 mic thu âm không dây cài áo kèm hộp sạc cho điện thoại",
                "wireless lavalier microphone charging case phone product photo",
                "mic cài áo không dây lọc ồn quay tiktok",
            ],
        ),
        "KALO-VN-540219": (
            "bottle",
            [
                "bình giữ nhiệt inox 316 hiển thị nhiệt độ có quai xách 800ml",
                "insulated stainless steel water bottle led temperature display product",
                "bình giữ nhiệt báo nhiệt độ nắp chạm kèm ống hút",
            ],
        ),
        "KALO-VN-492811": (
            "stand",
            [
                "giá đỡ điện thoại tablet hợp kim nhôm xoay 360 độ để bàn",
                "360 rotating aluminum foldable phone stand desk product photo",
                "chân đế xoay 360 hợp kim nhôm đỡ điện thoại ipad",
            ],
        ),
    }

    if not FEEDS_FILE.exists():
        print("Không tìm thấy file feed!")
        return

    products = json.loads(FEEDS_FILE.read_text(encoding="utf-8"))
    for p in products:
        ext_id = p["external_id"]
        if ext_id not in product_queries:
            continue
        prefix, queries = product_queries[ext_id]
        print(f"\n==> Đang crawl ảnh thật cho: {p['title']} ({ext_id})")
        urls = crawl_images_for_query(prefix, queries, count=4)
        gallery = p.get("image_Gallery", [])
        for i, item in enumerate(gallery):
            if i < len(urls):
                item["url"] = urls[i]

    FEEDS_FILE.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[HOÀN TẤT] Đã cập nhật toàn bộ ảnh sản phẩm THẬT vào feeds/kalodata_trending_vn.json!")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        prefix_arg = sys.argv[1]
        query_arg = sys.argv[2]
        result = crawl_images_for_query(prefix_arg, [query_arg, f"{query_arg} product photo"], count=4)
        print(json.dumps({"ok": True, "urls": result}))
    else:
        crawl_all_default_products()
