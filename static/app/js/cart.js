const updateBtns = document.getElementsByClassName("update-cart");

function formatVnd(value) {
    return new Intl.NumberFormat("vi-VN").format(Math.round(Number(value) || 0)) + "đ";
}

function setCartButtonsDisabled(disabled) {
    Array.from(updateBtns).forEach((button) => {
        button.disabled = disabled;
    });
}

function updateHeaderCartCount(count) {
    document.querySelectorAll(".cart-count, .cart-badge").forEach((el) => {
        el.textContent = count > 0 ? count : "";
    });
}

async function updateUserOrder(productId, action) {
    setCartButtonsDisabled(true);

    try {
        const response = await fetch("/update_item/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrftoken,
            },
            body: JSON.stringify({ productId, action }),
        });

        if (response.status === 401) {
            window.location.href = "/login/";
            return;
        }

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || data.error || "Không cập nhật được giỏ hàng");
        }

        const itemRow = document.getElementById(`cart-item-${productId}`);
        const qtyEl = document.getElementById(`qty-${productId}`);
        const itemTotalEl = document.getElementById(`item-total-${productId}`);
        const cartItemCountEl = document.getElementById("cart-item-count");
        const cartGrandTotalEl = document.getElementById("cart-grand-total");

        if (data.removed && itemRow) {
            itemRow.remove();
        } else {
            if (qtyEl) qtyEl.textContent = data.quantity;
            if (itemTotalEl) itemTotalEl.textContent = formatVnd(data.item_total);
        }

        if (cartItemCountEl) cartItemCountEl.textContent = data.cart_items;
        if (cartGrandTotalEl) cartGrandTotalEl.textContent = formatVnd(data.cart_total);
        updateHeaderCartCount(data.cart_items);

        if (data.cart_items === 0) {
            window.location.reload();
        }
    } catch (error) {
        console.error("Cart update failed:", error);
        alert(error.message || "Không cập nhật được giỏ hàng. Vui lòng thử lại.");
    } finally {
        setCartButtonsDisabled(false);
    }
}

Array.from(updateBtns).forEach((button) => {
    button.addEventListener("click", function () {
        const productId = this.dataset.product;
        const action = this.dataset.action;

        if (user === "AnonymousUser") {
            window.location.href = "/login/";
            return;
        }

        updateUserOrder(productId, action);
    });
});
