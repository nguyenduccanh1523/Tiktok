# TikTok Affiliate AI Studio — Docker MVP Starter

> **Đây là bộ khởi tạo thực thi được, KHÔNG phải hệ thống sản xuất đã hoàn thiện.**
> - Đã có pipeline: nguồn JSON → chấm điểm → PostgreSQL → Redis Queue → Ollama → TTS → FFmpeg → MP4 + script + caption.
> - **Chưa có connector TikTok Shop hoạt động sẵn:** bạn cần quyền TikTok Shop Affiliate / seller Bestsellers hoặc nguồn dữ liệu hợp pháp. Chế độ mặc định sử dụng **dữ liệu DEMO mô phỏng**, không được công bố là doanh số thật.
> - **Chưa tự đăng TikTok**, chưa gắn sản phẩm giỏ hàng, chưa có UI quản trị/bảo vệ login nhiều người. Video đến trạng thái `review` để kiểm tra thủ công.
> - ClipForge chạy độc lập để thử dựng video nâng cao; **chưa tự động tích hợp ClipForge vào worker** trong bản khởi tạo này. Worker dùng FFmpeg chắc chắn có thể tích hợp và kiểm soát.
> - Các thư viện/ảnh/âm thanh/model vẫn cần kiểm tra giấy phép và điều khoản sử dụng thương mại trước khi đăng.

## 1. Yêu cầu

- Ubuntu 22.04/24.04 hoặc tương đương, Docker Engine + `docker-compose` hoặc `docker compose`.
- Khuyến nghị thử bản CPU: >= 8 vCPU / 16 GB RAM / SSD trống >= 30 GB; 4 vCPU/8 GB có thể chạy từng dịch vụ và thử với Edge TTS nhưng có thể chậm hoặc thiếu RAM khi chạy đầy đủ.
- Kết nối internet trong lần đầu để tải image, Ollama model và VieNeu model. Khi chọn VieNeu và model đã tải, AI/TTS/render có thể chạy offline; feed network thì vẫn cần internet.
- `curl`, `git` để tiện kiểm thử.

## 2. Cài đặt

```bash
unzip tiktok-affiliate-ai-starter.zip
cd tiktok-affiliate-ai-starter
cp .env.example .env
# Sửa POSTGRES_PASSWORD, API_KEY. Đừng commit .env lên Git.
nano .env

docker-compose -f compose.yaml config
docker-compose -f compose.yaml up -d --build
# nếu máy dùng Docker Compose V2, thay docker-compose bằng docker compose

docker-compose -f compose.yaml exec ollama ollama pull qwen2.5:3b
# kiểm tra
curl http://127.0.0.1:8008/health
```

### Kiểm tra luồng demo

```bash
KEY=$(grep '^API_KEY=' .env | cut -d= -f2-)
# Chấm điểm dữ liệu demo, ghi DB, tự vào queue TOP 1
curl -X POST http://127.0.0.1:8008/discover -H "X-API-Key: $KEY"
# Xem sản phẩm và job
curl http://127.0.0.1:8008/products -H "X-API-Key: $KEY"
curl http://127.0.0.1:8008/jobs -H "X-API-Key: $KEY"
docker-compose -f compose.yaml logs -f worker
```

**Trường hợp job `failed`:** xem trường `error` trong `/jobs`, model Ollama đã được `pull` chưa và worker đã tải model VieNeu chưa. Thử `TTS_BACKEND=edge` cho smoke test nhanh, sau đó `docker-compose up -d --force-recreate worker`. Edge TTS yêu cầu internet và **không nên mặc nhiên giả định quyền sử dụng thương mại**.

Output trên host nằm ở `./output/<job-id>/`:
- `video.mp4`: 1080x1920, H.264/AAC, video 9:16
- `voice.wav` hoặc `voice.mp3`
- `script.txt`, `caption.txt`, `subtitles.srt`

Các video nguồn `demo` có watermark **DEMO - KHONG DANG** và caption DEMO. Không đăng sản phẩm demo lên TikTok.

