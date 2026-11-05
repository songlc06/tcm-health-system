/* 轻量交互脚本：提示自动消失、危险操作确认、表格行跳转 */
document.addEventListener("DOMContentLoaded", function () {
  // 提示条 6 秒后自动收起
  document.querySelectorAll(".flash").forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity .4s, transform .4s";
      el.style.opacity = "0";
      el.style.transform = "translateY(-6px)";
      setTimeout(function () { el.remove(); }, 420);
    }, 6000);
  });

  // 危险操作二次确认
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      if (!window.confirm(el.getAttribute("data-confirm"))) {
        e.preventDefault();
      }
    });
  });

  // 可点击行跳转（表格行加 data-href）
  document.querySelectorAll("tr[data-href]").forEach(function (row) {
    row.style.cursor = "pointer";
    row.addEventListener("click", function (e) {
      if (e.target.closest("a, button, input, label, select")) return;
      window.location = row.getAttribute("data-href");
    });
  });

  // 打印
  document.querySelectorAll("[data-print]").forEach(function (btn) {
    btn.addEventListener("click", function () { window.print(); });
  });
});
