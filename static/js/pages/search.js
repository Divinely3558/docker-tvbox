/* 搜索页：全站并发流式搜索、本地搜索历史 */

import { requestJSON } from "../api.js";
import { foldGroup, makeCard, toast } from "../ui.js";

export function initSearchStream() {
  const box = document.getElementById("search-stream");
  const dataEl = document.getElementById("search-sites");
  if (!box || !dataEl) return;

  let sites = [];
  try {
    sites = JSON.parse(dataEl.textContent || "[]");
  } catch (error) {
    return;
  }
  if (!sites.length) return;

  const wd = box.dataset.wd || "";
  const progress = document.getElementById("search-progress");
  const empty = document.getElementById("search-empty");
  // 全部站点一起并发搜索，结果哪家先返回就先显示，避免慢站拖住首屏。
  const queue = sites.slice();
  const totalSites = sites.length;
  let total = 0;
  let done = 0;

  const updateProgress = () => {
    if (!progress) return;
    if (done < totalSites) {
      progress.textContent = `已搜索 ${done}/${totalSites} 个站点 · 已找到 ${total} 个结果`;
    } else {
      progress.remove();
    }
  };

  const appendGroup = (group) => {
    const items = group.list || [];
    if (!items.length) return;
    total += items.length;
    const section = document.createElement("section");
    section.className = "result-group";
    const head = document.createElement("div");
    head.className = "section-head";
    const title = document.createElement("h2");
    title.className = "section-title";
    title.textContent = group.name || "";
    const count = document.createElement("span");
    count.className = "section-more";
    count.textContent = String(items.length);
    head.append(title, count);
    const grid = document.createElement("div");
    grid.className = "card-grid";
    // 片名命中关键词的排前面，避免无关结果占满首屏那 6 个位置。
    const kw = (wd || "").trim().toLowerCase();
    const ordered = kw
      ? [...items].sort((a, b) => {
          const hit = (item) =>
            (item.vod_name || "").toLowerCase().includes(kw) ? 0 : 1;
          return hit(a) - hit(b);
        })
      : items;
    ordered.forEach((item) => grid.appendChild(makeCard(item, group.site)));
    section.append(head, grid);
    foldGroup(section);
    box.appendChild(section);
  };

  let active = 0;

  const worker = async () => {
    active += 1;
    try {
      while (queue.length) {
        const site = queue.shift();
        try {
          const params = new URLSearchParams({ wd, site: site.key, page: "1" });
          const data = await requestJSON(`/api/search?${params.toString()}`);
          (data.results || []).forEach(appendGroup);
        } catch (error) {
          // 单个站点失败不影响其它站点。
        } finally {
          done += 1;
          updateProgress();
        }
      }
    } finally {
      active -= 1;
      if (!active) finish();
    }
  };

  const finish = () => {
    if (progress) progress.remove();
    if (!total && empty) empty.hidden = false;
  };

  function pump() {
    while (active < 10 && queue.length) worker();
  }

  pump();
}

// ---- 热词与本地搜索历史 ---------------------------------------------
const SEARCH_KEY = "yingmi.search-history";

function readSearchHistory() {
  try {
    const raw = JSON.parse(localStorage.getItem(SEARCH_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((item) => typeof item === "string") : [];
  } catch (error) {
    return [];
  }
}

function writeSearchHistory(words) {
  try {
    localStorage.setItem(SEARCH_KEY, JSON.stringify(words.slice(0, 20)));
  } catch (error) {
    // 隐私模式下写不进去也不影响搜索
  }
}

function goSearch(word) {
  const params = new URLSearchParams();
  if (word) params.set("wd", word);
  const current = new URLSearchParams(location.search).get("site");
  if (current) params.set("site", current);
  location.href = `/search${params.toString() ? `?${params}` : ""}`;
}

function renderSearchHistory() {
  const box = document.getElementById("search-history");
  const section = document.getElementById("search-history-section");
  if (!box || !section) return;
  const words = readSearchHistory();
  section.hidden = !words.length;
  box.replaceChildren();
  words.forEach((word) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip-item";
    chip.textContent = word;
    chip.addEventListener("click", () => goSearch(word));
    box.appendChild(chip);
  });
}

export function initSearch() {
  renderSearchHistory();
  // 单站点搜索是服务端直出，这里统一折叠超过 N 个的结果组。
  document.querySelectorAll(".result-group").forEach(foldGroup);

  document.querySelectorAll("form[action='/search'], form[action=\"/search\"]").forEach((form) => {
    form.addEventListener("submit", () => {
      const input = form.querySelector("input[name=wd]");
      const word = (input && input.value.trim()) || "";
      if (!word) return;
      const words = readSearchHistory().filter((item) => item !== word);
      words.unshift(word);
      writeSearchHistory(words);
    });
  });

  document.querySelectorAll("[data-search-word]").forEach((button) => {
    button.addEventListener("click", () => {
      const word = button.dataset.searchWord || "";
      const input = document.getElementById("search-input");
      if (input) input.value = word;
      const words = readSearchHistory().filter((item) => item !== word);
      words.unshift(word);
      writeSearchHistory(words);
      goSearch(word);
    });
  });

  const clear = document.getElementById("history-clear");
  if (clear) {
    clear.addEventListener("click", () => {
      writeSearchHistory([]);
      renderSearchHistory();
      toast("已清空搜索历史");
    });
  }
}
