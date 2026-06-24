// Shared token-verification modal used by both the waiter board and the admin
// dashboard. Three ways to verify, most-reliable first:
//   1. Type the short code (T-XXXX) shown on the customer's token  <- always works
//   2. Scan the QR with the camera (needs https/localhost + permission)
//   3. Paste the full token
// On a genuine, unserved token it offers a "Mark served" button.
//
// Usage:  window.TokenVerify.open({ onServed: () => reloadMyList() })
(function () {
  const rupees = (p) => "₹" + (p / 100).toFixed(2).replace(/\.00$/, "");
  let modal = null;
  let scanner = null;
  let onServedCb = null;

  function build() {
    if (modal) return;
    modal = document.createElement("div");
    modal.className =
      "hidden fixed inset-0 z-50 bg-slate-950/90 backdrop-blur p-4 overflow-y-auto";
    modal.innerHTML = `
      <div class="mx-auto max-w-md w-full">
        <div class="flex justify-between items-center mb-3">
          <h2 class="font-bold text-lg">Verify token</h2>
          <button data-close class="text-slate-400 text-2xl leading-none">✕</button>
        </div>

        <label class="text-xs text-slate-400">Token code (shown big on the customer's token)</label>
        <div class="flex gap-2 mt-1">
          <input data-code placeholder="T-9F3A2C" autocapitalize="characters" autocomplete="off"
            class="flex-1 rounded-xl bg-slate-900 border border-slate-700 px-3 py-3 text-lg font-mono uppercase tracking-wider focus:outline-none focus:border-emerald-500" />
          <button data-code-btn class="rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold px-5">Check</button>
        </div>

        <div class="my-3 flex items-center gap-3 text-xs text-slate-500">
          <span class="flex-1 h-px bg-slate-800"></span> or scan the QR <span class="flex-1 h-px bg-slate-800"></span>
        </div>
        <div data-reader id="verify-reader" class="rounded-xl overflow-hidden bg-black aspect-square"></div>

        <details class="mt-3">
          <summary class="text-xs text-slate-500 cursor-pointer">Paste full token instead</summary>
          <textarea data-paste rows="2" placeholder="Paste token…"
            class="mt-2 w-full rounded-xl bg-slate-900 border border-slate-700 px-3 py-2 text-xs"></textarea>
          <button data-paste-btn class="mt-2 w-full rounded-xl bg-slate-800 hover:bg-slate-700 py-2 text-sm">Verify pasted token</button>
        </details>

        <div data-result class="mt-3"></div>
      </div>`;
    document.body.appendChild(modal);

    modal.querySelector("[data-close]").addEventListener("click", close);
    modal.addEventListener("click", (e) => {
      if (e.target === modal) close();
    });
    const codeInput = modal.querySelector("[data-code]");
    const checkCode = () => {
      const c = codeInput.value.trim();
      if (c) doVerify({ public_id: c });
    };
    modal.querySelector("[data-code-btn]").addEventListener("click", checkCode);
    codeInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") checkCode();
    });
    modal.querySelector("[data-paste-btn]").addEventListener("click", () => {
      const t = modal.querySelector("[data-paste]").value.trim();
      if (t) doVerify({ token: t });
    });
  }

  async function doVerify(body) {
    const resultEl = modal.querySelector("[data-result]");
    resultEl.innerHTML = '<p class="text-slate-400 text-sm">Verifying…</p>';
    try {
      const res = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      render(await res.json());
    } catch (e) {
      resultEl.innerHTML = `<p class="text-rose-400 text-sm">Error: ${e.message}</p>`;
    }
  }

  function render(data) {
    const resultEl = modal.querySelector("[data-result]");
    if (!data.valid) {
      const extra = data.order ? ` (${data.order.public_id})` : "";
      resultEl.innerHTML = `
        <div class="rounded-xl bg-rose-500/15 border border-rose-500/40 p-4">
          <p class="text-rose-400 font-bold text-lg">✕ ${data.reason}${extra}</p>
          <p class="text-xs text-slate-400 mt-1">Do not serve unless it's genuine.</p>
        </div>`;
      return;
    }
    const o = data.order;
    const table = o.table_number ? ` · 🪑 Table ${o.table_number}` : "";
    resultEl.innerHTML = `
      <div class="rounded-xl bg-emerald-500/15 border border-emerald-500/40 p-4">
        <p class="text-emerald-400 font-bold text-lg">✓ Genuine — ${o.public_id}${table}</p>
        <div class="mt-2 text-sm text-slate-300">${o.items
          .map((i) => `${i.emoji || "🍵"} ${i.name} ×${i.qty}`)
          .join("<br>")}</div>
        <p class="mt-2 font-bold text-emerald-400">${rupees(o.total_paise)}</p>
        <button data-serve class="mt-3 w-full rounded-xl bg-emerald-600 hover:bg-emerald-500 font-semibold py-2.5">Mark served ✓</button>
      </div>`;
    resultEl.querySelector("[data-serve]").addEventListener("click", async (e) => {
      const btn = e.target;
      btn.disabled = true;
      btn.textContent = "Serving…";
      try {
        const r = await fetch(`/api/staff/orders/${o.public_id}/serve`, { method: "POST" });
        if (!r.ok) throw new Error((await r.json()).detail || "Failed");
        resultEl.innerHTML =
          `<div class="rounded-xl bg-emerald-500/15 border border-emerald-500/40 p-4 text-emerald-400 font-bold text-center">✓ Served ${o.public_id}</div>`;
        if (onServedCb) onServedCb();
        setTimeout(close, 1000);
      } catch (err) {
        btn.disabled = false;
        btn.textContent = "Mark served ✓";
        alert("Could not serve: " + err.message);
      }
    });
  }

  function startScanner() {
    const readerEl = modal.querySelector("[data-reader]");
    if (!window.Html5Qrcode) {
      readerEl.innerHTML =
        '<p class="text-slate-500 text-xs p-6 text-center">QR scanner not loaded — type the code above.</p>';
      return;
    }
    try {
      scanner = new Html5Qrcode("verify-reader");
      scanner
        .start({ facingMode: "environment" }, { fps: 10, qrbox: 220 }, (text) => {
          stopScanner();
          // The QR holds a JWT, or just the order code if the token was served.
          if (text.startsWith("T-")) doVerify({ public_id: text });
          else doVerify({ token: text });
        })
        .catch(() => {
          readerEl.innerHTML =
            '<p class="text-slate-500 text-xs p-6 text-center">Camera unavailable — type the code above instead.</p>';
        });
    } catch (e) {
      readerEl.innerHTML =
        '<p class="text-slate-500 text-xs p-6 text-center">Camera unavailable — type the code above instead.</p>';
    }
  }

  function stopScanner() {
    if (scanner) {
      scanner.stop().catch(() => {});
      scanner = null;
    }
  }

  function open(opts) {
    onServedCb = (opts && opts.onServed) || null;
    build();
    modal.querySelector("[data-result]").innerHTML = "";
    modal.querySelector("[data-code]").value = "";
    modal.classList.remove("hidden");
    modal.querySelector("[data-code]").focus();
    startScanner();
  }

  function close() {
    stopScanner();
    if (modal) modal.classList.add("hidden");
  }

  window.TokenVerify = { open };
})();
