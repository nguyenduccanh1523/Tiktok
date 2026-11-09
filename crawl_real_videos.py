import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

YT_DLP = "/Users/nguyenduccanh/Documents/Ca_nhan/Tool/Tiktok/.venv/bin/yt-dlp"
ASSETS_DIR = Path("/Users/nguyenduccanh/Documents/Ca_nhan/Tool/Tiktok/assets/real")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def clean_brackets_preserve_brand(raw_title: str) -> str:
    """
    Loại bỏ các cụm khuyến mãi trong ngoặc, nhưng GIỮ LẠI tên thương hiệu bên trong ngoặc
    (Ví dụ: [TRANYOO] -> TRANYOO, [UGREEN] -> UGREEN, nhưng [QUÀ TẶNG 20/10] -> xóa).
    """
    promo_pattern = r"\[\s*(quà tặng|freeship|hàng mới|mua \d+|giảm \d+|hot|sale|chính hãng|bảo hành|mã|voucher|đã bán).*?\]"
    cleaned = re.sub(promo_pattern, " ", raw_title, flags=re.I)
    cleaned = re.sub(r"\(\s*(quà tặng|freeship|hàng mới|mua \d+|giảm \d+|hot|sale|chính hãng|bảo hành).*?\)", " ", cleaned, flags=re.I)
    # Giữ lại từ thương hiệu bên trong ngoặc vuông hoặc ngoặc đơn
    cleaned = re.sub(r"\[([^\]]+)\]", r" \1 ", cleaned)
    cleaned = re.sub(r"\(([^\)]+)\)", r" \1 ", cleaned)
    return cleaned


def simplify_product_query(raw_title: str) -> list[str]:
    """
    Rút gọn tên sản phẩm thương mại điện tử dài thành danh sách các từ khóa tìm kiếm
    chuyên tìm video REVIEW THỰC TẾ, TRÊN TAY, TEST TÍNH NĂNG (tuyệt đối KHÔNG tìm unboxing/mở hộp
    vì unboxing hay quay cảnh cắt thùng carton, bóc băng dính, thư cảm ơn mà không thấy hàng).
    """
    cleaned = clean_brackets_preserve_brand(raw_title)
    parts = [p.strip() for p in re.split(r"[|•\-–—/]+", cleaned) if p.strip()]
    first_seg = parts[0] if parts else cleaned.strip()
    first_seg = re.sub(
        r"\b(bảo hành\s*\d+\s*tháng|chính hãng|freeship|giá rẻ|sale|hot|quà tặng\s*\d+/\d+)\b",
        "",
        first_seg,
        flags=re.I,
    ).strip()

    ascii_tokens = re.findall(r"\b[A-Za-z0-9][A-Za-z0-9.+_-]{1,15}\b", cleaned)
    stop_ascii = {
        "max", "min", "mah", "va", "cho", "co", "bo", "kem", "voi", "pro", "new", "hot", "led",
        "tai", "nghe", "day", "nhet", "sac", "pin", "cap", "quat", "gia", "op", "lung", "binh",
        "mic", "hop", "so", "dan", "anh", "thanh", "vom", "am", "laptop", "gaming", "earphone",
        "headphone", "chong", "on", "chat", "luong", "cao", "da", "dang", "cong", "ket", "noi",
        "trong", "kich", "thuoc", "mau", "sac"
    }
    brand_model_tokens = [
        t
        for t in ascii_tokens
        if t.lower() not in stop_ascii and not re.match(r"^\d+(w|mah|ml|mm|cm|g|kg)$", t.lower())
    ]
    brand_model_str = " ".join(brand_model_tokens[:4]).strip()

    title_lower = cleaned.lower()
    raw_lower = raw_title.lower()
    is_wired_earphone = any(k in raw_lower for k in ("tai nghe dây", "có dây", "tai nghe có dây", "dây nhét tai", "cắm dây", "jack 3.5"))
    is_book_or_album = any(k in title_lower for k in ("scrapbook", "album", "sổ", "sách", "vở", "ảnh"))
    is_gadget = any(k in title_lower for k in ("sạc", "pin", "tai nghe", "mic", "quạt", "giá đỡ", "cáp", "đèn"))

    queries = []
    if is_wired_earphone:
        # Đặc trị tai nghe có dây: Bắt buộc kèm từ 'có dây' hoặc 'dây' để tránh nhầm sang tai nghe bluetooth
        if brand_model_str:
            queries.append(f"tai nghe có dây {brand_model_str}")
            queries.append(f"tai nghe dây {brand_model_str}")
            queries.append(f"{brand_model_str} tai nghe có dây")
            queries.append(brand_model_str)
        queries.append(f"tai nghe có dây {first_seg}")
        queries.append(f"tai nghe dây {first_seg}")
    elif is_book_or_album:
        if brand_model_str:
            queries.append(f"{brand_model_str} review")
            queries.append(f"{brand_model_str} flip through")
            queries.append(f"{brand_model_str} handmade")
        queries.append(f"{first_seg} review")
        queries.append(f"{first_seg} lật từng trang")
        queries.append(f"{first_seg} trên tay")
    elif is_gadget:
        if brand_model_str:
            queries.append(f"{brand_model_str} review")
            queries.append(f"{brand_model_str} test thực tế")
            queries.append(f"{brand_model_str} trên tay")
            queries.append(brand_model_str)
        queries.append(f"{first_seg} review")
        queries.append(f"{first_seg} trên tay")
        queries.append(f"{first_seg} test thực tế")
    else:
        if brand_model_str:
            queries.append(f"{brand_model_str} review")
            queries.append(f"{brand_model_str} trên tay")
            queries.append(brand_model_str)
        queries.append(f"{first_seg} review")
        queries.append(f"{first_seg} trên tay")
        queries.append(first_seg)

    out = []
    for q in queries:
        q_norm = re.sub(r"\s+", " ", q).strip()
        if q_norm and q_norm not in out:
            out.append(q_norm)
    return out or [raw_title[:45].strip()]