### Mở ClipForge (độc lập)

`http://127.0.0.1:3000` — thử ảnh sản phẩm thuộc quyền sử dụng của bạn. ClipForge chạy riêng, không tự nhận job từ worker của bộ khởi tạo. Khi tích hợp cần map output/CLI/API thật của phiên bản đã pin và kiểm thử worker adapter.

## 3. Kết nối nguồn sản phẩm được phép

MVP có 2 adapter:

- `FEED_MODE=file`: đọc file `/workspace/feeds/demo_products.json`; có thể thay bằng JSON xuất từ nguồn mà bạn được phép sử dụng.
- `FEED_MODE=authorized_json`: đọc `FEED_URL` qua HTTPS với tùy chọn bearer token. Endpoint này phải do bạn hoặc nhà cung cấp có quyền truy cập vận hành, trả về JSON array theo schema mẫu; **không phải TikTok API tự động có sẵn**.

Mỗi object yêu cầu tối thiểu `source`, `external_id`, `title`, `image_files`, `affiliate_url`, `metrics_date`, `sales_7d`, và các cờ xác nhận chất lượng. Xem mẫu trong `feeds/demo_products.json`.

### Quy tắc xếp hạng sơ bộ

`score = 100*(0.45*volume_norm + 0.25*growth_norm + 0.15*rating_norm + 0.15*commission_norm)`

Chỉ số `volume_norm` chuẩn hóa theo log và theo tập dữ liệu được nạp; `growth_norm` chặn tại 100%, `rating_norm` tối đa 5.0, `commission_norm` tối đa 30%. Đây là **điểm nội bộ để ưu tiên**, không phải chứng nhận "Top bán chạy TikTok". Nếu thiếu số lượng bán ra/ ngày đo thì score null. Quyền dùng ảnh/spec/affiliate vẫn phải duyệt độc lập. Cần bổ sung tỷ lệ hoàn/trả hàng, mức cạnh tranh, lợi nhuận và đánh giá gian lận nếu có dữ liệu.

### Bảo vệ chất lượng trước khi tạo video

Hàng được tạo video tự động chỉ khi:

1. Có ảnh nguồn nằm tại `/workspace/assets`, thuộc quyền sử dụng của bạn.
2. `asset_rights_verified=true`, `specifications_verified=true`, `affiliate_eligible=true` (do quy trình kiểm duyệt hoặc nguồn đáng tin xác nhận).
3. Có `affiliate_url`, số liệu xếp hạng đủ dùng.
4. Không bị trùng (source + external ID), job cùng sản phẩm/cùng ngày/cùng biến thể cũng chỉ tạo một lần.
5. `DEMO_MODE=false` ở môi trường thật (và không có dữ liệu `source=demo`).

**Lưu ý:** cờ true trong JSON không thay thế kiểm chứng thật. Hệ thống mặc định chỉ xuất trạng thái `review`, tuyệt đối không tự post. Có thể thêm bước tự xác minh specs bằng nguồn người bán có quyền và luật duyệt của người vận hành.

## 4. Tách service & bổ sung production

- `api`: REST API. Mặc định chỉ bind `127.0.0.1:8008`, bảo vệ X-API-Key.
- `scheduler`: mỗi ngày 08:00 Asia/Bangkok chạy discovery. Bạn có thể POST `/discover` ngay để thử.
- `worker`: một RQ worker tạo lần lượt video; dùng RabbitMQ/Celery nếu cần độ phức tạp cao hơn.
- `ollama`: LLM chạy local, model cần pull riêng.
- `postgres` + `redis`: không mở port ra Internet; dữ liệu trong named volumes.
- `clipforge`: giao diện tùy chọn, giữ độc lập; bind `127.0.0.1:3000`.

**Chưa sẵn production:** TLS và login dashboard, giới hạn tài nguyên CPU/RAM, bộ lọc blacklist sản phẩm, backpressure queue, retry/backoff, metrics/alerting, audit log, bản quyền media có bằng chứng, xác minh thông số có nguồn, API quyền TikTok Shop, A/B analytics, retention cleanup, export backup, job dead-letter queue, quản trị model và giới hạn thời lượng, chống prompt injection từ mô tả nguồn.

