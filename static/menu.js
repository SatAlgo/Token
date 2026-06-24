// Cart + checkout logic for the customer menu page.
(function () {
  const MENU = JSON.parse(document.getElementById("menu-data").textContent);
  const cart = {}; // { itemId: qty }

  const bar = document.getElementById("checkout-bar");
  const countEl = document.getElementById("cart-count");
  const totalEl = document.getElementById("cart-total");
  const payBtn = document.getElementById("pay-btn");

  function rupees(paise) {
    return "₹" + (paise / 100).toFixed(2).replace(/\.00$/, "");
  }

  function render() {
    let count = 0,
      total = 0;
    for (const [id, qty] of Object.entries(cart)) {
      count += qty;
      total += MENU[id].price * qty;
    }
    countEl.textContent = count + (count === 1 ? " item" : " items");
    totalEl.textContent = rupees(total);
    bar.style.transform = count > 0 ? "translateY(0)" : "translateY(100%)";

    document.querySelectorAll("[data-item]").forEach((row) => {
      const id = row.dataset.item;
      const qty = cart[id] || 0;
      row.querySelector(".qty").textContent = qty;
      row.querySelector(".qty-minus").disabled = qty === 0;
    });
  }

  document.querySelectorAll("[data-item]").forEach((row) => {
    const id = row.dataset.item;
    row.querySelector(".qty-plus").addEventListener("click", () => {
      cart[id] = (cart[id] || 0) + 1;
      render();
    });
    row.querySelector(".qty-minus").addEventListener("click", () => {
      if (cart[id]) cart[id]--;
      if (cart[id] === 0) delete cart[id];
      render();
    });
  });

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Request failed");
    }
    return res.json();
  }

  async function checkout() {
    const items = Object.entries(cart).map(([id, qty]) => ({ id: Number(id), qty }));
    if (!items.length) return;

    const tableNumber = (document.getElementById("table-number").value || "").trim();

    payBtn.disabled = true;
    payBtn.classList.add("opacity-60");
    try {
      const order = await postJSON("/api/orders", { items, table_number: tableNumber });
      const pay = order.payment;

      if (pay.mode === "razorpay") {
        await razorpayCheckout(order, pay);
      } else {
        // Demo mode: confirm instantly.
        await finishPayment(order.public_id, {});
      }
    } catch (e) {
      alert("Could not place order: " + e.message);
      payBtn.disabled = false;
      payBtn.classList.remove("opacity-60");
    }
  }

  async function finishPayment(publicId, proof) {
    await postJSON(`/api/orders/${publicId}/pay`, proof);
    // Hand off to the live token page.
    window.location.href = `/t/${publicId}`;
  }

  function razorpayCheckout(order, pay) {
    return new Promise((resolve, reject) => {
      const rzp = new Razorpay({
        key: pay.key_id,
        amount: pay.amount_paise,
        currency: "INR",
        name: order.shop_name,
        description: "Tea shop order " + order.public_id,
        order_id: pay.provider_order_id,
        theme: { color: "#10b981" },
        handler: async function (resp) {
          try {
            await finishPayment(order.public_id, {
              razorpay_payment_id: resp.razorpay_payment_id,
              razorpay_signature: resp.razorpay_signature,
            });
            resolve();
          } catch (e) {
            reject(e);
          }
        },
        modal: {
          ondismiss: () => reject(new Error("Payment cancelled")),
        },
      });
      rzp.open();
    });
  }

  payBtn.addEventListener("click", checkout);
  render();
})();
