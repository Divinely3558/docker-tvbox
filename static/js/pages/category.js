/* 分类页：筛选条件 */

export function initFilters() {
  document.querySelectorAll(".filter-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const group = chip.closest(".filter-group");
      if (!group) return;
      group.querySelectorAll(".filter-chip").forEach((item) => {
        item.classList.toggle("is-active", item === chip);
      });
    });
  });

  const apply = document.getElementById("filter-apply");
  if (!apply) return;
  apply.addEventListener("click", () => {
    const sheet = document.getElementById("filter-sheet");
    if (!sheet) return;
    const extend = {};
    sheet.querySelectorAll(".filter-chip.is-active").forEach((chip) => {
      if (chip.dataset.value) extend[chip.dataset.key] = chip.dataset.value;
    });
    const params = new URLSearchParams({ site: sheet.dataset.site, tid: sheet.dataset.tid });
    if (Object.keys(extend).length) params.set("ext", JSON.stringify(extend));
    location.href = `/category?${params.toString()}`;
  });
}
