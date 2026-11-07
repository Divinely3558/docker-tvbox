/* 全局 UI 基础设施：toast、弹层、快捷键、海报卡片与地址拼装 */

const body = document.body;
const page = body.dataset.page || "";
const DESKTOP = "(min-width: 900px)";
const toastEl = document.getElementById("toast");
let toastTimer = null;

export function toast(message) {
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.classList.add("is-show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("is-show"), 4000);
}

export const detailUrl = (site, id, name) =>
  `/detail?site=${encodeURIComponent(site || "")}&id=${encodeURIComponent(id || "")}` +
  (name ? `&name=${encodeURIComponent(name)}` : "");

export const playUrl = (options) => {
  const params = new URLSearchParams();
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, value);
  });
  return `/play?${params.toString()}`;
};

// ---- 弹层 -----------------------------------------------------------
function visibleSheets() {
  return [...document.querySelectorAll(".sheet")].filter((el) => !el.hidden);
}

export function openSheet(id) {
  const sheet = document.getElementById(id);
  if (!sheet) return;
  sheet.hidden = false;
  body.classList.add("sheet-open");
  if (window.matchMedia(DESKTOP).matches) {
    const input = sheet.querySelector("input:not([type=hidden])");
    if (input) setTimeout(() => input.focus(), 60);
  }
}

export function closeSheet(sheet) {
  if (sheet) sheet.hidden = true;
  if (!visibleSheets().length) body.classList.remove("sheet-open");
}

const PLANET = `<span class="card-planet" aria-hidden="true">
  <svg viewBox="0 0 64 64">
    <circle cx="32" cy="32" r="14" fill="none" stroke="#dedee2" stroke-width="2.6"/>
    <ellipse cx="32" cy="33" rx="24" ry="7" fill="none" stroke="#dedee2" stroke-width="2.6" transform="rotate(-18 32 33)"/>
    <circle cx="52" cy="17" r="2.2" fill="#e6e6ea"/>
    <circle cx="14" cy="48" r="1.6" fill="#e6e6ea"/>
  </svg>
</span>`;

// ---- 海报卡片（加载更多时复用） -------------------------------------
export function makeCard(item, siteKey) {
  const link = document.createElement("a");
  link.className = "card";
  link.href = detailUrl(siteKey, item.vod_id, item.vod_name);
  link.title = item.vod_name || "";

  const media = document.createElement("div");
  media.className = "card-media";
  media.insertAdjacentHTML("afterbegin", PLANET);

  if (item.vod_pic) {
    const img = document.createElement("img");
    img.src = item.vod_pic;
    img.alt = item.vod_name || "";
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";
    img.addEventListener("error", () => img.remove());
    media.appendChild(img);
  }

  const shade = document.createElement("div");
  shade.className = "card-shade";

  const overlay = document.createElement("div");
  overlay.className = "card-overlay";
  if (item.vod_remarks) {
    const note = document.createElement("span");
    note.className = "card-note";
    note.textContent = item.vod_remarks;
    overlay.appendChild(note);
  }
  const name = document.createElement("span");
  name.className = "card-name";
  name.textContent = item.vod_name || "";
  overlay.appendChild(name);

  media.append(shade, overlay);
  link.appendChild(media);
  return link;
}

// 搜索结果每个站点先展示前 N 个，其余折叠到「更多」里，避免无关结果刷屏。
const GROUP_HEAD = 6;

export function foldGroup(section) {
  const head = section.querySelector(".section-head");
  const grid = section.querySelector(".card-grid");
  if (!head || !grid) return;
  const cards = Array.from(grid.children);
  if (cards.length <= GROUP_HEAD) return;
  const rest = cards.slice(GROUP_HEAD);
  rest.forEach((card) => card.remove());
  let tail = head.querySelector(".section-tail");
  if (!tail) {
    tail = document.createElement("div");
    tail.className = "section-tail";
    const count = head.querySelector(".section-more");
    if (count) {
      count.remove();
      tail.appendChild(count);
    }
    head.appendChild(tail);
  }
  const more = document.createElement("button");
  more.type = "button";
  more.className = "text-action";
  more.textContent = "更多";
  more.addEventListener("click", () => {
    rest.forEach((card) => grid.appendChild(card));
    more.remove();
  });
  tail.appendChild(more);
}

// ---- 全局交互：弹层开关、返回、快捷键、锚点弹层 -----------------------
export function initGlobal() {
  document.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-sheet]");
    if (opener) {
      event.preventDefault();
      openSheet(opener.dataset.sheet);
      return;
    }
    const closer = event.target.closest("[data-close-sheet]");
    if (closer) {
      closeSheet(closer.closest(".sheet"));
      return;
    }
    const back = event.target.closest("[data-back]");
    if (back) {
      event.preventDefault();
      if (history.length > 1) history.back();
      else location.href = "/";
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      visibleSheets().forEach(closeSheet);
    }
    if (event.key === "/" && page !== "play") {
      const input = document.querySelector('input[type="search"]');
      if (input && document.activeElement !== input) {
        event.preventDefault();
        input.focus();
      }
    }
  });

  const hash = location.hash.replace(/^#/, "");
  const initialSheet = !hash
    ? ""
    : hash === "history"
      ? "history-sheet"
      : document.getElementById(hash)?.classList.contains("sheet")
        ? hash
        : "";
  if (initialSheet) {
    const openInitial = () => openSheet(initialSheet);
    document.addEventListener("DOMContentLoaded", openInitial);
    if (document.readyState !== "loading") openInitial();
  }
}
