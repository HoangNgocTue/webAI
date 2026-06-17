// Lấy tất cả các nút cập nhật giỏ hàng
var updateBtns = document.getElementsByClassName('update-cart');

// Lặp qua tất cả các nút và thêm sự kiện click
for (let i = 0; i < updateBtns.length; i++) {
    updateBtns[i].addEventListener('click', function () {
        var productId = this.dataset.product;  // Lấy id sản phẩm từ data-product
        var action = this.dataset.action;      // Lấy action từ data-action

        console.log('productId', productId, 'action', action);
        console.log('user:', user);

        // Kiểm tra nếu user là 'AnonymousUser'
        if (user === "AnonymousUser") {
            console.log('User is not logged in');
            // Lưu trữ giỏ hàng trong session hoặc localStorage khi người dùng chưa đăng nhập
            updateUserOrder(productId, action);  // Gọi hàm cập nhật giỏ hàng
        } else {
            console.log('User is logged in');
            // Nếu người dùng đã đăng nhập, cập nhật giỏ hàng của họ
            updateUserOrder(productId, action);
        }
    });
}

// Hàm xử lý cập nhật giỏ hàng
function updateUserOrder(productId, action) {
    console.log('Updating user order...');

    var url = '/update_item/';  // URL for updating the cart

    // Perform the fetch request to update the cart
    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',  // Specify the content type as JSON
            'X-CSRFToken': csrftoken,  // Ensure CSRF token is included in headers
        },
        body: JSON.stringify({'productId': productId, 'action': action}),  // Send the data
    })
    .then((response) => {
        // Check if the response is valid JSON
        if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
        }
        return response.json();  // Parse the JSON response
    })
    .then((data) => {
        console.log('Response from server:', data);
        if (data.cart_items !== undefined) {
            location.reload();  // Reload the page to reflect updated cart
        } else {
            alert('Error: ' + data.error);  // Show an error if something went wrong
        }
    })
    .catch((error) => {
        console.error('Error:', error);
    });
}