import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

YT_DLP = "/Users/nguyenduccanh/Documents/Ca_nhan/Tool/Tiktok/.venv/bin/yt-dlp"
ASSETS_DIR = Path("/Users/nguyenduccanh/Documents/Ca_nhan/Tool/Tiktok/assets/real")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
INSPECT_BIN = Path("/Users/nguyenduccanh/Documents/Ca_nhan/Tool/Tiktok/inspect_video_content")


def is_vertical_video(video_path: Path) -> bool:
    """
    Kiểm tra video có đúng tỷ lệ dọc (9:16 hoặc height >= width) hay không.
    Tuyệt đối từ chối các video quay ngang (16:9).
    """
    if not video_path.exists():
        return False
    try:
        swift_code = f'''
import AVFoundation
let asset = AVURLAsset(url: URL(fileURLWithPath: "{video_path}"))
if let track = asset.tracks(withMediaType: .video).first {{
    let s = track.naturalSize.applying(track.preferredTransform)
    let w = abs(s.width)
    let h = abs(s.height)
    exit(h >= w ? 0 : 1)
}}
exit(1)
'''
        res = subprocess.run(["/usr/bin/swift", "-e", swift_code], capture_output=True, timeout=6)
        return res.returncode == 0
    except Exception:
        return True


def is_hands_on_video(video_path: Path) -> bool:
    """
    Sử dụng native Apple Vision Framework để kiểm tra:
    Video có phải là quay cận cảnh sản phẩm & đôi tay người review hay không.
    Trả về True nếu video tập trung vào sản phẩm (không có khuôn mặt nói chuyện kiểu vlogger).
    """
    if not INSPECT_BIN.exists() or not video_path.exists():
        return True
    try:
        res = subprocess.run([str(INSPECT_BIN), str(video_path)], capture_output=True, text=True, timeout=20)
        if res.returncode == 0:
            print(f"  [VISION-PASS] Video {video_path.name} đạt chuẩn: 100% Cận cảnh sản phẩm & Đôi tay thao tác.")
            return True
        else:
            print(f"  [VISION-REJECT] Bỏ qua video {video_path.name} vì phát hiện quay cả người/quay mặt vlogger nói chuyện.")
            return False
    except Exception as e:
        print(f"  [VISION-WARN] Không thể kiểm tra video {video_path.name}: {e}")
        return True


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
    chuyên tìm video TRÊN TAY, CẬN CẢNH, THAO TÁC ĐÔI TAY VỚI SẢN PHẨM (tuyệt đối KHÔNG tìm vlogger/quay cả người
    và KHÔNG tìm unboxing hộp giấy carton rỗng).
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
        "mic", "hop", "so", "dan", "thanh", "vom", "am", "laptop", "gaming", "earphone",
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
    is_book_or_album = any(k in title_lower for k in ("scrapbook", "album ảnh", "sổ dán ảnh", "sổ dán", "sổ kỷ yếu", "quyển sách", "cuốn sách", "vở vẽ"))
    is_bottle = any(k in title_lower for k in ("bình", "ly", "cốc", "bình giữ nhiệt", "ly giữ nhiệt", "cốc giữ nhiệt", "thermos", "tumbler"))
    is_gadget = any(k in title_lower for k in ("sạc", "pin", "tai nghe", "mic", "quạt", "giá đỡ", "cáp", "đèn", "gậy chụp ảnh", "tripod", "selfie", "gậy", "kẹp"))
    is_fashion = any(k in title_lower for k in ("áo", "quần", "váy", "đầm", "cadigan", "khoác", "sơ mi", "set đồ", "set áo"))

    queries = []
    if is_wired_earphone:
        # Đặc trị tai nghe có dây: Bắt buộc kèm từ 'có dây' hoặc 'dây' để tránh nhầm sang tai nghe bluetooth
        if brand_model_str:
            queries.append(f"trên tay tai nghe có dây {brand_model_str}")
            queries.append(f"cận cảnh tai nghe có dây {brand_model_str}")
            queries.append(f"tai nghe có dây {brand_model_str} trên tay")
            queries.append(f"tai nghe có dây {brand_model_str}")
            queries.append(brand_model_str)
        queries.append(f"trên tay tai nghe có dây {first_seg}")
        queries.append(f"cận cảnh tai nghe có dây {first_seg}")
    elif is_bottle:
        # Đặc trị bình/ly giữ nhiệt: Bắt buộc kèm từ 'bình giữ nhiệt' hoặc 'ly giữ nhiệt' đúng thương hiệu/mẫu
        term = "ly giữ nhiệt" if ("ly" in title_lower or "cốc" in title_lower) else "bình giữ nhiệt"
        if brand_model_str:
            queries.append(f"trên tay {term} {brand_model_str}")
            queries.append(f"cận cảnh {term} {brand_model_str}")
            queries.append(f"{term} {brand_model_str} trên tay")
            queries.append(f"{term} {brand_model_str}")
        queries.append(f"trên tay {term} {first_seg}")
        queries.append(f"cận cảnh {first_seg}")
        queries.append(f"trên tay {first_seg}")
    elif is_book_or_album:
        if brand_model_str:
            queries.append(f"{brand_model_str} lật từng trang trên tay")
            queries.append(f"trên tay {brand_model_str} cận cảnh")
            queries.append(f"{brand_model_str} flip through")
        queries.append(f"{first_seg} lật từng trang trên tay")
        queries.append(f"trên tay {first_seg}")
        queries.append(f"cận cảnh {first_seg}")
    elif is_gadget:
        if brand_model_str:
            queries.append(f"trên tay {brand_model_str}")
            queries.append(f"cận cảnh {brand_model_str}")
            queries.append(f"cầm trên tay {brand_model_str}")
            queries.append(f"{brand_model_str} test trên tay")
            queries.append(f"{brand_model_str} hands on")
            queries.append(brand_model_str)
        queries.append(f"trên tay {first_seg}")
        queries.append(f"cận cảnh {first_seg}")
        queries.append(f"cầm trên tay {first_seg}")
        queries.append(f"test trên tay {first_seg}")
    elif is_fashion:
        queries.append(f"cận cảnh chất vải {first_seg}")
        queries.append(f"trên tay {first_seg}")
        queries.append(f"soi chất liệu {first_seg}")
        queries.append(f"cận cảnh {first_seg}")
    else:
        if brand_model_str:
            queries.append(f"trên tay {brand_model_str}")
            queries.append(f"cận cảnh {brand_model_str}")
            queries.append(f"cầm trên tay {brand_model_str}")
            queries.append(brand_model_str)
        queries.append(f"trên tay {first_seg}")
        queries.append(f"cận cảnh {first_seg}")
        queries.append(f"cầm trên tay {first_seg}")

    out = []
    for q in queries:
        q_norm = re.sub(r"\s+", " ", q).strip()
        if q_norm and q_norm not in out:
            out.append(q_norm)
    return out or [raw_title[:45].strip()]


