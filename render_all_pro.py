#!/usr/bin/env python3
"""
Tổ chức lại thư mục ./output/ sao cho MỖI SẢN PHẨM LÀ 1 THƯ MỤC RIÊNG:
  ./output/<ma_sp>_<ten_sp>/
    ├── video_1.mp4
    ├── video_2.mp4
    ...
Và kết xuất sẵn các video sạch (đã cắt bỏ 100% ảnh/logo góc dưới).
"""
import shutil
from pathlib import Path
import app

app.ensure_directories()

# Xóa danh sách job cũ để đồng bộ sang cấu trúc thư mục từng sản phẩm mới
state = app.load_state()
state["jobs"] = []
app.save_state(state)

products = app.get_all_products()

for p in products:
    print(f"==> Đang tạo Video vào thư mục riêng cho: {p['title'][:45]}...")
    # Tạo sẵn Biến thể #1 (Hybrid: Video thật + Cận cảnh ảnh thật)
    pack_1 = app.build_affiliate_script(p, variant_index=1)
    j1 = app.generate_real_mp4_job(
        product=p,
        scenes=pack_1["scenes"],
        caption=pack_1["caption"],
        variant_index=1,
        visual_mode="real_video",
    )
    print(f"  [OK] {j1['output_dir']} -> {j1['video_file_name']} ({j1['video_size_mb']} MB)")

# Dọn các thư mục tạm cũ (clean_*, ready_*, pro_adam_*) để thư mục ./output/ chỉ còn đúng 5 thư mục của 5 sản phẩm
for child in app.OUTPUT_DIR.iterdir():
    if child.is_dir() and (
        child.name.startswith("clean_")
        or child.name.startswith("ready_")
        or child.name.startswith("pro_adam_")
    ):
        shutil.rmtree(child, ignore_errors=True)

print("==> Hoàn tất chuẩn hóa thư mục theo từng sản phẩm!")
