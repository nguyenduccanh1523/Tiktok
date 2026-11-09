/**
 * TikTok Affiliate Video AI — Frontend tinh gọn & tự động hóa:
 * - Mỗi sản phẩm có 5 Biến thể kịch bản/góc máy khác nhau (không bao giờ trùng lặp nhàm chán)
 * - Hỗ trợ nút "Tạo Trọn Bộ 5 Video Khác Nhau" hoặc mỗi lần bấm Tạo tự nhảy sang biến thể mới
 * - Crawl sản phẩm mới chỉ cần dán 1 Link TikTok/Shopee hoặc Tên sản phẩm
 * - Lưu riêng từng sản phẩm vào 1 thư mục độc lập: ./output/<ma_sp>_<ten_sp>/
 */

const state = {
  products: [],
  selectedProduct: null,
  variantIndex: 1,
  visualMode: "hybrid",
  scenes: [],
  caption: "",
  currentJob: null,
  productJobs: [],
  keysStatus: {},
};

const VARIANT_LABELS = [
  "Biến thể #1 (Hook Cảnh Báo)",
  "Biến thể #2 (Mở Hộp Thực Tế)",
  "Biến thể #3 (Test Trải Nghiệm)",
  "Biến thể #4 (Soi Chất Liệu)",
  "Biến thể #5 (Tổng Kết Ưu Điểm)",
];

const productStripEl = document.getElementById("product-strip");
const variantTabsEl = document.getElementById("variant-tabs");
const visualModeSelectEl = document.getElementById("visual-mode-select");
const btnBatch5El = document.getElementById("btn-batch-5");
const realPhotosGridEl = document.getElementById("real-photos-grid");
const scenesScriptListEl = document.getElementById("scenes-script-list");
const captionInputEl = document.getElementById("caption-input");
const videoPlayerEl = document.getElementById("real-video-player");
const savedVariantsStripEl = document.getElementById("saved-variants-strip");
const renderingOverlayEl = document.getElementById("rendering-overlay");
const renderingStatusTextEl = document.getElementById("rendering-status-text");
const videoMetaBadgeEl = document.getElementById("video-meta-badge");
const engineStatusPillEl = document.getElementById("engine-status-pill");
const btnDownloadMp4El = document.getElementById("btn-download-mp4");
const btnDownloadVoiceEl = document.getElementById("btn-download-voice");
const btnDownloadScriptEl = document.getElementById("btn-download-script");
const savedFolderPathEl = document.getElementById("saved-folder-path");
const btnRenderMp4El = document.getElementById("btn-render-mp4");

function formatNum(n) {
  return Number(n || 0).toLocaleString("vi-VN");
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function updateEngineStatusPill(keysStatus) {
  state.keysStatus = keysStatus || {};
  const parts = ["🎬 Khung Hình Sạch 100% (Đã cắt góc thừa)"];
  if (state.keysStatus.has_gemini) {
    parts.push("🎙️ Gemini AI Voice (Charon Male)");
  } else if (state.keysStatus.has_elevenlabs) {
    parts.push("🎙️ ElevenLabs Adam Active");
  } else {
    parts.push("🎙️ Giọng Nam Nhanh (Adam DSP)");
  }
  parts.push("📁 Lưu Riêng Từng Thư Mục SP");
  engineStatusPillEl.textContent = parts.join(" • ");
}

async function bootstrap() {
  const res = await fetch("/api/bootstrap");
  const data = await res.json();
  state.products = data.products || [];
  updateEngineStatusPill(data.keys_status);
  renderProductStrip();

  if (state.products.length > 0) {
    await selectProduct(state.products[0].external_id, 1);
  }
}

function renderProductStrip() {
  productStripEl.innerHTML = "";
  state.products.forEach((prod, idx) => {
    const firstImg =
      prod.image_Gallery && prod.image_Gallery[0] ? prod.image_Gallery[0].url : "";
    const isActive =
      state.selectedProduct && state.selectedProduct.external_id === prod.external_id;

    const item = document.createElement("div");
    item.className = `prod-item ${isActive ? "active" : ""}`;
    item.setAttribute("role", "listitem");
    item.tabIndex = 0;

    item.innerHTML = `
      <img src="${firstImg}" alt="${escapeHtml(prod.title)}" class="prod-thumb">
      <div class="prod-info">
        <h3 class="prod-name">#${idx + 1}. ${escapeHtml(prod.title)}</h3>
        <div class="prod-meta">
          <span>Bán 7N: <strong>${formatNum(prod.sales_7d)}</strong></span>
          <span>AI Score: <strong>${prod.score}</strong></span>
        </div>
      </div>
    `;

    item.addEventListener("click", () => selectProduct(prod.external_id, 1));
    item.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectProduct(prod.external_id, 1);
      }
    });
    productStripEl.appendChild(item);
  });
}