def find_short_video_ids(query: str, max_ids: int = 8) -> list[str]:
    encoded_q = urllib.parse.quote(f"{query} #shorts")
    url = f"https://www.youtube.com/results?search_query={encoded_q}&sp=EgIYAQ%253D%253D"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
    short_ids = re.findall(r'"reelWatchEndpoint":\{"videoId":"([a-zA-Z0-9_-]{11})"', html)
    if not short_ids:
        short_ids = re.findall(r'"/shorts/([a-zA-Z0-9_-]{11})"', html)
    if not short_ids:
        short_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)

    seen = []
    for vid in short_ids:
        if vid not in seen:
            seen.append(vid)
        if len(seen) >= max_ids:
            break
    return seen


def collect_candidate_short_ids(query_or_queries: str | list[str], min_count: int = 8) -> list[str]:
    if isinstance(query_or_queries, str):
        candidate_queries = simplify_product_query(query_or_queries)
    else:
        candidate_queries = []
        for q in query_or_queries:
            for sq in simplify_product_query(q):
                if sq not in candidate_queries:
                    candidate_queries.append(sq)

    all_vids: list[str] = []
    for q in candidate_queries:
        try:
            vids = find_short_video_ids(q, max_ids=8)
            print(f"[{q}] Found Short IDs: {vids}")
            for v in vids:
                if v not in all_vids:
                    all_vids.append(v)
            if len(all_vids) >= min_count:
                break
        except Exception as e:
            print(f"[Warn] Lỗi tìm Short ID cho '{q}': {e}")
    return all_vids


def download_single_short_id(vid: str, out_path: Path) -> bool:
    url = f"https://www.youtube.com/shorts/{vid}"
    cmd = [
        YT_DLP,
        "--js-runtimes", "node",
        "-S", "vcodec:h264,res:1080,ext:mp4",
        "-f", "bv*[vcodec^=avc1][ext=mp4]/b[vcodec^=avc1][ext=mp4]/18",
        "--match-filter", "duration <= 85 & duration >= 7",
        "--no-playlist",
        "-o", str(out_path),
        "--force-overwrites",
        url,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=65)
        if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 100_000:
            print(f"  -> Downloaded {out_path.name} ({out_path.stat().st_size // 1024} KB) from {url}")
            return True
        else:
            print(f"  -> Failed {vid}: {res.stderr[-180:]}")
    except Exception as e:
        print(f"  -> Exception downloading {vid}: {e}")
    return False


def download_short_mp4(query_or_queries: str | list[str], out_path: Path) -> bool:
    all_vids = collect_candidate_short_ids(query_or_queries, min_count=5)
    for vid in all_vids[:5]:
        if download_single_short_id(vid, out_path):
            return True
    return False


def download_multiple_short_mp4s(
    query_or_queries: str | list[str],
    prefix: str,
    count: int = 5,
    force_refresh: bool = False,
) -> list[Path]:
    """
    Đảm bảo tải đủ `count` (5) VIDEO NGUỒN HOÀN TOÀN KHÁC NHAU (5 YouTube Shorts IDs khác nhau)
    cho 1 sản phẩm:
      assets/real/{clean_prefix}_video_1.mp4
      assets/real/{clean_prefix}_video_2.mp4
      ...
      assets/real/{clean_prefix}_video_5.mp4
    Nhờ đó khi tạo 5 video cho 1 sản phẩm, mỗi video là 1 clip quay thực tế từ 1 người/bối cảnh khác nhau 100%!
    """
    if prefix.endswith("_video"):
        clean_prefix = prefix[:-6]
    else:
        clean_prefix = prefix

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    legacy_single = ASSETS_DIR / f"{clean_prefix}_video.mp4"
    v1_path = ASSETS_DIR / f"{clean_prefix}_video_1.mp4"
    if legacy_single.exists() and legacy_single.stat().st_size > 100_000 and not v1_path.exists():
        import shutil
        shutil.copy2(legacy_single, v1_path)

    existing_paths = []
    for i in range(1, count + 1):
        p = ASSETS_DIR / f"{clean_prefix}_video_{i}.mp4"
        if p.exists() and p.stat().st_size > 100_000 and not force_refresh:
            existing_paths.append(p)

    if len(existing_paths) >= count:
        return existing_paths

    all_vids = collect_candidate_short_ids(query_or_queries, min_count=count + 4)
    saved_paths: list[Path] = []
    vid_cursor = 0

    for idx in range(1, count + 1):
        target_path = ASSETS_DIR / f"{clean_prefix}_video_{idx}.mp4"
        if target_path.exists() and target_path.stat().st_size > 100_000 and not force_refresh:
            saved_paths.append(target_path)
            vid_cursor += 1
            continue

        downloaded = False
        while vid_cursor < len(all_vids):
            vid = all_vids[vid_cursor]
            vid_cursor += 1
            if download_single_short_id(vid, target_path):
                saved_paths.append(target_path)
                downloaded = True
                break
        if not downloaded and saved_paths:
            # Nếu mạng hết kết quả mới thì mới copy tạm từ clip trước
            import shutil
            shutil.copy2(saved_paths[-1], target_path)
            saved_paths.append(target_path)

    # Đồng bộ ngược lại {prefix}_video.mp4 cho tương thích
    if saved_paths and not legacy_single.exists():
        import shutil
        shutil.copy2(saved_paths[0], legacy_single)

    return saved_paths
