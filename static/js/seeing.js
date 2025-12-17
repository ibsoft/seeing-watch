const showToasts = () => {
  const toastEls = document.querySelectorAll(".toast");
  toastEls.forEach((el) => {
    const toast = new bootstrap.Toast(el, { delay: 4000, autohide: true });
    toast.show();
  });
};

document.addEventListener("DOMContentLoaded", () => {
  const tooltipTriggerList = document.querySelectorAll("[data-bs-toggle='tooltip']")
  tooltipTriggerList.forEach((el) => new bootstrap.Tooltip(el))

  const dayButtons = document.querySelectorAll(".day-btn")
  const dayViews = document.querySelectorAll(".day-view")

  const highlightDay = (index) => {
    dayButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.dayIndex === index))
    dayViews.forEach((view) => view.classList.toggle("inactive", view.dataset.dayIndex !== index))
  }

  highlightDay(dayButtons[0]?.dataset.dayIndex || "0")

  dayButtons.forEach((button) => {
    button.addEventListener("click", () => highlightDay(button.dataset.dayIndex))
  })

  const now = Date.now()
  document.querySelectorAll(".hour-card[data-datetime]").forEach((card) => {
    const candidate = Date.parse(card.dataset.datetime)
    if (!Number.isNaN(candidate)) {
      const diff = Math.abs(candidate - now)
      if (diff < 90 * 60 * 1000) {
        card.classList.add("current-hour")
      }
    }
  })

  showToasts()
})

if ('serviceWorker' in navigator) {
  const swUrl = document.body && document.body.dataset && document.body.dataset.swUrl
  if (swUrl) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register(swUrl)
        .catch((err) => console.warn("Service worker registration failed", err))
    })
  }
}