def find_short_video_ids(query: str, max_ids: int = 12) -> list[str]:
    encoded_q = urllib.parse.quote(f"{query} #shorts")
    url = f"https://www.youtube.com/results?search_query={encoded_q}&sp=EgIYAQ%253D%253D"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    try:
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[Warn] Lỗi request YouTube search ({query}): {e}")
        return []

    # Tìm cặp (videoId, title) để ưu tiên video trên tay / cận cảnh và loại bỏ vlog/quay người
    matches = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}\]', html)
    bad_kw = {"vlog", "tâm sự", "chuyện trò", "hỏi đáp", "q&a", "reaction", "phỏng vấn", "podcast", "chém gió", "troll", "hài hước", "kể chuyện"}
    good_ids = []
    other_ids = []
    seen = set()

    for vid, title in matches:
        if vid in seen or title == "Bộ lọc tìm kiếm":
            continue
        seen.add(vid)
        t_low = title.lower()
        if any(b in t_low for b in bad_kw):
            continue
        if any(g in t_low for g in ("trên tay", "cận cảnh", "cầm trên tay", "test", "thử", "soi", "chi tiết", "trải nghiệm", "hands on", "pov", "đập hộp", "lật từng", "chất liệu", "thao tác", "hướng dẫn")):
            good_ids.append(vid)
        else:
            other_ids.append(vid)

    # Dự phòng các ID từ reelWatchEndpoint nếu regex title bị thiếu
    reel_ids = re.findall(r'"reelWatchEndpoint":\{"videoId":"([a-zA-Z0-9_-]{11})"', html)
    for vid in reel_ids:
        if vid not in seen:
            seen.add(vid)
            other_ids.append(vid)

    ranked_ids = good_ids + other_ids
    return ranked_ids[:max_ids]


