/**
 * Frontend Controller JS for CineVault AList Media Center
 * Handles:
 * - Homepage Hero Banner Carousel
 * - One-click MPC-HC External Player Launch (/api/play)
 * - Guided API Key Setup Wizard & Connectivity Tester (/api/settings, /api/settings/test)
 * - Add Media Modal: AList Directory Browser + DeepSeek AI Name De-obfuscator + TMDB Matcher
 * - TV Series Season & Episode Selector + Episode Still Cards + Watch Progress Tracking
 * - Admin Backend: Logo/Poster/Backdrop/Source/Season Switcher & TMDB Rematcher
 */

function showToast(message, type = "info", duration = 4200) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const colors = {
    success: "border-emerald-500/50 bg-emerald-950/90 text-emerald-100",
    error: "border-rose-500/50 bg-rose-950/90 text-rose-100",
    info: "border-blue-500/50 bg-slate-900/95 text-slate-100",
  };
  const icons = {
    success: "✓",
    error: "✕",
    info: "🎬",
  };

  const el = document.createElement("div");
  el.className = `flex items-center gap-3 px-4 py-3 rounded-xl border shadow-2xl backdrop-blur-md text-sm font-medium transition-all duration-300 transform translate-y-0 opacity-100 ${colors[type] || colors.info}`;
  el.innerHTML = `
    <span class="inline-flex items-center justify-center w-6 h-6 rounded-full bg-white/10 text-xs font-bold shrink-0">${icons[type] || "i"}</span>
    <div class="flex-1 leading-snug">${message}</div>
  `;
  container.appendChild(el);

  setTimeout(() => {
    el.classList.add("opacity-0", "translate-y-2");
    setTimeout(() => el.remove(), 300);
  }, duration);
}

/* ============================================================
 * 1. MPC-HC External Player Invocation (/api/play)
 * ============================================================ */
async function playWithMpcHc(mediaId, seasonNumber = null, episodeNumber = null, episodeId = null, customPath = null) {
  showToast("正在请求 AList 直链并唤起本地 MPC-HC 播放器...", "info", 2800);
  try {
    const resp = await fetch("/api/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        media_id: mediaId,
        season_number: seasonNumber,
        episode_number: episodeNumber,
        episode_id: episodeId,
        alist_path: customPath,
      }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.error || "启动 MPC-HC 失败");
    }
    showToast(
      `已调用 MPC-HC 播放：<strong>${data.title || "视频"}</strong> (PID: ${data.pid})`,
      "success",
      4500
    );

    // If on detail page or homepage, update episode watched UI if applicable
    if (data.episode) {
      markEpisodeWatchedUI(data.episode.season_number, data.episode.episode_number, data.media);
    }
  } catch (err) {
    showToast(`播放失败: ${err.message}`, "error", 5000);
  }
}

/* ============================================================
 * 2. Watch Progress Tracking (/api/progress)
 * ============================================================ */
async function updateWatchProgress(payload, reloadAfter = false) {
  try {
    const resp = await fetch("/api/progress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.error || "更新进度失败");
    }
    showToast(
      `已更新《${data.media.title}》观看进度：${data.media.progress_percent}%`,
      "success",
      2500
    );
    if (reloadAfter) {
      setTimeout(() => window.location.reload(), 450);
    }
    return data;
  } catch (err) {
    showToast(`进度更新失败: ${err.message}`, "error");
    return null;
  }
}

function markEpisodeWatchedUI(seasonNum, episodeNum, mediaData) {
  const pill = document.querySelector(`[data-ep-pill="${seasonNum}-${episodeNum}"]`);
  if (pill) {
    pill.classList.add("ring-1", "ring-emerald-500/60");
  }
  const progressText = document.getElementById("detail-progress-label");
  if (progressText && mediaData) {
    progressText.textContent = `当前进度：第 ${mediaData.current_season} 季 · 第 ${mediaData.current_episode} 集 (${mediaData.progress_percent}%)`;
  }
  const progressBar = document.getElementById("detail-progress-bar");
  if (progressBar && mediaData) {
    progressBar.style.width = `${mediaData.progress_percent}%`;
  }
}

/* ============================================================
 * 3. Homepage Hero Banner Carousel
 * ============================================================ */
let heroIndex = 0;
let heroTimer = null;

