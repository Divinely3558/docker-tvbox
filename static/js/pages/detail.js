/* 详情页：线路切换、选集、预解析与收藏 */

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
