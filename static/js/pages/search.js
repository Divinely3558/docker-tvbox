/* 搜索页：热词、本地搜索历史与结果折叠 */

import { foldGroup, toast } from "../ui.js";

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
