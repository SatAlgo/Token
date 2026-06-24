// Customer token page: show the booking time, render the QR, cache for offline,
// and flip to "SERVED" the moment the waiter marks the order done. The "live"
// proof (pulsing glow + sweeping shimmer watermark) is pure CSS — no timer.
(function () {
  const order = JSON.parse(document.getElementById("order-data").textContent);
  const jwt = (document.getElementById("token-jwt").textContent || "").trim();

  // --- Static booking time (when the order was placed/paid). No countdown. ---
  const bookedEl = document.getElementById("booked-at");
  if (bookedEl) {
    const when = new Date(order.paid_at || order.created_at);
    bookedEl.textContent = when.toLocaleString("en-IN", {
      hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short",
    });
  }

  // --- QR code holding the signed JWT (or order id if already served) ---
  const qrData = jwt || order.public_id;
  if (window.QRCode) {
    QRCode.toCanvas(qrData, { width: 96, margin: 1 }, (err, canvas) => {
      if (!err) document.getElementById("qr").appendChild(canvas);
    });
  }

  // --- Offline caching: keep the token visible if wifi/power dies ---
  // Stored in localStorage so the PWA can show it even with no network.
  try {
    localStorage.setItem("lastToken:" + order.public_id, JSON.stringify({ order, jwt }));
  } catch (e) {}

  // --- Remember this token in the customer's "My tokens" list (this device) so
  // they can return to it after going back to the menu and order again. ---
  try {
    const KEY = "myTokens";
    const list = JSON.parse(localStorage.getItem(KEY) || "[]");
    const entry = {
      public_id: order.public_id,
      total_paise: order.total_paise,
      table_number: order.table_number,
      created_at: order.created_at,
      items: order.items,
    };
    const idx = list.findIndex((o) => o.public_id === order.public_id);
    if (idx >= 0) list[idx] = entry;
    else list.unshift(entry);
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, 30))); // keep last 30
  } catch (e) {}

  function showServed() {
    document.getElementById("served-overlay").classList.remove("hidden");
    // Stop the glow/shimmer so a static green tick clearly reads as "done".
    const card = document.getElementById("token-card");
    card.classList.remove("token-live");
    card.classList.add("token-served");
    const pill = document.getElementById("live-pill");
    if (pill) pill.classList.add("hidden");
    const st = document.getElementById("status-text");
    st.textContent = "served";
    st.classList.remove("text-emerald-400");
    st.classList.add("text-slate-400");
  }

  if (order.status === "served") showServed();

  // --- Realtime: listen for this order being served ---
  // Customers aren't logged in, so instead of the staff WebSocket we poll the
  // public status endpoint. Lightweight and works behind any network.
  if (order.status === "paid") {
    const poll = setInterval(async () => {
      try {
        const res = await fetch("/api/orders/" + order.public_id);
        if (!res.ok) return;
        const data = await res.json();
        if (data.status === "served") {
          showServed();
          clearInterval(poll);
        }
      } catch (e) {
        // Offline — keep showing the token, nothing to do.
      }
    }, 4000);
  }
})();
