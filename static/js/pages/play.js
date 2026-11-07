/* 播放页：hls.js 起播与兜底、进度记忆、选集与连播、全屏快捷键 */

import { requestJSON } from "../api.js";
import { playUrl, toast } from "../ui.js";
import {
  dropPlayCache,
  playCacheKey,
  prefetchPlayData,
  readPlayCache,
} from "../playcache.js";

function loadHls() {
  if (window.Hls) return Promise.resolve(window.Hls);
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "/static/vendor/hls.min.js";
    script.onload = () => resolve(window.Hls);
    script.onerror = () => reject(new Error("hls.js 加载失败"));
    document.head.appendChild(script);
  });
}

export function initPlay() {
  const app = document.getElementById("play-app");
  if (!app) return;
  const video = document.getElementById("video");
  const stateEl = document.getElementById("player-state");
  if (!video) return;

  const site = app.dataset.site;
  const flag = app.dataset.flag;
  const episodeId = app.dataset.id;
  const episodeName = app.dataset.name;
  const vodId = app.dataset.vod;
  const title = app.dataset.title;
  const pic = app.dataset.pic;
  const switchLink = document.getElementById("switch-source");
  const showSwitch = () => {
    if (switchLink && title) switchLink.hidden = false;
  };

  let hls = null;
  let lastSaved = 0;

  const setState = (message, withRetry = false) => {
    if (!stateEl) return;
    stateEl.hidden = false;
    stateEl.textContent = message;
    if (withRetry) {
      showSwitch();
      const button = document.createElement("button");
      button.className = "btn btn-dark";
      button.type = "button";
      button.textContent = "重试";
      button.style.marginTop = "12px";
      button.addEventListener("click", () => location.reload());
      stateEl.appendChild(document.createElement("br"));
      stateEl.appendChild(button);
    }
  };
  const clearState = () => {
    if (stateEl) stateEl.hidden = true;
  };

  let fallbackUrl = "";
  let attachSeq = 0;

  function attach(url, nextFallback = "") {
    fallbackUrl = nextFallback;
    const seq = ++attachSeq;
    if (hls) {
      hls.destroy();
      hls = null;
    }
    const isM3u8 = /\.m3u8($|\?)/i.test(url) || url.includes("/hls?") || url.includes("/spider/index.m3u8");
    const playNative = () => {
      if (seq !== attachSeq) return;
      video.preload = "auto";
      video.src = url;
      clearState();
      video.play().catch(() => {});
    };
    if (isM3u8) {
      // 优先 hls.js：Chrome 对 HLS MIME 会返回 "maybe" 却不一定真能播，
      // 交给 MSE 才能控制缓冲与码率，原生只在 MSE 不可用时兜底。
      loadHls()
        .then((Hls) => {
          if (seq !== attachSeq) return;
          if (!Hls.isSupported()) {
            playNative();
            return;
          }
          let recoveries = 0;
          hls = new Hls({
            enableWorker: true,
            lowLatencyMode: false,
            backBufferLength: 30,
            maxBufferLength: 60,
            maxMaxBufferLength: 120,
            maxBufferSize: 100 * 1024 * 1024,
            // 内网带宽充足：初始就按高带宽选最高档，MANIFEST_PARSED 后再锁定。
            abrEwmaDefaultEstimate: 100 * 1000 * 1000,
            startLevel: -1,
            manifestLoadingMaxRetry: 2,
            levelLoadingMaxRetry: 4,
            fragLoadingMaxRetry: 6,
          });
          hls.on(Hls.Events.MEDIA_ATTACHED, () => hls.loadSource(url));
          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            if (hls.levels && hls.levels.length) {
              const top = hls.levels.length - 1;
              hls.currentLevel = top;
              hls.nextLevel = top;
            }
          });
          hls.on(Hls.Events.ERROR, (_, data) => {
            if (!data.fatal) return;
            if (fallbackUrl) {
              const next = fallbackUrl;
              attach(next, "");
              return;
            }
            if (recoveries < 2 && data.type === Hls.ErrorTypes.NETWORK_ERROR) {
              recoveries += 1;
              hls.startLoad();
              return;
            }
            if (recoveries < 2 && data.type === Hls.ErrorTypes.MEDIA_ERROR) {
              recoveries += 1;
              hls.recoverMediaError();
              return;
            }
            if (playDataFromCache && retryFresh()) return;
            setState("播放失败：媒体流不可用或已失效", true);
            showSwitch();
            hls.destroy();
            hls = null;
          });
          hls.attachMedia(video);
          clearState();
          // 浏览器可能拦截有声自动播放，失败时保留原生控件让用户手动开始。
          video.play().catch(() => {});
        })
        .catch(() => {
          if (video.canPlayType("application/vnd.apple.mpegurl")) {
            playNative();
            return;
          }
          setState("HLS 播放组件加载失败，请刷新重试", true);
        });
    } else {
      playNative();
    }
  }

  const retryViaProxy = () => {
    if (!fallbackUrl) return false;
    const next = fallbackUrl;
    attach(next, "");
    return true;
  };

  function saveHistory(force = false) {
    if (!vodId) return;
    const now = Date.now();
    if (!force && now - lastSaved < 10000) return;
    lastSaved = now;
    const payload = {
      site,
      vod_id: vodId,
      name: title,
      pic,
      flag,
      episode: episodeName,
      position: video.currentTime || 0,
      duration: video.duration || 0,
      device: window.matchMedia("(max-width: 767px)").matches ? "mobile" : "web",
    };
    requestJSON("/api/history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(() => {});
  }

  async function restorePosition() {
    if (!vodId) return;
    try {
      const data = await requestJSON("/api/history");
      const item = (data.items || []).find(
        (row) => row.vod_id === vodId && row.flag === flag && row.episode === episodeName
      );
      if (item && item.position > 5) {
        video.currentTime = item.position;
        toast(`已跳到上次观看位置 ${Math.floor(item.position / 60)}:${String(Math.floor(item.position % 60)).padStart(2, "0")}`);
      }
    } catch (error) {
      // 忽略
    }
  }

  let nextTimer = null;
  let episodes = [];
  let currentIndex = -1;

  const nextButton = document.getElementById("next-episode");
  const nextOverlay = document.getElementById("next-overlay");
  const nextText = document.getElementById("next-text");
  const nextHost = document.getElementById("play-episode-grid");
  const episodesBox = document.getElementById("play-episodes");

  const episodeUrl = (episode) =>
    playUrl({
      site,
      flag,
      id: episode.url,
      name: episode.name,
      vod: vodId,
      title,
      pic,
    });

  function clearNext() {
    if (nextTimer) {
      clearInterval(nextTimer);
      nextTimer = null;
    }
    if (nextOverlay) nextOverlay.hidden = true;
  }

  function goNext() {
    if (currentIndex < 0 || currentIndex + 1 >= episodes.length) return;
    location.href = episodeUrl(episodes[currentIndex + 1]);
  }

  function scheduleNext() {
    if (currentIndex < 0 || currentIndex + 1 >= episodes.length) return;
    prefetchNext();
    const next = episodes[currentIndex + 1];
    let remain = 5;
    clearNext();
    if (nextOverlay) nextOverlay.hidden = false;
    const paint = () => {
      if (nextText) nextText.textContent = `${remain} 秒后播放：${next.name}`;
    };
    paint();
    nextTimer = setInterval(() => {
      remain -= 1;
      if (remain <= 0) {
        clearNext();
        goNext();
        return;
      }
      paint();
    }, 1000);
  }

  function renderEpisodes() {
    if (!nextHost || !episodes.length) return;
    nextHost.replaceChildren();
    episodes.forEach((episode, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "episode" + (index === currentIndex ? " is-playing" : "");
      button.textContent = episode.name;
      button.addEventListener("click", () => {
        location.href = episodeUrl(episode);
      });
      nextHost.appendChild(button);
    });
    if (episodesBox) episodesBox.hidden = false;
    const active = nextHost.children[currentIndex];
    if (active) active.scrollIntoView({ block: "nearest", inline: "center" });
  }

  async function loadEpisodes() {
    if (!vodId) return;
    try {
      const data = await requestJSON(
        `/api/detail?site=${encodeURIComponent(site)}&id=${encodeURIComponent(vodId)}`
      );
      const lines = (data.vod && data.vod.play_lines) || [];
      const line =
        lines.find((item) => item.flag === flag) ||
        lines.find((item) => item.episodes.some((ep) => ep.url === episodeId)) ||
        lines[0];
      if (!line) return;
      episodes = line.episodes;
      const found = episodes.findIndex(
        (ep) => ep.url === episodeId || ep.name === episodeName
      );
      currentIndex = found < 0 ? 0 : found;
      renderEpisodes();
      if (nextButton) nextButton.hidden = currentIndex + 1 >= episodes.length;
    } catch (error) {
      // 选集加载失败不影响当前播放
    }
  }

  if (nextButton) nextButton.addEventListener("click", goNext);
  const nextNow = document.getElementById("next-now");
  if (nextNow) {
    nextNow.addEventListener("click", () => {
      clearNext();
      goNext();
    });
  }
  const nextCancel = document.getElementById("next-cancel");
  if (nextCancel) nextCancel.addEventListener("click", clearNext);

  let playDataFromCache = false;
  let playRetried = false;
  let prefetchedNext = "";

  // 临近片尾再解析下一集，太早取到的地址可能已过期。
  function prefetchNext() {
    if (currentIndex < 0 || currentIndex + 1 >= episodes.length) return;
    const next = episodes[currentIndex + 1];
    const key = playCacheKey(site, flag, next.url);
    if (prefetchedNext === key) return;
    prefetchedNext = key;
    prefetchPlayData(site, flag, next.url).catch(() => {});
  }

  function applyPlayData(data) {
    if (data.kind === "parse") {
      setState("该地址需要网页解析插件，当前版本暂不支持。可在详情页切换其它线路。");
      showSwitch();
      return;
    }
    const proxied = data.url || data.stream;
    const url = data.direct || proxied;
    if (!url) {
      setState("没有拿到播放地址，请换一个线路。");
      showSwitch();
      return;
    }
    attach(url, data.direct ? proxied : "");
    video.addEventListener("loadedmetadata", restorePosition, { once: true });
  }

  async function fetchPlayData() {
    const cached = readPlayCache(site, flag, episodeId);
    if (cached) {
      dropPlayCache(site, flag, episodeId);
      playDataFromCache = true;
      applyPlayData(cached);
      return;
    }
    const data = await requestJSON("/api/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ site, flag, id: episodeId }),
    });
    applyPlayData(data);
  }

  // 预解析的地址可能带时效签名，播放失败时丢掉缓存重新取一次。
  function retryFresh() {
    if (playRetried) return false;
    playRetried = true;
    playDataFromCache = false;
    dropPlayCache(site, flag, episodeId);
    fetchPlayData().catch((error) =>
      setState(`获取播放地址失败：${error.message}`, true)
    );
    return true;
  }

  fetchPlayData().catch((error) =>
    setState(`获取播放地址失败：${error.message}`, true)
  );

  loadEpisodes();

  video.addEventListener("timeupdate", () => {
    saveHistory();
    if (video.duration && video.duration - video.currentTime < 90) prefetchNext();
  });
  video.addEventListener("pause", () => saveHistory(true));
  video.addEventListener("ended", () => {
    saveHistory(true);
    scheduleNext();
  });
  window.addEventListener("pagehide", () => saveHistory(true));
  video.addEventListener("error", () => {
    if (retryViaProxy()) return;
    if (playDataFromCache && retryFresh()) return;
    if (video.src) setState("播放失败：视频源不可用，试试其它线路。", true);
  });

  function toggleFullscreen() {
    const target = document.querySelector(".player-stage") || video;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else if (target.requestFullscreen) {
      target.requestFullscreen().catch(() => {});
    }
  }

  const fullscreen = document.getElementById("fullscreen");
  if (fullscreen) fullscreen.addEventListener("click", toggleFullscreen);

  document.addEventListener("keydown", (event) => {
    if (event.target.matches("input, textarea, select")) return;
    if (event.key === " " || event.code === "Space") {
      event.preventDefault();
      if (video.paused) video.play().catch(() => {});
      else video.pause();
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const delta = event.key === "ArrowLeft" ? -10 : 10;
      video.currentTime = Math.max(0, video.currentTime + delta);
    } else if (event.key.toLowerCase() === "f") {
      toggleFullscreen();
    }
  });
}
