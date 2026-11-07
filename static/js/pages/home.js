/* 首页 / 分类页：无限滚动加载更多 */

import { requestJSON } from "../api.js";
import { makeCard, toast } from "../ui.js";

export function initInfiniteScroll() {
  const sentinel = document.getElementById("load-sentinel");
  const grid = document.getElementById("result-grid") || document.getElementById("home-grid");
  if (!sentinel || !grid) return;

  let loading = false;
  let done = false;
  const seen = new Set(
    Array.from(grid.querySelectorAll(".card")).map((card) => card.title).filter(Boolean)
  );

  const loadNext = async () => {
    if (loading || done) return;
    loading = true;
    let appended = 0;
    try {
      const page = Number(sentinel.dataset.page || 2);
      const ext = new URLSearchParams(location.search).get("ext") || "";
      const params = new URLSearchParams({
        site: sentinel.dataset.site,
        tid: sentinel.dataset.tid,
        page: String(page),
      });
      if (ext) params.set("ext", ext);
      const data = await requestJSON(`/api/category?${params.toString()}`);
      const items = data.list || [];
      const fresh = items.filter((item) => {
        const name = item.vod_name || "";
        if (!name || seen.has(name)) return false;
        seen.add(name);
        return true;
      });
      if (!fresh.length) {
        // 该页没有新内容（无更多数据，或站点忽略分页返回重复列表）。
        done = true;
        sentinel.remove();
        return;
      }
      fresh.forEach((item) => grid.appendChild(makeCard(item, sentinel.dataset.site)));
      appended = fresh.length;
      sentinel.dataset.page = String(page + 1);
      const total = Number(data.page_count || 0);
      if (total && page >= total) {
        done = true;
        sentinel.remove();
        return;
      }
    } catch (error) {
      toast(error.message);
    } finally {
      loading = false;
    }
    // 自动补满：哨兵仍在视口附近时继续拉下一页，直到铺满或没有更多。
    if (appended && sentinel.isConnected
        && sentinel.getBoundingClientRect().top < window.innerHeight + 600) {
      loadNext();
    }
  };

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadNext();
    }, { rootMargin: "600px 0px" });
    observer.observe(sentinel);
  } else {
    window.addEventListener("scroll", () => {
      if (sentinel.getBoundingClientRect().top < window.innerHeight + 400) loadNext();
    }, { passive: true });
  }
}