function initHeroCarousel() {
  const slides = document.querySelectorAll("[data-hero-slide]");
  if (!slides.length) return;

  function showSlide(idx) {
    heroIndex = (idx + slides.length) % slides.length;
    slides.forEach((el, i) => {
      if (i === heroIndex) {
        el.classList.remove("opacity-0", "pointer-events-none", "z-0");
        el.classList.add("opacity-100", "z-10");
      } else {
        el.classList.add("opacity-0", "pointer-events-none", "z-0");
        el.classList.remove("opacity-100", "z-10");
      }
    });
    document.querySelectorAll("[data-hero-dot]").forEach((dot, i) => {
      if (i === heroIndex) {
        dot.classList.add("w-8", "bg-blue-500");
        dot.classList.remove("w-2.5", "bg-white/30");
      } else {
        dot.classList.remove("w-8", "bg-blue-500");
        dot.classList.add("w-2.5", "bg-white/30");
      }
    });
    document.querySelectorAll("[data-hero-thumb]").forEach((thumb, i) => {
      if (i === heroIndex) {
        thumb.classList.add("ring-2", "ring-blue-500", "scale-105", "opacity-100");
        thumb.classList.remove("opacity-60");
      } else {
        thumb.classList.remove("ring-2", "ring-blue-500", "scale-105", "opacity-100");
        thumb.classList.add("opacity-60");
      }
    });
  }

  window.switchHeroSlide = (idx) => {
    showSlide(idx);
    resetHeroTimer();
  };
  window.nextHeroSlide = () => window.switchHeroSlide(heroIndex + 1);
  window.prevHeroSlide = () => window.switchHeroSlide(heroIndex - 1);

  function resetHeroTimer() {
    if (heroTimer) clearInterval(heroTimer);
    if (slides.length > 1) {
      heroTimer = setInterval(() => showSlide(heroIndex + 1), 7500);
    }
  }

  showSlide(0);
  resetHeroTimer();
}

/* ============================================================
 * 4. Modals: Onboarding API Keys Setup & Add Media Wizard
 * ============================================================ */
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.classList.add("flex");
  if (modalId === "add-media-modal") {
    const pathInput = document.getElementById("alist-browser-path");
    if (pathInput && ! document.getElementById("alist-browser-list").children.length) {
      loadAlistDirectory(pathInput.value || "/Quark/来自：分享");
    }
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.add("hidden");
  modal.classList.remove("flex");
}

function collectSettingsForm(prefix = "cfg-") {
  const keys = [
    "ALIST_URL",
    "ALIST_USERNAME",
    "ALIST_PASSWORD",
    "ALIST_SCAN_PATH",
    "TMDB_TOKEN",
    "MDBLIST_APIKEY",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_API",
    "MPC_HC_PATH",
  ];
  const out = {};
  keys.forEach((k) => {
    const el = document.getElementById(`${prefix}${k}`);
    if (el) out[k] = el.value.trim();
  });
  return out;
}

async function saveSettingsForm(prefix = "cfg-", closeAfter = false) {
  const settings = collectSettingsForm(prefix);
  try {
    const resp = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || "保存失败");
    showToast("密钥与配置已成功保存！", "success");
    if (closeAfter) {
      closeModal("keys-wizard-modal");
    }
  } catch (err) {
    showToast(`保存配置失败: ${err.message}`, "error");
  }
}

async function testConnector(target, prefix = "cfg-", statusElementId = null) {
  const settings = collectSettingsForm(prefix);
  const statusEl = statusElementId ? document.getElementById(statusElementId) : null;
  if (statusEl) {
    statusEl.innerHTML = `<span class="text-blue-400 animate-pulse">正在连接测试 (${target})...</span>`;
  }
  try {
    const resp = await fetch("/api/settings/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, settings }),
    });
    const data = await resp.json();
    const res = data.results ? data.results[target] : null;
    if (target === "all") {
      const summary = Object.entries(data.results || {})
        .map(([k, v]) => `${k.toUpperCase()}: ${v.ok ? "✅ 正常" : "❌ " + (v.error || "失败")}`)
        .join(" | ");
      if (statusEl) statusEl.innerHTML = `<span class="text-emerald-300">${summary}</span>`;
      showToast(summary, data.ok ? "success" : "error", 5000);
      return;
    }
    if (res && res.ok) {
      let detail = "连接成功";
      if (target === "alist") detail = `已连接 AList，挂载点: ${(res.root_mounts || []).join(", ")}`;
      if (target === "tmdb") detail = `TMDB 认证通过 (${res.base_url})`;
      if (target === "mdblist") detail = `MDBList 评分服务正常 (${res.ratings_count} 项评分源)`;
      if (target === "llm") detail = `DeepSeek (${res.model}) 识片成功: 虫知-虫朱-亻夹 → ${res.sample_test?.clean_title}`;
      if (target === "player") detail = res.message;
      if (statusEl) statusEl.innerHTML = `<span class="text-emerald-400">✅ ${detail}</span>`;
      showToast(detail, "success");
    } else {
      const errMsg = (res && res.error) || "连接测试未通过";
      if (statusEl) statusEl.innerHTML = `<span class="text-rose-400">❌ ${errMsg}</span>`;
      showToast(`${target.toUpperCase()} 测试失败: ${errMsg}`, "error");
    }
  } catch (err) {
    if (statusEl) statusEl.innerHTML = `<span class="text-rose-400">❌ ${err.message}</span>`;
    showToast(`测试出错: ${err.message}`, "error");
  }
}