async function selectProduct(productId, variantIndex = 1) {
  state.variantIndex = variantIndex;
  const res = await fetch("/api/prepare-product", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id: productId, variant_index: variantIndex }),
  });
  const data = await res.json();
  if (!data.ok) return;

  state.selectedProduct = data.product;
  state.scenes = data.script_pack.scenes || [];
  state.caption = data.script_pack.caption || "";
  state.productJobs = data.product_jobs || [];
  captionInputEl.value = state.caption;

  renderProductStrip();
  renderVariantTabs();
  renderRealPhotos();
  renderScriptInputs();
  renderSavedVariantsStrip();

  if (data.latest_job && Number(data.latest_job.variant_index || 1) === variantIndex) {
    loadJobIntoPlayer(data.latest_job);
  } else if (data.latest_job) {
    loadJobIntoPlayer(data.latest_job);
  } else {
    await triggerRenderMp4(variantIndex, false);
  }
}

function renderVariantTabs() {
  if (!variantTabsEl) return;
  variantTabsEl.innerHTML = "";
  for (let v = 1; v <= 5; v++) {
    const existing = state.productJobs.find((j) => Number(j.variant_index || 1) === v);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `variant-tab-btn ${state.variantIndex === v ? "active" : ""}`;
    btn.innerHTML = `
      <span>${VARIANT_LABELS[v - 1]}</span>
      <span class="v-status">${existing ? "✓ Đã có video_" + v + ".mp4" : "Chưa dựng"}</span>
    `;
    btn.addEventListener("click", () => {
      if (state.selectedProduct) {
        selectProduct(state.selectedProduct.external_id, v);
      }
    });
    variantTabsEl.appendChild(btn);
  }
}

function renderSavedVariantsStrip() {
  if (!savedVariantsStripEl) return;
  savedVariantsStripEl.innerHTML = "";
  if (!state.productJobs || state.productJobs.length === 0) {
    return;
  }
  state.productJobs.forEach((job) => {
    const vIdx = Number(job.variant_index || 1);
    const isCurrent = state.currentJob && state.currentJob.job_id === job.job_id;
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `saved-chip ${isCurrent ? "active" : ""}`;
    chip.textContent = `▶ video_${vIdx}.mp4 (${job.total_duration_sec}s)`;
    chip.addEventListener("click", () => {
      state.variantIndex = vIdx;
      loadJobIntoPlayer(job);
      renderVariantTabs();
      renderSavedVariantsStrip();
    });
    savedVariantsStripEl.appendChild(chip);
  });
}

function renderRealPhotos() {
  realPhotosGridEl.innerHTML = "";
  state.scenes.forEach((sc, idx) => {
    const card = document.createElement("div");
    card.className = "photo-card";
    const fileInputId = `photo-upload-${idx}`;
    card.innerHTML = `
      <div class="photo-wrap">
        <img src="${sc.image_url}" alt="Ảnh thật cảnh ${idx + 1}">
      </div>
      <div class="photo-caption">Cảnh #${idx + 1} (${escapeHtml(sc.motion)})</div>
      <div>
        <label for="${fileInputId}" class="btn-change-photo">📷 Đổi ảnh thật khác</label>
        <input type="file" id="${fileInputId}" name="photo_${idx}" accept="image/*" class="visually-hidden" data-idx="${idx}">
      </div>
    `;
    realPhotosGridEl.appendChild(card);

    card.querySelector(`#${fileInputId}`).addEventListener("change", async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const dataUrl = await fileToDataURL(file);
      const upRes = await fetch("/api/upload-scene-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data_url: dataUrl }),
      });
      const upData = await upRes.json();
      if (upData.ok) {
        state.scenes[idx].image_url = upData.image_url;
        renderRealPhotos();
        renderScriptInputs();
      }
    });
  });
}

