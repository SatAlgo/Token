// Waiter board: live list of paid orders + token verification (QR / paste).
(function () {
  const ordersEl = document.getElementById("orders");
  const emptyEl = document.getElementById("empty");
  const tpl = document.getElementById("order-template");
  const seen = new Map(); // public_id -> card element

  function rupees(paise) {
    return "₹" + (paise / 100).toFixed(2).replace(/\.00$/, "");
  }

  function timeAgo(iso) {
    const secs = Math.floor((Date.now() - new Date(iso)) / 1000);
    if (secs < 60) return secs + "s ago";
    return Math.floor(secs / 60) + "m ago";
  }

  function addOrUpdate(order) {
    if (order.status !== "paid") {
      removeCard(order.public_id);
      return;
    }
    if (seen.has(order.public_id)) return;

    const node = tpl.content.cloneNode(true);
    const card = node.querySelector(".order-card");
    card.querySelector(".public-id").textContent = order.public_id;
    card.querySelector(".time").textContent = timeAgo(order.created_at);
    card.querySelector(".total").textContent = rupees(order.total_paise);
    if (order.table_number) {
      const t = card.querySelector(".table");
      t.textContent = "🪑 Table " + order.table_number;
      t.classList.remove("hidden");
    }
    card.querySelector(".items").innerHTML = order.items
      .map((i) => `<div>${i.emoji} ${i.name} × ${i.qty}</div>`)
      .join("");

    const btn = card.querySelector(".serve-btn");
    btn.addEventListener("click", () => serve(order.public_id, btn));

    ordersEl.appendChild(node);
    seen.set(order.public_id, card);
    emptyEl.classList.add("hidden");
  }

  function removeCard(publicId) {
    const card = seen.get(publicId);
    if (card) {
      card.remove();
      seen.delete(publicId);
    }
    if (seen.size === 0) emptyEl.classList.remove("hidden");
  }

  async function serve(publicId, btn) {
    btn.disabled = true;
    btn.textContent = "Serving…";
    try {
      const res = await fetch(`/api/staff/orders/${publicId}/serve`, { method: "POST" });
      if (!res.ok) throw new Error((await res.json()).detail);
      removeCard(publicId); // WS broadcast will also confirm
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Mark served ✓";
      alert("Could not serve: " + e.message);
    }
  }

  async function loadInitial() {
    const res = await fetch("/api/staff/active");
    if (res.status === 401) return (window.location.href = "/login?next=/waiter");
    const list = await res.json();
    list.forEach(addOrUpdate);
  }

  // --- WebSocket for instant updates ---
  const dot = document.getElementById("ws-dot");
  const wsText = document.getElementById("ws-text");

  function connectWS() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/staff`);
    ws.onopen = () => {
      dot.className = "h-2 w-2 rounded-full bg-emerald-400";
      wsText.textContent = "live";
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "order_paid") addOrUpdate(msg.order);
      if (msg.type === "order_served") removeCard(msg.order.public_id);
    };
    ws.onclose = () => {
      dot.className = "h-2 w-2 rounded-full bg-rose-500";
      wsText.textContent = "reconnecting…";
      setTimeout(connectWS, 2000); // auto-reconnect
    };
  }

  // --- Token verification modal ---
  const modal = document.getElementById("verify-modal");
  const resultEl = document.getElementById("verify-result");
  let scanner = null;

  async function verifyToken(token) {
    resultEl.innerHTML = '<p class="text-slate-400 text-sm">Verifying…</p>';
    try {
      const res = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const data = await res.json();
      if (data.valid) {
        const o = data.order;
        resultEl.innerHTML = `
          <div class="rounded-xl bg-emerald-500/15 border border-emerald-500/40 p-4">
            <p class="text-emerald-400 font-bold text-lg">✓ Genuine — ${o.public_id}</p>
            <div class="mt-2 text-sm text-slate-300">${o.items.map((i) => `${i.emoji} ${i.name} × ${i.qty}`).join("<br>")}</div>
            <p class="mt-2 font-bold text-emerald-400">${rupees(o.total_paise)}</p>
            <button id="verify-serve" class="mt-3 w-full rounded-xl bg-emerald-600 font-semibold py-2">Mark served ✓</button>
          </div>`;
        document.getElementById("verify-serve").addEventListener("click", async () => {
          await serve(o.public_id, document.getElementById("verify-serve"));
          closeModal();
        });
      } else {
        resultEl.innerHTML = `
          <div class="rounded-xl bg-rose-500/15 border border-rose-500/40 p-4">
            <p class="text-rose-400 font-bold text-lg">✕ ${data.reason}</p>
            <p class="text-xs text-slate-400 mt-1">Do not serve this token.</p>
          </div>`;
      }
    } catch (e) {
      resultEl.innerHTML = `<p class="text-rose-400 text-sm">Error: ${e.message}</p>`;
    }
  }

  function openModal() {
    modal.classList.remove("hidden");
    resultEl.innerHTML = "";
    if (window.Html5Qrcode) {
      scanner = new Html5Qrcode("reader");
      scanner
        .start({ facingMode: "environment" }, { fps: 10, qrbox: 220 }, (text) => {
          verifyToken(text);
          stopScanner();
        })
        .catch(() => {
          document.getElementById("reader").innerHTML =
            '<p class="text-slate-500 text-xs p-4 text-center">Camera unavailable — paste the token below.</p>';
        });
    }
  }

  function stopScanner() {
    if (scanner) {
      scanner.stop().catch(() => {});
      scanner = null;
    }
  }

  function closeModal() {
    stopScanner();
    modal.classList.add("hidden");
  }

  document.getElementById("scan-btn").addEventListener("click", openModal);
  document.getElementById("verify-close").addEventListener("click", closeModal);
  document.getElementById("manual-verify").addEventListener("click", () => {
    const t = document.getElementById("manual-token").value.trim();
    if (t) verifyToken(t);
  });

  // Refresh "x ago" labels every 20s.
  setInterval(() => {
    seen.forEach((card, id) => {
      // no-op placeholder; times update on reload — kept simple for MVP
    });
  }, 20000);

  loadInitial();
  connectWS();
})();