### Bảo mật thiết yếu
- Tuyệt đối không public Redis / PostgreSQL / Ollama / ClipForge trực tiếp; dùng VPN hoặc Nginx có TLS + SSO khi cần truy cập từ xa.
- Đổi API_KEY/POSTGRES_PASSWORD; không đưa `.env` vào repo.
- Giới hạn quyền đọc ảnh, lưu bằng chứng license cho từng ảnh, tránh tải ảnh URL không rõ quyền và SSRF.
- Dùng service account/API token với quyền tối thiểu, tránh cookie scraping, captcha bypass và tự login TikTok bằng bot.
- Back up Postgres `pg_dump` và named volumes chứa ảnh/output/ClipForge trước mọi lần upgrade.
- Pin các image tag/digest sau khi smoke test thành công thay vì luôn dùng `latest`.

## 5. API

- `GET /health` — kiểm tra API
- `POST /discover` — đồng bộ feed, chấm điểm, xếp hạng, auto queue
- `GET /products` — danh sách ứng viên
- `POST /products/{id}/render?variant=2` — tạo biến thể thứ 2 (tối đa 20)
- `GET /jobs` — tiến độ và thông báo lỗi
- `GET /jobs/{id}/video` — tải MP4 khi status `review`
- `GET /docs` — FastAPI Swagger (chỉ có thể truy cập local, API cần khóa)

Để sinh lại một job cùng ngày/biến thể, hệ thống hiện yêu cầu chọn `variant` khác; production bổ sung `retry` chuẩn và metadata lỗi theo bước.

## 6. Kế hoạch thực hiện

| Ngày | Mục tiêu | Pass |
|---|---|---|
| 1 | Compose, Postgres, Redis, Ollama | health 200, model pull thành công |
| 2 | Import feed hợp pháp và kiểm chứng dữ liệu | ingest >= 10 sản phẩm không trùng, có source và thời điểm số liệu |
| 3 | Ranking & quality gate | thiếu metric/quyền ảnh -> không chạy video |
| 4 | Ollama script & validation | 5 script phù hợp, không bịa features |
| 5 | VieNeu TTS + FFmpeg | 5 MP4 phát được, nghe tiếng Việt, phụ đề không che sản phẩm |
| 6 | ClipForge thử 2 template + human QA | 2 video đạt chuẩn hình ảnh/thông tin |
| 7 | Chạy lịch và đo thời gian | 1 batch đầu-cuối, kiểm duyệt và tải MP4 thành công |

## 7. KPI đo thử

- Tỷ lệ job hoàn thành >= 90% trong 20 video thử (đây là **mục tiêu thử nghiệm**, không phải kết quả đã đạt).
- 100% video không bịa tính năng và ảnh đúng sản phẩm sau duyệt thủ công.
- 100% clip có voice, caption, 9:16, MP4, không vượt phạm vi quyền media.
- Không có TikTok automation đăng hàng loạt cho đến khi quy trình cấp quyền và policy được đánh giá.

## 8. Tham khảo

- https://github.com/xixihhhh/clipforge
- https://github.com/pnnbao97/VieNeu-TTS
- https://github.com/ollama/ollama
- https://github.com/gyoridavid/short-video-maker
- https://partner.tiktokshop.com/docv2/page/3dk9557y
- https://partner.tiktokshop.com/docv2/page/affiliate-integration

## Lưu ý về mã nguồn
Bộ starter chỉ chứa mã do trợ lý tạo ra; không nhúng mã từ các repository trên. Khi dùng dịch vụ/repo bên thứ ba, tuân thủ license của từng thành phần (ClipForge: AGPL-3.0; VieNeu-TTS: Apache-2.0; n8n Community nếu dùng thêm: fair-code), và kiểm tra model weights/media/license riêng.
