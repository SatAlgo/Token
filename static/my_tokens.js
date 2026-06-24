// "My tokens" page: list every order placed on this device (from localStorage),
// refresh each one's live status, and link back to its token.
(function () {
  const rupees = (p) => "₹" + (p / 100).toFixed(2).replace(/\.00$/, "");
  const listEl = document.getElementById("tokens-list");
  const emptyEl = document.getElementById("empty");
  const tpl = document.getElementById("token-row");

  let saved = [];
  try {
    saved = JSON.parse(localStorage.getItem("myTokens") || "[]");
  } catch (e) {}

  if (!saved.length) {
    emptyEl.classList.remove("hidden");
    return;
  }

  function statusBadge(el, status) {
    const map = {
      paid: ["Active", "bg-emerald-500/15 text-emerald-400"],
      served: ["Served ✓", "bg-slate-700 text-slate-300"],
      pending_payment: ["Unpaid", "bg-amber-500/15 text-amber-400"],
      cancelled: ["Cancelled", "bg-rose-500/15 text-rose-400"],
    };
    const [text, cls] = map[status] || ["—", "bg-slate-700 text-slate-300"];
    el.textContent = text;
    el.className = "status text-xs px-2 py-0.5 rounded-full " + cls;
  }

  saved.forEach((o) => {
    const node = tpl.content.cloneNode(true);
    const row = node.querySelector(".row");
    row.href = "/t/" + o.public_id;
    row.querySelector(".pid").textContent = o.public_id;
    row.querySelector(".total").textContent = rupees(o.total_paise);
    row.querySelector(".time").textContent = new Date(o.created_at).toLocaleString("en-IN", {
      hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short",
    });
    if (o.table_number) {
      const t = row.querySelector(".table");
      t.textContent = "🪑 " + o.table_number;
      t.classList.remove("hidden");
    }
    // Item thumbnails (image or emoji tile) + quantity.
    row.querySelector(".items").innerHTML = (o.items || [])
      .map((i) =>
        i.image_url
          ? `<img src="${i.image_url}" class="h-9 w-9 rounded-lg object-cover" title="${i.name} ×${i.qty}">`
          : `<span class="h-9 w-9 rounded-lg bg-slate-800 flex items-center justify-center text-lg" title="${i.name} ×${i.qty}">${i.emoji}</span>`
      )
      .join("");
    statusBadge(row.querySelector(".status"), "paid");
    row.dataset.id = o.public_id;
    listEl.appendChild(node);
  });

  // Refresh live status from the server (served/active). Works offline-tolerant.
  saved.forEach(async (o) => {
    try {
      const res = await fetch("/api/orders/" + o.public_id);
      if (!res.ok) return;
      const data = await res.json();
      const row = listEl.querySelector(`[data-id="${o.public_id}"]`);
      if (row) statusBadge(row.querySelector(".status"), data.status);
    } catch (e) {
      // offline — leave the cached "Active" badge as-is
    }
  });
})();