function renderScriptInputs() {
  scenesScriptListEl.innerHTML = "";
  state.scenes.forEach((sc, idx) => {
    const row = document.createElement("div");
    row.className = "script-row";
    row.innerHTML = `
      <img src="${sc.image_url}" alt="Thumb cảnh ${idx + 1}">
      <div class="script-input-wrap">
        <label for="narration-input-${idx}">Câu thoại #${idx + 1} (Biến thể #${state.variantIndex}):</label>
        <input type="text" id="narration-input-${idx}" name="narration_${idx}" value="${escapeHtml(sc.narration)}" data-idx="${idx}">
      </div>
    `;
    scenesScriptListEl.appendChild(row);

    row.querySelector("input").addEventListener("input", (e) => {
      state.scenes[idx].narration = e.target.value;
    });
  });
}

function loadJobIntoPlayer(job) {
  state.currentJob = job;
  const cacheBust = `?t=${Date.now()}`;
  videoPlayerEl.src = `${job.video_url}${cacheBust}`;
  videoPlayerEl.load();
  videoPlayerEl.play().catch(() => {});

  const vIdx = Number(job.variant_index || 1);
  const fileName = job.video_file_name || `video_${vIdx}.mp4`;
  videoMetaBadgeEl.textContent = `${fileName} • ${job.total_duration_sec}s • ${job.video_size_mb} MB`;

  btnDownloadMp4El.href = job.video_url;
  btnDownloadMp4El.download = `${job.product_id.toLowerCase()}_video_${vIdx}.mp4`;
  btnDownloadMp4El.textContent = `⬇ LƯU ${fileName.toUpperCase()} VỀ MÁY`;

  btnDownloadVoiceEl.href = job.audio_url;
  btnDownloadVoiceEl.download = `voice_${vIdx}.m4a`;

  if (btnDownloadScriptEl && job.script_url) {
    btnDownloadScriptEl.href = job.script_url;
    btnDownloadScriptEl.download = `script_${vIdx}.txt`;
  }

  savedFolderPathEl.textContent = job.output_dir;
  renderSavedVariantsStrip();
}

async function triggerRenderMp4(targetVariant = null, advanceVariant = false) {
  if (!state.selectedProduct) return;

  if (advanceVariant) {
    const nextV = (state.variantIndex % 5) + 1;
    await selectProduct(state.selectedProduct.external_id, nextV);
  }

  const vToRender = targetVariant || state.variantIndex;
  const visualMode = visualModeSelectEl ? visualModeSelectEl.value : "hybrid";

  renderingOverlayEl.hidden = false;
  if (renderingStatusTextEl) {
    renderingStatusTextEl.textContent = `Đang dựng Biến thể #${vToRender} (video_${vToRender}.mp4)...`;
  }
  btnRenderMp4El.disabled = true;

  try {
    const res = await fetch("/api/render-mp4", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_id: state.selectedProduct.external_id,
        scenes: state.scenes,
        caption: captionInputEl.value,
        variant_index: vToRender,
        visual_mode: visualMode,
      }),
    });
    const data = await res.json();
    if (!data.ok) {
      throw new Error(data.error || "Không thể kết xuất MP4");
    }
    state.productJobs = data.product_jobs || state.productJobs;
    loadJobIntoPlayer(data.job);
    renderVariantTabs();
  } catch (err) {
    alert(`Lỗi tạo video: ${err.message}`);
  } finally {
    renderingOverlayEl.hidden = true;
    btnRenderMp4El.disabled = false;
  }
}

