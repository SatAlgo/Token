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
    if (res.status === 401) return (window.location.href = "/login");
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

  // --- Token verification (shared modal: code / QR / paste) ---
  document.getElementById("scan-btn").addEventListener("click", () => {
    // When served from the verify modal, the WebSocket broadcast removes the card.
    window.TokenVerify.open({ onServed: () => {} });
  });

  loadInitial();
  connectWS();
})();
