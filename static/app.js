/* 影迷 Web 入口：装配全局交互与各页面初始化（各 init 内部按 DOM 自行判断是否生效） */

import { initGlobal } from "./js/ui.js";
import { initSources } from "./js/sources.js";
import { initFilters } from "./js/pages/category.js";
import { initDetail, initSwitchSource } from "./js/pages/detail.js";
import { initInfiniteScroll } from "./js/pages/home.js";
import { initPlay } from "./js/pages/play.js";
import { initSearch, initSearchStream } from "./js/pages/search.js";
import { initSettings } from "./js/pages/settings.js";

initGlobal();
initSources();
initFilters();
initInfiniteScroll();
initSearchStream();
initSwitchSource();
initDetail();
initSearch();
initSettings();
initPlay();
