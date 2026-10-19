/* Coffee Bliss — global UI behaviours */
(function () {
  "use strict";

  // Mobile nav toggle
  const toggle = document.querySelector(".nav-toggle");
  const links = document.querySelector(".nav-links");
  function setNav(open) {
    if (!links || !toggle) return;
    links.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  }
  if (toggle && links) {
    toggle.addEventListener("click", (e) => {
      e.stopPropagation();
      setNav(!links.classList.contains("open"));
    });
    links.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => setNav(false)));
    document.addEventListener("click", (e) => {
      if (links.classList.contains("open") && !links.contains(e.target) && !toggle.contains(e.target)) {
        setNav(false);
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setNav(false);
    });
  }

  // Navbar: compact + shadow once scrolled
  const navbar = document.querySelector("[data-navbar]");
  if (navbar) {
    const onScroll = () => navbar.classList.toggle("scrolled", window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // Nav search overlay
  const searchToggle = document.getElementById("search-toggle");
  const searchForm = document.getElementById("nav-search");
  if (searchToggle && searchForm) {
    const input = searchForm.querySelector(".nav-search-input");
    const close = () => {
      navbar && navbar.classList.remove("searching");
      searchToggle.setAttribute("aria-expanded", "false");
    };
    searchToggle.addEventListener("click", () => {
      if (navbar) navbar.classList.add("searching");
      searchToggle.setAttribute("aria-expanded", "true");
      if (input) setTimeout(() => input.focus(), 30);
    });
    searchForm.querySelector("[data-search-close]")?.addEventListener("click", close);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });
  }

  // Light / dark theme toggle
  const themeToggle = document.getElementById("theme-toggle");
  const root = document.documentElement;
  function applyTheme(theme) {
    if (theme === "light") {
      root.setAttribute("data-theme", "light");
    } else {
      root.removeAttribute("data-theme");
    }
    if (themeToggle) themeToggle.setAttribute("aria-pressed", theme === "light" ? "true" : "false");
    document.dispatchEvent(new CustomEvent("themechange", { detail: { theme } }));
  }
  const stored = (() => {
    try { return localStorage.getItem("coffee-bliss-theme"); } catch (e) { return null; }
  })();
  const initial = stored === "light" || stored === "dark" ? stored : "dark";
  applyTheme(initial);
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
      try { localStorage.setItem("coffee-bliss-theme", next); } catch (e) {}
      applyTheme(next);
    });
  }

  // Auto-dismiss flash messages
  document.querySelectorAll(".message").forEach((el) => {
    setTimeout(() => {
      el.style.transition = "opacity .4s ease, transform .4s ease";
      el.style.opacity = "0";
      el.style.transform = "translateX(30px)";
      setTimeout(() => el.remove(), 400);
    }, 5000);
  });

  // Reveal-on-scroll
  const io = "IntersectionObserver" in window
    ? new IntersectionObserver(
        (entries) => {
          entries.forEach((e) => {
            if (e.isIntersecting) {
              e.target.classList.add("in");
              io.unobserve(e.target);
            }
          });
        },
        { threshold: 0.12 }
      )
    : null;
  document.querySelectorAll(".reveal").forEach((el) => (io ? io.observe(el) : el.classList.add("in")));

  // 3D tilt on cards
  document.querySelectorAll("[data-tilt]").forEach((card) => {
    card.addEventListener("pointermove", (e) => {
      const r = card.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform = `perspective(900px) rotateY(${px * 10}deg) rotateX(${-py * 10}deg) translateY(-6px)`;
    });
    card.addEventListener("pointerleave", () => {
      card.style.transform = "";
    });
  });

  // Newsletter / inline forms: basic client validation
  document.querySelectorAll("form[data-validate]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      const email = form.querySelector('input[type="email"]');
      if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
        e.preventDefault();
        email.focus();
        email.style.borderColor = "var(--danger)";
      }
    });
  });

  // Quantity steppers
  document.querySelectorAll("[data-qty]").forEach((wrap) => {
    const input = wrap.querySelector("input");
    wrap.querySelectorAll("[data-qty-step]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const step = parseInt(btn.dataset.qtyStep, 10);
        const min = parseInt(input.min || "1", 10);
        input.value = Math.max(min, (parseInt(input.value, 10) || 1) + step);
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
  });

  // Auto-submit filter selects
  document.querySelectorAll("[data-autosubmit]").forEach((el) => {
    el.addEventListener("change", () => el.form && el.form.submit());
  });

  // ---- Auth helpers ------------------------------------------------------

  // Reveal / hide password
  document.querySelectorAll("[data-pw-toggle]").forEach((btn) => {
    const wrap = btn.closest(".input-wrap");
    const input = wrap && wrap.querySelector("input");
    if (!input) return;
    btn.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.classList.toggle("revealed", show);
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      input.focus();
    });
  });

  // Caps Lock warning
  document.querySelectorAll("input[data-caps-hint]").forEach((input) => {
    const hint = document.getElementById(input.dataset.capsHint);
    if (!hint) return;
    const update = (e) => {
      if (!e.getModifierState) return;
      hint.classList.toggle("on", e.getModifierState("CapsLock"));
    };
    input.addEventListener("keydown", update);
    input.addEventListener("keyup", update);
    input.addEventListener("blur", () => hint.classList.remove("on"));
  });

  // Demo account quick-fill
  document.querySelectorAll("[data-demo-fill]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const form = btn.closest("form");
      if (!form) return;
      const email = form.querySelector('input[type="email"], input[name="username"]');
      const pw = form.querySelector('input[type="password"]');
      if (email) {
        email.value = btn.dataset.email || "";
        email.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (pw) {
        pw.value = btn.dataset.password || "";
        pw.dispatchEvent(new Event("input", { bubbles: true }));
        pw.focus();
      }
    });
  });

  // Password strength meter + live rule checklist
  function scorePassword(value) {
    const rules = {
      length: value.length >= 8,
      case: /[a-z]/.test(value) && /[A-Z]/.test(value),
      number: /\d/.test(value),
      symbol: /[^A-Za-z0-9]/.test(value),
    };
    return { rules, score: Object.values(rules).filter(Boolean).length };
  }
  document.querySelectorAll("[data-pw-meter]").forEach((meter) => {
    const input = document.getElementById(meter.dataset.input);
    if (!input) return;
    const bar = meter.querySelector(".bar");
    const label = document.querySelector('[data-pw-label="' + meter.dataset.input + '"]');
    const rulesEl = document.querySelector('[data-pw-rules="' + meter.dataset.input + '"]');
    const words = ["", "Weak", "Fair", "Good", "Strong"];
    input.addEventListener("input", () => {
      if (!input.value) {
        meter.dataset.score = "0";
        if (bar) bar.style.width = "0";
        if (label) label.textContent = "";
        rulesEl && rulesEl.querySelectorAll("li").forEach((li) => li.classList.remove("ok"));
        return;
      }
      const { rules, score } = scorePassword(input.value);
      meter.dataset.score = String(score);
      if (bar) bar.style.width = (score / 4) * 100 + "%";
      if (label) label.textContent = words[score] ? "Strength: " + words[score] : "";
      if (rulesEl) {
        rulesEl.querySelectorAll("li").forEach((li) => {
          li.classList.toggle("ok", !!rules[li.dataset.rule]);
        });
      }
    });
  });

  // Live inline field validation (email + password match)
  function setFieldState(input, msgEl, ok, text) {
    input.classList.toggle("valid", ok === true);
    input.classList.toggle("invalid", ok === false);
    if (msgEl) {
      msgEl.textContent = text || "";
      msgEl.classList.toggle("on", !!text);
      msgEl.classList.toggle("ok", ok === true);
      msgEl.classList.toggle("error", ok === false);
    }
  }
  document.querySelectorAll("[data-live-validate]").forEach((input) => {
    const field = input.closest(".field") || input.parentElement;
    const msgEl = field && field.querySelector("[data-msg-for]");
    const rule = input.dataset.liveValidate;
    const run = () => {
      const value = input.value.trim();
      if (!value) return setFieldState(input, msgEl, null, "");
      if (rule === "email") {
        const ok = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
        setFieldState(input, msgEl, ok, ok ? "Looks good" : "Enter a valid email address");
      } else if (rule === "match") {
        const other = document.getElementById(input.dataset.matchWith || "");
        const ok = other && value === other.value;
        setFieldState(input, msgEl, ok, ok ? "Passwords match" : "Passwords don't match");
      } else if (rule === "min") {
        const ok = value.length >= (parseInt(input.dataset.minLength || "1", 10));
        setFieldState(input, msgEl, ok, ok ? "Looks good" : "Too short");
      }
    };
    input.addEventListener("input", run);
    if (input.dataset.matchWith) {
      const other = document.getElementById(input.dataset.matchWith);
      other && other.addEventListener("input", () => input.value && run());
    }
  });

  // Prevent double-submit + show loading state
  document.querySelectorAll("form[data-lock-submit]").forEach((form) => {
    form.addEventListener("submit", () => {
      const btn = form.querySelector('button[type="submit"], button:not([type])');
      if (btn) {
        btn.classList.add("is-loading");
        btn.disabled = true;
        setTimeout(() => { btn.disabled = false; btn.classList.remove("is-loading"); }, 8000);
      }
    });
  });
})();
