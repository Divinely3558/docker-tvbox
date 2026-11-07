/* 详情页：线路切换、选集、预解析、收藏与换源弹层 */

import { requestJSON } from "../api.js";
import { playUrl, toast } from "../ui.js";
import { prefetchPlayData } from "../playcache.js";

export function initDetail() {
  const tabs = document.querySelectorAll(".line-tab");
  const groups = document.querySelectorAll(".episode-grid[data-line]");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((item) => item.classList.toggle("is-active", item === tab));
      groups.forEach((group) => {
        group.hidden = group.dataset.line !== tab.dataset.line;
      });
    });
  });

  const gotoPlay = (source) => {
    const group = source.closest(".episode-grid");
    if (!group) return;
    location.href = playUrl({
      site: group.dataset.site,
      flag: group.dataset.flag,
      id: source.dataset.url,
      name: source.dataset.name,
      vod: group.dataset.vod,
      title: group.dataset.title,
      pic: group.dataset.pic,
    });
  };

  document.querySelectorAll(".episode").forEach((episode) => {
    if (!episode.closest("#play-episode-grid")) {
      episode.addEventListener("click", () => gotoPlay(episode));
    }
  });

  const playButtonUrl = (button) =>
    playUrl({
      site: button.dataset.site,
      flag: button.dataset.flag,
      id: button.dataset.url,
      name: button.dataset.name,
      vod: button.dataset.vod,
      title: button.dataset.title,
      pic: button.dataset.pic,
    });

  document.querySelectorAll("#play-first, #play-resume").forEach((button) => {
    button.addEventListener("click", () => {
      location.href = playButtonUrl(button);
    });
  });

  // 空闲时预解析首集；悬停/按下某集时也顺手解析，命中后播放页直接起播。
  let warming = false;
  const warm = (button) => {
    if (warming || !button) return;
    const { site, flag, url } = button.dataset;
    if (!site || !flag || !url) return;
    warming = true;
    prefetchPlayData(site, flag, url).finally(() => {
      warming = false;
    });
  };
  const firstPlay = document.getElementById("play-first") || document.getElementById("play-resume");
  if (firstPlay) {
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(() => warm(firstPlay), { timeout: 1800 });
    } else {
      setTimeout(() => warm(firstPlay), 900);
    }
    firstPlay.addEventListener("pointerdown", () => warm(firstPlay), { passive: true, once: true });
  }
  document.querySelectorAll(".episode").forEach((episode) => {
    if (episode.closest("#play-episode-grid")) return;
    episode.addEventListener("pointerenter", () => warm(episode), { passive: true });
    episode.addEventListener("pointerdown", () => warm(episode), { passive: true, once: true });
  });

  const fav = document.getElementById("fav-btn");
  if (!fav) return;
  fav.addEventListener("click", async () => {
    const on = fav.dataset.on === "true";
    const payload = {
      site: fav.dataset.site,
      vod_id: fav.dataset.id,
      name: fav.dataset.name,
      pic: fav.dataset.pic,
    };
    fav.disabled = true;
    try {
      if (on) {
        const params = new URLSearchParams({ site: payload.site, vod_id: payload.vod_id });
        await requestJSON(`/api/favorites?${params.toString()}`, { method: "DELETE" });
      } else {
        await requestJSON("/api/favorites", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      fav.dataset.on = on ? "false" : "true";
      fav.classList.toggle("is-on", !on);
      const label = fav.querySelector("span");
      if (label) label.textContent = on ? "收藏" : "已收藏";
      const star = fav.querySelector("svg");
      if (star) star.outerHTML = on
        ? '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.6 14.6 9l5.9.8-4.3 4.1 1 5.9L12 17l-5.2 2.8 1-5.9-4.3-4.1 5.9-.8z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>'
        : '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.6 14.6 9l5.9.8-4.3 4.1 1 5.9L12 17l-5.2 2.8 1-5.9-4.3-4.1 5.9-.8z" fill="currentColor"/></svg>';
      toast(on ? "已取消收藏" : "已加入收藏");
    } catch (error) {
      toast(error.message);
    } finally {
      fav.disabled = false;
    }
  });
}

// ---- 换源弹层（详情页与播放页共用） -----------------------------------
export function initSwitchSource() {
  const button = document.getElementById("switch-source");
  const sheet = document.getElementById("switch-sheet");
  const list = document.getElementById("switch-list");
  const progress = document.getElementById("switch-progress");
  const dataEl = document.getElementById("switch-sites");
  if (!button || !sheet || !list || !progress || !dataEl) return;

  let sites = [];
  try {
    sites = JSON.parse(dataEl.textContent || "[]");
  } catch (error) {
    return;
  }
  if (!sites.length) return;

  const title = button.dataset.title || "";
  const filters = document.getElementById("switch-filters");
  const seen = new Set();
  const chips = new Map();
  let activeFilter = "";
  let started = false;
  let rows = 0;
  let done = 0;

  if (filters) {
    filters.addEventListener("click", (event) => {
      const chip = event.target.closest(".filter-chip");
      if (!chip) return;
      filters.querySelectorAll(".filter-chip").forEach((el) => {
        el.classList.toggle("is-active", el === chip);
      });
      activeFilter = chip.dataset.siteFilter || "";
      list.querySelectorAll(".switch-row").forEach((row) => {
        row.hidden = Boolean(activeFilter) && row.dataset.site !== activeFilter;
      });
    });
  }

  const ensureChip = (key, label) => {
    if (!filters || chips.has(key)) return;
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "filter-chip";
    chip.dataset.siteFilter = key;
    chip.textContent = label || key;
    filters.appendChild(chip);
    chips.set(key, chip);
  };

  const updateProgress = () => {
    if (done < dispatched) {
      progress.textContent = `已搜索 ${done}/${dispatched} 个站点 · 已找到 ${rows} 个`;
    } else if (rest.length) {
      progress.textContent = `已搜索 ${dispatched} 个站点 · 已找到 ${rows} 个`;
    } else {
      progress.textContent = rows ? `找到 ${rows} 个可用源` : "没有找到其他可用源";
    }
  };

  const appendRow = (group, item, siteName) => {
    const dedupeKey = `${group.site}:${item.vod_id}`;
    if (seen.has(dedupeKey)) return;
    seen.add(dedupeKey);
    rows += 1;
    ensureChip(group.site, siteName || group.name);
    const params = new URLSearchParams({
      site: group.site,
      id: String(item.vod_id || ""),
      name: title,
    });
    const row = document.createElement("a");
    row.className = "switch-row";
    row.dataset.site = group.site;
    row.hidden = Boolean(activeFilter) && group.site !== activeFilter;
    row.href = `/detail?${params.toString()}`;

    const thumb = document.createElement("div");
    thumb.className = "switch-thumb";
    if (item.vod_pic) {
      const img = document.createElement("img");
      img.src = item.vod_pic;
      img.alt = item.vod_name || "";
      img.loading = "lazy";
      img.referrerPolicy = "no-referrer";
      img.onerror = () => img.remove();
      thumb.appendChild(img);
    }

    const body = document.createElement("div");
    body.className = "switch-body";
    const name = document.createElement("span");
    name.className = "switch-name";
    name.textContent = item.vod_name || title;
    body.appendChild(name);
    if (item.vod_remarks) {
      const remark = document.createElement("span");
      remark.className = "switch-remark";
      remark.textContent = item.vod_remarks;
      body.appendChild(remark);
    }

    const siteEl = document.createElement("span");
    siteEl.className = "switch-site";
    siteEl.textContent = siteName || group.name || "";

    row.append(thumb, body, siteEl);
    list.appendChild(row);
  };

  const moreWrap = document.getElementById("switch-more-wrap");
  const queue = sites.slice(0, 5);
  const rest = sites.slice(5);
  let dispatched = 0;
  let active = 0;
  let moreButton = null;

  const showMore = () => {
    if (!rest.length || !moreWrap || moreButton) return;
    moreButton = document.createElement("button");
    moreButton.type = "button";
    moreButton.className = "btn btn-soft btn-block";
    moreButton.textContent = `显示全部站点（还有 ${rest.length} 个）`;
    moreButton.addEventListener("click", () => {
      queue.push(...rest.splice(0, rest.length));
      moreButton.remove();
      moreButton = null;
      updateProgress();
      pump();
    });
    moreWrap.appendChild(moreButton);
  };

  const worker = async () => {
    active += 1;
    try {
      while (queue.length) {
        const site = queue.shift();
        dispatched += 1;
        updateProgress();
        try {
          const params = new URLSearchParams({ wd: title, site: site.key, page: "1" });
          const data = await requestJSON(`/api/search?${params.toString()}`);
          (data.results || []).forEach((group) => {
            (group.list || []).forEach((item) => appendRow(group, item, site.name));
          });
        } catch (error) {
          // 单个站点失败不影响其它站点
        } finally {
          done += 1;
          updateProgress();
        }
      }
    } finally {
      active -= 1;
      if (!active) {
        if (rest.length) showMore();
        updateProgress();
      }
    }
  };

  function pump() {
    while (active < 6 && queue.length) worker();
  }

  const start = () => {
    if (started) return;
    started = true;
    showMore();
    pump();
  };

  button.addEventListener("click", () => {
    sheet.hidden = false;
    start();
  });
  sheet.querySelectorAll("[data-close-sheet]").forEach((el) => {
    el.addEventListener("click", () => {
      sheet.hidden = true;
    });
  });
}