async function triggerBatch5() {
  if (!state.selectedProduct) return;
  renderingOverlayEl.hidden = false;
  btnBatch5El.disabled = true;
  btnRenderMp4El.disabled = true;

  if (renderingStatusTextEl) {
    renderingStatusTextEl.textContent =
      "Đang tự động dựng trọn bộ 5 Video khác nhau (video_1..5.mp4) vào thư mục riêng của sản phẩm...";
  }

  try {
    const res = await fetch("/api/render-batch-5", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_id: state.selectedProduct.external_id,
        visual_mode: visualModeSelectEl.value || "real_video",
      }),
    });
    const data = await res.json();
    if (!data.ok) {
      throw new Error(data.error || "Lỗi tạo 5 video");
    }
    state.productJobs = data.product_jobs || [];
    if (data.jobs && data.jobs.length > 0) {
      loadJobIntoPlayer(data.jobs[0]);
    }
    renderVariantTabs();
    renderSavedVariantsStrip();
  } catch (err) {
    alert(`Lỗi tạo 5 video: ${err.message}`);
  } finally {
    renderingOverlayEl.hidden = true;
    btnBatch5El.disabled = false;
    btnRenderMp4El.disabled = false;
  }
}

function fileToDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onloadend = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

function initEvents() {
  document.getElementById("render-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    // Mỗi lần bấm nút Tạo -> tự động chuyển sang biến thể mới để không bao giờ bị trùng lặp video
    await triggerRenderMp4(null, true);
  });

  if (btnBatch5El) {
    btnBatch5El.addEventListener("click", () => {
      triggerBatch5();
    });
  }

  // Modal API Keys
  const keysDialog = document.getElementById("keys-dialog");
  const geminiKeyInput = document.getElementById("gemini-key-input");
  const elevenlabsKeyInput = document.getElementById("elevenlabs-key-input");

  document.getElementById("btn-open-keys-modal").addEventListener("click", () => {
    geminiKeyInput.value = state.keysStatus.gemini_masked || "";
    elevenlabsKeyInput.value = state.keysStatus.elevenlabs_masked || "";
    keysDialog.showModal();
  });
  document.getElementById("btn-close-keys").addEventListener("click", () => keysDialog.close());
  document.getElementById("btn-cancel-keys").addEventListener("click", () => keysDialog.close());

  document.getElementById("keys-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const res = await fetch("/api/save-keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        gemini_api_key: geminiKeyInput.value.trim(),
        elevenlabs_api_key: elevenlabsKeyInput.value.trim(),
      }),
    });
    const data = await res.json();
    if (data.ok) {
      updateEngineStatusPill(data.keys_status);
      keysDialog.close();
      await triggerRenderMp4(state.variantIndex, false);
    }
  });

  // Modal Crawl Sản Phẩm Mới (Chỉ 1 ô nhập Link hoặc Tên)
  const dialog = document.getElementById("crawl-dialog");
  const crawlQueryInput = document.getElementById("crawl-query");
  const crawlErrorEl = document.getElementById("crawl-error");

  document.getElementById("btn-open-crawl-modal").addEventListener("click", () => {
    crawlQueryInput.value = "";
    crawlErrorEl.textContent = "";
    dialog.showModal();
  });
  document.getElementById("btn-close-modal").addEventListener("click", () => dialog.close());
  document.getElementById("btn-cancel-modal").addEventListener("click", () => dialog.close());

  crawlQueryInput.addEventListener("input", () => {
    crawlQueryInput.setCustomValidity("");
    crawlErrorEl.textContent = "";
  });

  document.getElementById("crawl-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (crawlQueryInput.value.trim().length < 3) {
      crawlErrorEl.textContent = "Vui lòng dán Link sản phẩm hoặc nhập Tên sản phẩm.";
      crawlQueryInput.focus();
      return;
    }

    const submitBtn = document.getElementById("btn-submit-crawl");
    submitBtn.disabled = true;
    submitBtn.textContent = "⏳ AI đang phân tích Link, tải ảnh/video thật & dựng MP4...";

    try {
      const res = await fetch("/api/crawl-new-product", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: crawlQueryInput.value.trim(),
        }),
      });
      const data = await res.json();
      if (!data.ok) {
        throw new Error(data.error || "Không crawl được sản phẩm");
      }

      state.products = data.products;
      dialog.close();
      await selectProduct(data.product.external_id, 1);
    } catch (err) {
      crawlErrorEl.textContent = err.message;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "⚡ Tự Động Crawl & Tạo Video Ngay";
    }
  });
}

initEvents();
bootstrap();
