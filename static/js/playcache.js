/* 播放地址预解析缓存：详情页提前取地址，播放页直接起播 */

import { requestJSON } from "./api.js";

const PLAY_CACHE_PREFIX = "yingmi.play.";
const PLAY_CACHE_TTL = 120000;

export function playCacheKey(site, flag, id) {
  return `${PLAY_CACHE_PREFIX}${site}|${flag}|${id}`;
}

export function readPlayCache(site, flag, id) {
  if (!site || !flag || !id) return null;
  try {
    const raw = JSON.parse(sessionStorage.getItem(playCacheKey(site, flag, id)) || "null");
    if (!raw || !raw.data || Date.now() - raw.at > PLAY_CACHE_TTL) return null;
    return raw.data;
  } catch (error) {
    return null;
  }
}

export function dropPlayCache(site, flag, id) {
  try {
    sessionStorage.removeItem(playCacheKey(site, flag, id));
  } catch (error) {
    // 隐私模式下没有 sessionStorage
  }
}

// 让服务端缓存列表并预热前几个分片，点击后即取即有。
async function warmHls(url) {
  try {
    const response = await fetch(url, { cache: "no-store", priority: "low" });
    if (!response.ok) return;
    const text = await response.text();
    if (text.indexOf("#EXT-X-STREAM-INF") < 0) return;
    const variants = text
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#"));
    const top = variants[variants.length - 1];
    if (top) fetch(top, { cache: "no-store", priority: "low" }).catch(() => {});
  } catch (error) {
    // 预热失败不影响正常播放
  }
}

export async function prefetchPlayData(site, flag, id) {
  if (!site || !flag || !id || readPlayCache(site, flag, id)) return null;
  const net = navigator.connection || {};
  if (net.saveData || /(^|-)2g$/.test(net.effectiveType || "")) return null;
  try {
    const data = await requestJSON("/api/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ site, flag, id }),
    });
    try {
      sessionStorage.setItem(
        playCacheKey(site, flag, id),
        JSON.stringify({ at: Date.now(), data })
      );
    } catch (error) {
      // 写不进去就退回实时解析
    }
    if (data.hls && data.url) warmHls(data.url);
    return data;
  } catch (error) {
    return null;
  }
}
