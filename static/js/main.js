/* Coffee Bliss — global UI behaviours */
(function () {
  "use strict";

  // Mobile nav toggle
  const toggle = document.querySelector(".nav-toggle");
  const links = document.querySelector(".nav-links");
  if (toggle && links) {
    toggle.addEventListener("click", () => links.classList.toggle("open"));
  }

  // Light / dark theme toggle
  const themeToggle = document.getElementById("theme-toggle");
  const root = document.documentElement;
  const themeIcon = themeToggle ? themeToggle.querySelector(".theme-icon") : null;
  function applyTheme(theme) {
    if (theme === "light") {
      root.setAttribute("data-theme", "light");
    } else {
      root.removeAttribute("data-theme");
    }
    if (themeIcon) themeIcon.textContent = theme === "light" ? "☀️" : "🌙";
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

  // Hero card reacts to pointer
  const heroCard = document.querySelector(".hero-card-3d");
  if (heroCard && window.matchMedia("(pointer:fine)").matches) {
    const hero = heroCard.closest(".hero");
    hero.addEventListener("pointermove", (e) => {
      const r = hero.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      heroCard.style.transform = `rotateY(${-14 + px * 16}deg) rotateX(${8 - py * 14}deg)`;
    });
  }

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
})();