/* ============================================================
 * 5. AList Interactive Browser & AI Name De-obfuscation
 * ============================================================ */
async function loadAlistDirectory(path) {
  const listEl = document.getElementById("alist-browser-list");
  const pathInput = document.getElementById("alist-browser-path");
  if (!listEl) return;
  if (pathInput) pathInput.value = path;

  listEl.innerHTML = `<div class="p-6 text-center text-slate-400 text-sm animate-pulse">正在读取 AList 目录: ${path} ...</div>`;
  try {
    const resp = await fetch(`/api/alist/list?path=${encodeURIComponent(path)}`);
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || "无法读取目录");

    const items = data.items || [];
    let html = "";

    if (path !== "/" && path !== "") {
      const parentPath = path.split("/").slice(0, -1).join("/") || "/";
      html += `
        <div onclick="loadAlistDirectory('${parentPath.replace(/'/g, "\\'")}')"
             class="flex items-center justify-between px-3.5 py-2.5 rounded-lg hover:bg-white/5 cursor-pointer border-b border-white/5 text-slate-300 text-sm">
          <div class="flex items-center gap-2.5">
            <span>⬆️</span>
            <span class="font-medium">返回上级目录 (${parentPath})</span>
          </div>
        </div>
      `;
    }

    items.forEach((item) => {
      const safePath = (item.path || "").replace(/'/g, "\\'");
      const safeName = (item.name || "").replace(/'/g, "\\'");
      const icon = item.is_dir ? "📁" : "🎞️";
      html += `
        <div class="flex items-center justify-between gap-2 px-3.5 py-2.5 rounded-lg hover:bg-blue-500/10 border-b border-white/5 text-sm group transition">
          <div class="flex items-center gap-2.5 min-w-0 flex-1 cursor-pointer"
               onclick="${item.is_dir ? `loadAlistDirectory('${safePath}')` : `selectAlistItem('${safePath}', '${safeName}')`}">
            <span class="shrink-0">${icon}</span>
            <span class="truncate text-slate-200 group-hover:text-white" title="${item.name}">${item.name}</span>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button type="button"
                    onclick="selectAlistItem('${safePath}', '${safeName}')"
                    class="px-2.5 py-1 rounded-md bg-blue-600/20 hover:bg-blue-600 text-blue-300 hover:text-white text-xs font-medium transition">
              选定并 AI 识片
            </button>
          </div>
        </div>
      `;
    });

    listEl.innerHTML = html || `<div class="p-6 text-center text-slate-500 text-sm">此目录为空</div>`;
  } catch (err) {
    listEl.innerHTML = `<div class="p-6 text-center text-rose-400 text-sm">读取失败: ${err.message}</div>`;
  }
}

function selectAlistItem(alistPath, rawName) {
  const selectedPathEl = document.getElementById("add-alist-path");
  const rawNameEl = document.getElementById("add-raw-name");
  if (selectedPathEl) selectedPathEl.value = alistPath;
  if (rawNameEl) rawNameEl.value = rawName;
  runAiGuessForAddModal();
}

async function runAiGuessForAddModal() {
  const rawNameEl = document.getElementById("add-raw-name");
  const pathEl = document.getElementById("add-alist-path");
  const resultBox = document.getElementById("ai-guess-result-box");
  const candidatesGrid = document.getElementById("tmdb-candidates-grid");
  if (!rawNameEl) return;

  const rawName = rawNameEl.value.trim() || (pathEl ? pathEl.value.split("/").pop() : "");
  if (!rawName) {
    showToast("请先输入或从左侧选择网盘目录/文件名称", "error");
    return;
  }

  if (resultBox) {
    resultBox.classList.remove("hidden");
    resultBox.innerHTML = `<div class="text-sm text-blue-300 animate-pulse">🤖 DeepSeek AI 正在分析字形变化（拆字/谐音/同形字）并检索 TMDB...</div>`;
  }

  try {
    const resp = await fetch("/api/ai/guess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_name: rawName, force_live: true }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || "AI 识别失败");

    const g = data.guess || {};
    if (resultBox) {
      resultBox.innerHTML = `
        <div class="flex flex-wrap items-center justify-between gap-2 mb-1.5">
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 rounded bg-purple-500/20 border border-purple-500/40 text-purple-300 text-xs font-semibold">${g.obfuscation_type || "AI 识别"}</span>
            <span class="text-white font-bold text-base">《${g.clean_title || rawName}》</span>
            ${g.english_title ? `<span class="text-slate-400 text-xs">(${g.english_title})</span>` : ""}
            ${g.year ? `<span class="text-amber-400 text-xs font-mono">[${g.year}]</span>` : ""}
          </div>
          <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300">${g.media_type === "tv" ? "📺 剧集" : "🎬 电影"}</span>
        </div>
        <p class="text-xs text-slate-300 leading-relaxed">${g.explanation || ""}</p>
      `;
    }

    renderTmdbCandidates(data.tmdb_candidates || [], candidatesGrid);
  } catch (err) {
    if (resultBox) {
      resultBox.innerHTML = `<div class="text-xs text-rose-400">识别出错: ${err.message}</div>`;
    }
  }
}

function renderTmdbCandidates(candidates, containerEl) {
  if (!containerEl) return;
  if (!candidates.length) {
    containerEl.innerHTML = `<div class="col-span-full text-center py-4 text-slate-400 text-xs">未找到 TMDB 候选结果，可直接点击下方“一键导入”使用 AI 推导结果。</div>`;
    return;
  }

  containerEl.innerHTML = candidates
    .map(
      (c, idx) => `
      <div onclick="pickTmdbCandidate(${c.tmdb_id}, '${c.media_type}', '${(c.title || "").replace(/'/g, "\\'")}', this)"
           data-tmdb-card="${c.tmdb_id}"
           class="tmdb-cand-card flex gap-3 p-2.5 rounded-xl border ${idx === 0 ? "border-blue-500 bg-blue-500/10" : "border-white/10 bg-slate-900/70"} hover:border-blue-400 cursor-pointer transition">
        <img src="${c.poster_url || "https://via.placeholder.com/120x180?text=No+Poster"}"
             alt="${c.title}"
             class="w-12 h-18 object-cover rounded-lg shrink-0 bg-slate-800" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5">
            <span class="text-xs px-1.5 py-0.5 rounded ${c.media_type === "tv" ? "bg-indigo-500/20 text-indigo-300" : "bg-amber-500/20 text-amber-300"}">${c.media_type === "tv" ? "剧集" : "电影"}</span>
            <span class="text-sm font-bold text-white truncate">${c.title}</span>
          </div>
          <div class="text-xs text-slate-400 mt-0.5">${c.year || "未知年份"} · ★ ${c.rating || "N/A"} · TMDB #${c.tmdb_id}</div>
          <p class="text-xs text-slate-400 line-clamp-2 mt-1">${c.overview || "暂无简介"}</p>
        </div>
      </div>
    `
    )
    .join("");

  // Auto-select the first candidate
  const first = candidates[0];
  document.getElementById("add-selected-tmdb-id").value = first.tmdb_id;
  document.getElementById("add-selected-media-type").value = first.media_type;
}

function pickTmdbCandidate(tmdbId, mediaType, title, cardEl) {
  document.getElementById("add-selected-tmdb-id").value = tmdbId;
  document.getElementById("add-selected-media-type").value = mediaType;
  document.querySelectorAll(".tmdb-cand-card").forEach((el) => {
    el.classList.remove("border-blue-500", "bg-blue-500/10");
    el.classList.add("border-white/10", "bg-slate-900/70");
  });
  if (cardEl) {
    cardEl.classList.add("border-blue-500", "bg-blue-500/10");
    cardEl.classList.remove("border-white/10", "bg-slate-900/70");
  }
}

async function submitAddMedia() {
  const alistPath = (document.getElementById("add-alist-path")?.value || "").trim();
  const rawName = (document.getElementById("add-raw-name")?.value || "").trim();
  const tmdbId = (document.getElementById("add-selected-tmdb-id")?.value || "").trim();
  const mediaType = (document.getElementById("add-selected-media-type")?.value || "").trim();
  const btn = document.getElementById("btn-submit-add-media");

  if (!alistPath && !tmdbId) {
    showToast("请选择 AList 网盘路径或匹配一个 TMDB 条目", "error");
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = "正在同步海报、剧照与评分...";
  }

  try {
    const resp = await fetch("/api/media/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        alist_path: alistPath,
        title: rawName,
        tmdb_id: tmdbId || null,
        media_type: mediaType || null,
      }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || "添加失败");
    showToast(data.message || "添加成功！", "success");
    closeModal("add-media-modal");
    setTimeout(() => {
      window.location.href = `/media/${data.item.id}`;
    }, 600);
  } catch (err) {
    showToast(`添加失败: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "立即导入至影视库";
    }
  }
}

async function triggerBatchScan(buttonEl) {
  const scanPath = document.getElementById("batch-scan-path")?.value || "/Quark/来自：分享";
  if (buttonEl) {
    buttonEl.disabled = true;
    buttonEl.innerHTML = `<span class="animate-spin inline-block mr-2">⟳</span>正在扫描网盘并拉取 TMDB/MDBList 元数据...`;
  }
  showToast(`开始扫描 AList 目录 ${scanPath}，请稍候...`, "info", 6000);
  try {
    const resp = await fetch("/api/media/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scan_path: scanPath }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || "扫描失败");
    showToast(
      `扫描完成！新增 ${data.added_count} 部，更新 ${data.updated_count} 部影视作品。`,
      "success",
      4000
    );
    setTimeout(() => window.location.reload(), 900);
  } catch (err) {
    showToast(`扫描出错: ${err.message}`, "error");
  } finally {
    if (buttonEl) {
      buttonEl.disabled = false;
      buttonEl.textContent = "🚀 一键智能扫描 AList 网盘";
    }
  }
}

/* ============================================================
 * 6. Standalone AI Lab Tester on Homepage (#ai-showcase)
 * ============================================================ */
async function runStandaloneAiLab() {
  const input = document.getElementById("ai-lab-input");
  const output = document.getElementById("ai-lab-output");
  if (!input || !output) return;
  const val = input.value.trim();
  if (!val) {
    showToast("请输入一个包含谐音、拆字或同形字的网盘名称", "error");
    return;
  }
  output.classList.remove("hidden");
  output.innerHTML = `<div class="text-sm text-purple-300 animate-pulse">🧠 正在调用 DeepSeek (${val}) 进行字形拆解与推理...</div>`;
  try {
    const resp = await fetch("/api/ai/guess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_name: val, force_live: true }),
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || "推理失败");
    const g = data.guess || {};
    const topMatch = (data.tmdb_candidates || [])[0];
    output.innerHTML = `
      <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div class="flex items-center gap-2 flex-wrap">
            <span class="px-2.5 py-0.5 rounded-full bg-purple-500/20 border border-purple-500/40 text-purple-300 text-xs font-semibold">${g.obfuscation_type || "AI 识别"}</span>
            <span class="text-slate-400 text-sm line-through">${val}</span>
            <span class="text-emerald-400 font-bold">➔</span>
            <span class="text-white font-bold text-lg">《${g.clean_title}》</span>
            ${g.english_title ? `<span class="text-slate-400 text-sm">(${g.english_title})</span>` : ""}
          </div>
          <p class="text-xs text-slate-300 mt-1.5">${g.explanation || ""}</p>
        </div>
        ${
          topMatch
            ? `<div class="flex items-center gap-3 bg-slate-900/90 px-3 py-2 rounded-xl border border-white/10 shrink-0">
                 <img src="${topMatch.poster_url || ""}" class="w-10 h-14 object-cover rounded" />
                 <div class="text-xs">
                   <div class="font-bold text-white">TMDB 匹配: ${topMatch.title} (${topMatch.year})</div>
                   <div class="text-amber-400 mt-0.5">★ ${topMatch.rating} · ID #${topMatch.tmdb_id}</div>
                 </div>
               </div>`
            : ""
        }
      </div>
    `;
  } catch (err) {
    output.innerHTML = `<div class="text-xs text-rose-400">识别失败: ${err.message}</div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initHeroCarousel();
});