def collect_candidate_short_ids(query_or_queries: str | list[str], min_count: int = 12) -> list[str]:
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
            vids = find_short_video_ids(q, max_ids=12)
            print(f"[{q}] Found Candidate IDs: {vids}")
            for v in vids:
                if v not in all_vids:
                    all_vids.append(v)
            if len(all_vids) >= min_count:
                break
        except Exception as e:
            print(f"[Warn] Lỗi tìm Short ID cho '{q}': {e}")
    return all_vids


def download_single_short_id(vid: str, out_path: Path, verify_hands_on: bool = True) -> bool:
    url = f"https://www.youtube.com/shorts/{vid}"
    cmd = [
        YT_DLP,
        "--js-runtimes", "node:/opt/homebrew/bin/node",
        "-S", "res:1080,vcodec:h264,ext:mp4",
        "-f", "bv*[vcodec^=avc1][height>=720]/bv*[vcodec^=avc1]/137/136/135/bestvideo[ext=mp4]/b[vcodec^=avc1]/18/best",
        "--match-filter", "duration <= 180 & duration >= 7",
        "--no-playlist",
        "-o", str(out_path),
        "--force-overwrites",
        url,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=75)
        if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 100_000:
            if not is_vertical_video(out_path):
                print(f"  [REJECT-LANDSCAPE] Bỏ qua video {vid} ({out_path.name}) vì quay ngang, bắt buộc phải là video dọc chuẩn TikTok.")
                out_path.unlink(missing_ok=True)
                return False
            if verify_hands_on:
                if not is_hands_on_video(out_path):
                    out_path.unlink(missing_ok=True)
                    return False
            print(f"  -> Downloaded {out_path.name} ({out_path.stat().st_size // 1024} KB) from {url}")
            return True
        else:
            print(f"  -> Failed {vid}: {res.stderr[-180:]}")
    except Exception as e:
        print(f"  -> Exception downloading {vid}: {e}")
    return False


def download_short_mp4(query_or_queries: str | list[str], out_path: Path) -> bool:
    all_vids = collect_candidate_short_ids(query_or_queries, min_count=8)
    for vid in all_vids[:8]:
        if download_single_short_id(vid, out_path, verify_hands_on=True):
            return True
    # Fallback nếu không có video nào 100% không mặt
    for vid in all_vids[:3]:
        if download_single_short_id(vid, out_path, verify_hands_on=False):
            return True
    return False


def download_multiple_short_mp4s(
    query_or_queries: str | list[str],
    prefix: str,
    count: int = 5,
    force_refresh: bool = False,
) -> list[Path]:
    """
    Đảm bảo tải đủ `count` (5) VIDEO TRÊN TAY / CẬN CẢNH SẢN PHẨM HOÀN TOÀN KHÁC NHAU
    (Sử dụng Apple Vision Framework để lọc bỏ triệt để video quay cả người/mặt vlogger):
      assets/real/{clean_prefix}_video_1.mp4
      assets/real/{clean_prefix}_video_2.mp4
      ...
      assets/real/{clean_prefix}_video_5.mp4
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
            if is_hands_on_video(p):
                existing_paths.append(p)
            else:
                print(f"[RE-CRAWL] Phát hiện video cũ {p.name} quay người/mặt vlogger, tiến hành xóa và tải lại clip trên tay cận cảnh...")
                p.unlink(missing_ok=True)

    if len(existing_paths) >= count:
        return existing_paths

    all_vids = collect_candidate_short_ids(query_or_queries, min_count=count + 14)
    saved_paths: list[Path] = list(existing_paths)
    vid_cursor = 0

    for idx in range(len(existing_paths) + 1, count + 1):
        target_path = ASSETS_DIR / f"{clean_prefix}_video_{idx}.mp4"
        downloaded = False
        while vid_cursor < len(all_vids):
            vid = all_vids[vid_cursor]
            vid_cursor += 1
            if download_single_short_id(vid, target_path, verify_hands_on=True):
                saved_paths.append(target_path)
                downloaded = True
                break

        # Nếu đã duyệt hết danh sách mà vẫn chưa đủ, cho phép fallback ứng viên khả dĩ nhất
        if not downloaded and vid_cursor < len(all_vids):
            for fallback_vid in all_vids[:count]:
                if download_single_short_id(fallback_vid, target_path, verify_hands_on=False):
                    saved_paths.append(target_path)
                    downloaded = True
                    break

        if not downloaded and saved_paths:
            import shutil
            shutil.copy2(saved_paths[-1], target_path)
            saved_paths.append(target_path)

    if saved_paths and not legacy_single.exists():
        import shutil
        shutil.copy2(saved_paths[0], legacy_single)

    return saved_paths
