/* Coffee Bliss — AI assistant widget */
(function () {
  "use strict";

  document.querySelectorAll("[data-assistant]").forEach(function (root) {
    const toggle = root.querySelector("[data-ai-toggle]");
    const close = root.querySelector("[data-ai-close]");
    const panel = root.querySelector("[data-ai-panel]");
    const form = root.querySelector("[data-ai-form]");
    const input = root.querySelector("[data-ai-input]");
    const send = root.querySelector("[data-ai-send]");
    const messages = root.querySelector("[data-ai-messages]");
    const reset = root.querySelector("[data-ai-reset]");
    if (!toggle || !panel || !form || !input || !messages) return;

    const endpoint = root.dataset.endpoint;
    const resetUrl = root.dataset.resetUrl;
    const welcome = root.dataset.welcome || "How can I help?";
    let busy = false;

    function csrfToken() {
      const field = form.querySelector('[name="csrfmiddlewaretoken"]') ||
        document.querySelector('[name="csrfmiddlewaretoken"]');
      return field ? field.value : "";
    }

    function scrollToLatest() {
      messages.scrollTop = messages.scrollHeight;
    }

    function addMessage(text, who) {
      const el = document.createElement("div");
      el.className = "ai-msg ai-msg-" + (who === "user" ? "user" : "bot");
      el.textContent = text;
      messages.appendChild(el);
      scrollToLatest();
      return el;
    }

    function setOpen(open) {
      panel.hidden = !open;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        if (input) setTimeout(function () { input.focus(); }, 30);
        scrollToLatest();
      }
    }

    toggle.addEventListener("click", function () { setOpen(panel.hidden); });
    if (close) close.addEventListener("click", function () { setOpen(false); toggle.focus(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !panel.hidden) { setOpen(false); toggle.focus(); }
    });

    function resize() {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 110) + "px";
    }
    input.addEventListener("input", resize);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true }));
      }
    });

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      const message = input.value.trim();
      if (!message || busy) return;

      busy = true;
      if (send) send.disabled = true;
      input.value = "";
      resize();
      addMessage(message, "user");

      const typing = addMessage("…", "bot");
      typing.classList.add("ai-typing");

      try {
        const response = await fetch(endpoint, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken(),
            "X-Requested-With": "XMLHttpRequest"
          },
          body: JSON.stringify({ message: message })
        });
        let data = {};
        try { data = await response.json(); } catch (err) { data = {}; }
        typing.remove();
        if (!response.ok) {
          addMessage(data.detail || "Sorry, I couldn't answer that just now.", "bot");
          return;
        }
        addMessage(data.reply || "Sorry, I didn't get a reply.", "bot");
      } catch (err) {
        typing.remove();
        addMessage("I can't reach the assistant right now. Please try again.", "bot");
      } finally {
        busy = false;
        if (send) send.disabled = false;
        input.focus();
      }
    });

    if (reset) {
      reset.addEventListener("click", async function () {
        if (busy) return;
        try {
          await fetch(resetUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" }
          });
        } catch (err) {}
        messages.innerHTML = "";
        addMessage(welcome, "bot");
        input.value = "";
        resize();
        input.focus();
      });
    }

    scrollToLatest();
  });
})();
