// Admin dashboard: navigation + overview analytics + orders + menu CRUD.
(function () {
  const rupees = (p) => "₹" + (p / 100).toFixed(2).replace(/\.00$/, "");
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  // ---------------------------------------------------------------- nav
  const ACTIVE = ["bg-emerald-500/15", "text-emerald-400"];
  function show(section) {
    $$("[data-section]").forEach((el) =>
      el.classList.toggle("hidden", el.dataset.section !== section)
    );
    $$(".nav-btn").forEach((b) => {
      const on = b.dataset.nav === section;
      b.classList.toggle("bg-emerald-500/15", on && b.closest("aside"));
      b.classList.toggle("text-emerald-400", on);
      b.classList.toggle("text-slate-400", !on);
    });
    if (section === "overview") loadOverview();
    if (section === "orders") loadOrders();
    if (section === "menu") loadMenu();
    location.hash = section;
  }
  $$(".nav-btn").forEach((b) => b.addEventListener("click", () => show(b.dataset.nav)));

  async function getJSON(url) {
    const res = await fetch(url);
    if (res.status === 401) return (window.location.href = "/login?next=/admin"), null;
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    return res.json();
  }

  // ---------------------------------------------------------------- overview
  let chart = null;
  async function loadOverview() {
    const a = await getJSON("/api/admin/analytics");
    if (!a) return;
    $("#a-rev-today").textContent = rupees(a.revenue_today_paise);
    $("#a-rev-week").textContent = rupees(a.revenue_week_paise);
    $("#a-rev-total").textContent = rupees(a.revenue_total_paise);
    $("#a-pending").textContent = a.pending_count;
    $("#a-served").textContent = a.served_total;
    $("#a-avg").textContent = rupees(a.avg_order_paise);

    $("#a-top").innerHTML = a.top_items.length
      ? a.top_items
          .map(
            (t, i) => `
        <div class="flex items-center justify-between text-sm">
          <span class="text-slate-300">${i + 1}. ${t.name} <span class="text-slate-500">×${t.qty}</span></span>
          <span class="text-emerald-400 font-semibold">${rupees(t.revenue_paise)}</span>
        </div>`
          )
          .join("")
      : '<p class="text-sm text-slate-500">No sales yet.</p>';

    const ctx = $("#revChart");
    const data = {
      labels: a.days.map((d) => d.label),
      datasets: [
        {
          data: a.days.map((d) => d.revenue_paise / 100),
          backgroundColor: "#10b981",
          borderRadius: 6,
        },
      ],
    };
    const light = document.documentElement.classList.contains("light");
    const tick = light ? "#475569" : "#94a3b8";
    const grid = light ? "#e2e8f0" : "#1e293b";
    if (chart) {
      chart.data = data;
      chart.options.scales.x.ticks.color = tick;
      chart.options.scales.y.ticks.color = tick;
      chart.options.scales.y.grid.color = grid;
      chart.update();
    } else {
      chart = new Chart(ctx, {
        type: "bar",
        data,
        options: {
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { color: tick } },
            y: { grid: { color: grid }, ticks: { color: tick }, beginAtZero: true },
          },
        },
      });
    }
  }

  // ---------------------------------------------------------------- orders
  let orderFilter = "all";
  function badge(delivered) {
    return delivered
      ? '<span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400">Delivered</span>'
      : '<span class="text-xs px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400">Pending</span>';
  }
  async function loadOrders() {
    const list = await getJSON("/api/admin/orders?status=" + orderFilter);
    if (!list) return;
    const el = $("#orders-list");
    if (!list.length) {
      el.innerHTML = '<p class="text-sm text-slate-500 text-center mt-10">No orders here.</p>';
      return;
    }
    el.innerHTML = list
      .map((o) => {
        const items = o.items
          .map((i) => `<span class="text-slate-300">${i.emoji} ${i.name}×${i.qty}</span>`)
          .join('<span class="text-slate-600"> · </span>');
        const t = new Date(o.paid_at || o.created_at).toLocaleString("en-IN", {
          hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short",
        });
        const table = o.table_number
          ? `<span class="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">🪑 Table ${o.table_number}</span>`
          : "";
        const serveBtn = o.delivered
          ? ""
          : `<button data-serve="${o.public_id}" class="mt-3 w-full rounded-xl bg-emerald-600 hover:bg-emerald-500 font-semibold py-2 text-sm">Mark delivered ✓</button>`;
        return `
        <div class="rounded-2xl bg-slate-900 border border-slate-800 p-4">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-bold">${o.public_id}</span>${table}${badge(o.delivered)}
            </div>
            <span class="text-emerald-400 font-bold">${rupees(o.total_paise)}</span>
          </div>
          <p class="text-xs text-slate-500 mt-0.5">${t}</p>
          <div class="mt-2 text-sm leading-relaxed">${items}</div>
          ${serveBtn}
        </div>`;
      })
      .join("");

    $$("[data-serve]").forEach((b) =>
      b.addEventListener("click", async () => {
        b.disabled = true;
        b.textContent = "…";
        try {
          const res = await fetch(`/api/staff/orders/${b.dataset.serve}/serve`, { method: "POST" });
          if (!res.ok) throw new Error((await res.json()).detail);
          loadOrders();
        } catch (e) {
          alert(e.message);
          b.disabled = false;
          b.textContent = "Mark delivered ✓";
        }
      })
    );
  }
  $$(".filter-btn").forEach((b) =>
    b.addEventListener("click", () => {
      orderFilter = b.dataset.filter;
      $$(".filter-btn").forEach((x) =>
        x.classList.toggle("bg-emerald-500", x === b)
      );
      $$(".filter-btn").forEach((x) =>
        x.classList.toggle("text-slate-950", x === b)
      );
      loadOrders();
    })
  );

  // ---------------------------------------------------------------- menu CRUD
  async function loadMenu() {
    const items = await getJSON("/api/admin/menu");
    if (!items) return;
    const cats = [...new Set(items.map((i) => i.category))];
    $("#cat-list").innerHTML = cats.map((c) => `<option value="${c}">`).join("");

    $("#menu-list").innerHTML = items.length
      ? items
          .map((i) => {
            const img = i.image_url
              ? `<img src="${i.image_url}" class="h-14 w-14 rounded-xl object-cover" />`
              : `<div class="h-14 w-14 rounded-xl bg-slate-800 flex items-center justify-center text-2xl">${i.emoji}</div>`;
            return `
          <div class="rounded-2xl bg-slate-900 border border-slate-800 p-3 flex items-center gap-3 ${i.available ? "" : "opacity-60"}">
            ${img}
            <div class="flex-1 min-w-0">
              <p class="font-semibold truncate">${i.name}</p>
              <p class="text-xs text-slate-500">${i.category} · ${rupees(i.price_paise)}</p>
              <p class="text-xs ${i.available ? "text-emerald-400" : "text-rose-400"}">${i.available ? "Available" : "Unavailable"}</p>
            </div>
            <div class="flex flex-col gap-1.5">
              <button data-edit="${i.id}" class="text-xs px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700">Edit</button>
              <button data-toggle="${i.id}" class="text-xs px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700">${i.available ? "Hide" : "Show"}</button>
            </div>
          </div>`;
          })
          .join("")
      : '<p class="text-sm text-slate-500">No items yet. Add your first one.</p>';

    window.__menu = items;
    $$("[data-edit]").forEach((b) =>
      b.addEventListener("click", () => openModal(items.find((x) => x.id == b.dataset.edit)))
    );
    $$("[data-toggle]").forEach((b) =>
      b.addEventListener("click", async () => {
        await fetch(`/api/admin/menu/${b.dataset.toggle}/availability`, { method: "POST" });
        loadMenu();
      })
    );
  }

  // modal
  const modal = $("#item-modal");
  function openModal(item) {
    $("#item-form").reset();
    $("#f-preview").innerHTML = "🍵";
    $("#f-image").value = "";
    if (item) {
      $("#modal-title").textContent = "Edit item";
      $("#f-id").value = item.id;
      $("#f-name").value = item.name;
      $("#f-price").value = item.price_rupees;
      $("#f-emoji").value = item.emoji;
      $("#f-category").value = item.category;
      $("#f-desc").value = item.description;
      $("#f-available").checked = item.available;
      $("#f-preview").innerHTML = item.image_url
        ? `<img src="${item.image_url}" class="h-full w-full object-cover" />`
        : item.emoji;
      $("#f-delete").classList.remove("hidden");
    } else {
      $("#modal-title").textContent = "Add item";
      $("#f-id").value = "";
      $("#f-delete").classList.add("hidden");
    }
    modal.classList.remove("hidden");
  }
  function closeModal() {
    modal.classList.add("hidden");
  }
  $("#add-item-btn").addEventListener("click", () => openModal(null));
  $("#modal-close").addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  $("#f-image").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) $("#f-preview").innerHTML = `<img src="${URL.createObjectURL(file)}" class="h-full w-full object-cover" />`;
  });

  $("#item-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = $("#f-id").value;
    const fd = new FormData();
    fd.append("name", $("#f-name").value);
    fd.append("price", $("#f-price").value);
    fd.append("description", $("#f-desc").value);
    fd.append("category", $("#f-category").value || "Tea");
    fd.append("emoji", $("#f-emoji").value || "🍵");
    fd.append("available", $("#f-available").checked ? "true" : "false");
    if ($("#f-image").files[0]) fd.append("image", $("#f-image").files[0]);

    const url = id ? `/api/admin/menu/${id}` : "/api/admin/menu";
    const method = id ? "PUT" : "POST";
    try {
      const res = await fetch(url, { method, body: fd });
      if (!res.ok) throw new Error((await res.json()).detail || "Failed");
      closeModal();
      loadMenu();
    } catch (err) {
      alert("Could not save: " + err.message);
    }
  });

  $("#f-delete").addEventListener("click", async () => {
    const id = $("#f-id").value;
    if (!id || !confirm("Delete this item?")) return;
    await fetch(`/api/admin/menu/${id}`, { method: "DELETE" });
    closeModal();
    loadMenu();
  });

  // ---------------------------------------------------------------- realtime
  // New paid orders / deliveries refresh the open section live.
  function connectWS() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/staff`);
    ws.onmessage = () => {
      const visible = [...$$("[data-section]")].find((s) => !s.classList.contains("hidden"));
      if (!visible) return;
      if (visible.dataset.section === "orders") loadOrders();
      if (visible.dataset.section === "overview") loadOverview();
    };
    ws.onclose = () => setTimeout(connectWS, 2000);
  }

  // ---------------------------------------------------------------- boot
  const start = ["overview", "orders", "menu"].includes(location.hash.slice(1))
    ? location.hash.slice(1)
    : "overview";
  // default the order filter highlight
  $('.filter-btn[data-filter="all"]').classList.add("bg-emerald-500", "text-slate-950");
  show(start);
  connectWS();
  setInterval(() => {
    const visible = [...$$("[data-section]")].find((s) => !s.classList.contains("hidden"));
    if (visible && visible.dataset.section === "overview") loadOverview();
  }, 15000);
})();
