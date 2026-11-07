/* 数据源管理：订阅源切换/刷新/增删与首页站点切换（base.html 弹层，全页面挂载） */

import { requestJSON } from "./api.js";
import { closeSheet, openSheet, toast } from "./ui.js";

// ---- 添加配置源（先验证密码，再填写地址） -----------------------------
let sourcePassword = "";
let pendingDeleteId = null;

function initAddSource() {
  const authForm = document.getElementById("source-auth-form");
  const addForm = document.getElementById("source-add-form");
  if (!authForm || !addForm) return;
  const authSheet = document.getElementById("source-auth-sheet");
  const authHint = document.getElementById("source-auth-hint");
  const addHint = document.getElementById("source-add-hint");

  const start = document.getElementById("source-add-start");
  if (start) {
    start.addEventListener("click", () => {
      pendingDeleteId = null;
      sourcePassword = "";
      openSheet("source-auth-sheet");
    });
  }

  document.addEventListener("click", (event) => {
    const del = event.target.closest("[data-delete-source]");
    if (!del) return;
    event.preventDefault();
    event.stopPropagation();
    pendingDeleteId = del.dataset.deleteSource;
    openSheet("source-auth-sheet");
  });

  authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = authForm.querySelector('button[type="submit"]');
    const label = button.textContent;
    const password = document.getElementById("source-auth-pass").value;
    button.disabled = true;
    button.textContent = "验证中…";
    if (authHint) authHint.hidden = true;
    try {
      await requestJSON("/api/sources/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      document.getElementById("source-auth-pass").value = "";
      if (pendingDeleteId) {
        // 删除手动添加的源：同一个密码弹窗复用于验证身份。
        await requestJSON(`/api/sources/${pendingDeleteId}/delete`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password }),
        });
        pendingDeleteId = null;
        sourcePassword = "";
        closeSheet(authSheet);
        toast("配置源已删除");
        setTimeout(() => location.reload(), 800);
        return;
      }
      sourcePassword = password;
      closeSheet(authSheet);
      openSheet("source-add-sheet");
    } catch (error) {
      toast(error.message);
      if (authHint) {
        authHint.textContent = error.message;
        authHint.hidden = false;
      }
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  });

  addForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = addForm.querySelector('button[type="submit"]');
    const label = button.textContent;
    const payload = {
      name: document.getElementById("source-add-name").value.trim(),
      url: document.getElementById("source-add-url").value.trim(),
      password: sourcePassword,
    };
    if (!payload.url) {
      toast("请填写配置地址");
      return;
    }
    button.disabled = true;
    button.textContent = "正在验证…";
    if (addHint) addHint.hidden = true;
    try {
      const data = await requestJSON("/api/sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      toast(`已添加「${data.name}」，共 ${data.site_count} 个站点`);
      setTimeout(() => location.reload(), 900);
    } catch (error) {
      toast(error.message);
      if (addHint) {
        addHint.textContent = error.message;
        addHint.hidden = false;
      }
      button.disabled = false;
      button.textContent = label;
      // 密码失效（例如部署密码改了）时退回密码验证步骤。
      if (error.message.includes("密码")) {
        sourcePassword = "";
        closeSheet(document.getElementById("source-add-sheet"));
        openSheet("source-auth-sheet");
      }
    }
  });
}

// 刷新当前配置源（数据源弹层与站点弹层各有一个刷新按钮，行为一致）。
function bindRefresh(button) {
  if (!button) return;
  button.addEventListener("click", async () => {
    button.disabled = true;
    const label = button.textContent;
    button.textContent = "刷新中…";
    try {
      const data = await requestJSON("/api/sources");
      if (!data.active) throw new Error("还没有可用的数据源");
      const result = await requestJSON(`/api/sources/${data.active}/reload`, { method: "POST" });
      toast(`已刷新，共 ${result.site_count} 个站点`);
      setTimeout(() => location.reload(), 600);
    } catch (error) {
      toast(error.message);
      button.disabled = false;
      button.textContent = label;
    }
  });
}

export function initSources() {
  // ---- 订阅数据源切换 -------------------------------------------------
  document.addEventListener("click", async (event) => {
    const cell = event.target.closest("[data-activate]");
    if (!cell) return;
    if (cell.classList.contains("is-on")) {
      closeSheet(cell.closest(".sheet"));
      return;
    }
    cell.disabled = true;
    try {
      await requestJSON(`/api/sources/${cell.dataset.activate}/activate`, { method: "POST" });
      location.reload();
    } catch (error) {
      toast(error.message);
      cell.disabled = false;
    }
  });

  // ---- 首页数据源（当前配置内的站点） ----------------------------------
  document.addEventListener("click", async (event) => {
    const cell = event.target.closest("[data-set-site]");
    if (!cell) return;
    if (cell.classList.contains("is-on")) {
      closeSheet(cell.closest(".sheet"));
      return;
    }
    cell.disabled = true;
    try {
      await requestJSON("/api/home-site", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: cell.dataset.setSite }),
      });
      location.href = "/";
    } catch (error) {
      toast(error.message);
      cell.disabled = false;
    }
  });

  bindRefresh(document.getElementById("source-refresh"));
  bindRefresh(document.getElementById("site-refresh"));
  initAddSource();
}
