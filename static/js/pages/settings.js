/* 我的：阿里云盘 token、缓存清理与观看历史清空 */

import { requestJSON } from "../api.js";
import { closeSheet, toast } from "../ui.js";

export function initSettings() {
  document.querySelectorAll("[data-token]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.token;
      const input = document.getElementById("ali-token");
      const token = action === "clear" ? "" : ((input && input.value) || "").trim();
      if (action === "save" && !token) {
        toast("请先填写 refresh token");
        return;
      }
      button.disabled = true;
      try {
        await requestJSON("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ aliyun_token: token }),
        });
        toast(action === "clear" ? "已清除阿里云盘 token" : "token 已保存");
        setTimeout(() => location.reload(), 500);
      } catch (error) {
        toast(error.message);
        button.disabled = false;
      }
    });
  });

  const clearCache = document.getElementById("cache-clear");
  if (clearCache) {
    clearCache.addEventListener("click", async () => {
      clearCache.disabled = true;
      clearCache.textContent = "清理中…";
      try {
        const data = await requestJSON("/api/cache/clear", { method: "POST" });
        toast(`已清理 ${data.files || 0} 个缓存文件`);
        closeSheet(document.getElementById("cache-sheet"));
      } catch (error) {
        toast(error.message);
      } finally {
        clearCache.disabled = false;
        clearCache.textContent = "立即清理";
      }
    });
  }

  const clearHistory = document.getElementById("history-clear-all");
  if (clearHistory) {
    clearHistory.addEventListener("click", async () => {
      const grid = document.getElementById("history-grid");
      const cards = grid ? [...grid.querySelectorAll("a.card")] : [];
      if (!cards.length) return;
      clearHistory.disabled = true;
      try {
        await Promise.all(
          cards.map((card) => {
            const params = new URLSearchParams({
              site: card.dataset.site || "",
              vod_id: card.dataset.vod || "",
            });
            return requestJSON(`/api/history?${params.toString()}`, { method: "DELETE" });
          })
        );
        grid.remove();
        closeSheet(document.getElementById("history-sheet"));
        toast("已清空观看历史");
      } catch (error) {
        toast(error.message);
      } finally {
        clearHistory.disabled = false;
      }
    });
  }
}
