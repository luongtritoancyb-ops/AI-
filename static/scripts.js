let map = L.map('map').setView([21.038235, 105.826213], 15);
let points = [];
let markers = [];    // Lưu marker điểm đi/đến (Màu xanh)
let ban_routes = []; // Lưu đường cấm (Màu đỏ)
let polyline;        // Lưu đường đi tìm được (Màu xanh)


// 1. KHỞI TẠO BẢN ĐỒ
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);


// 2. TẠO ĐƯỜNG BAO
fetch('/boundary')
.then(res => res.json())
.then(coords => {
    const polygon = L.polygon(coords, {
        color: 'green',
        weight: 2,
        fillOpacity: 0.2
    }).addTo(map);
    map.fitBounds(polygon.getBounds());
})
.catch(err => {
    console.error('Lỗi khi lấy đường bao:', err);
});


// --- HÀM QUẢN LÝ DỌN DẸP BẢN ĐỒ (ĐÃ NÂNG CẤP) ---
// keepInput = true: Giữ lại chữ trong ô tìm kiếm (Dùng khi ấn nút Tìm)
// keepInput = false: Xóa trắng hết (Dùng khi ấn nút Xóa hoặc Click mới)
function clearRouteOnly(keepInput = false) {
    // Xóa đường kẻ xanh
    if (polyline) {
        map.removeLayer(polyline);
        polyline = null;
    }

    // Xóa các marker điểm A, B
    if (markers.length > 0) {
        markers.forEach(m => map.removeLayer(m));
        markers = [];
    }

    // Reset mảng điểm click (để bắt đầu quy trình click mới)
    points = [];

    // Chỉ xóa text trong ô input nếu không yêu cầu giữ lại
    if (!keepInput) {
        document.getElementById('placeInput1').value = "";
        document.getElementById('placeInput2').value = "";
    }
}


// 3. XỬ LÝ SỰ KIỆN CLICK TRÊN BẢN ĐỒ
map.on('click', function(e) {
    // Nếu đã có đường vẽ cũ (do tìm kiếm trước đó), xóa đi để chọn lại từ đầu
    if (polyline || points.length >= 2) {
        clearRouteOnly(false); // Xóa sạch cả input để tránh nhầm lẫn
    }

    const latlng = e.latlng;
    points.push(latlng);

    // Xác định điểm xuất phát
    if (points.length == 1) {
        const marker = L.marker(latlng).addTo(map).bindPopup('Điểm xuất phát').openPopup();
        markers.push(marker);
    } 
    // Xác định điểm đến
    else {
        const marker = L.marker(latlng).addTo(map).bindPopup('Điểm đến').openPopup();
        markers.push(marker);
    }

    // Khi đủ 2 điểm -> Gửi về Server
    if (points.length === 2) {
        fetch('/find-route-by-click', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                point1: {lat: points[0].lat, lng: points[0].lng},
                point2: {lat: points[1].lat, lng: points[1].lng}
            })
        })
        .then(res => res.json())
        .then(coords => {
            if (coords.length > 0) {
                polyline = L.polyline(coords, { color: 'blue' }).addTo(map);
                map.fitBounds(polyline.getBounds());
            } else {
                alert(coords.error || "Không tìm thấy đường đi giữa 2 điểm này!");
                // Nếu lỗi thì xóa điểm vừa chọn để chọn lại
                clearRouteOnly(false);
            }
        })
        .catch(err => {
            console.error(err);
            alert("Lỗi kết nối Server! Hãy kiểm tra xem Python đã chạy chưa.");
        });
    }
});


// 4. HÀM TÌM ĐƯỜNG BẰNG TEXT (NÚT "TÌM")
function findRoute() {
    const start = document.getElementById('placeInput1').value;
    const end = document.getElementById('placeInput2').value;

    if (!start || !end) {
        alert("Vui lòng nhập đầy đủ điểm đi và điểm đến!");
        return;
    }

    fetch('/find-route-by-text', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            place1: start,
            place2: end
        })
    })
    .then(res => res.json())
    .then(coords => {
        if (coords.length > 0) {
            // Dọn dẹp bản đồ cũ NHƯNG giữ lại chữ trong ô input
            clearRouteOnly(true);

            // Vẽ marker mới từ kết quả trả về
            // (Vì tìm bằng tên nên tọa độ marker chính xác do Server trả về)
            const start_marker = L.marker(coords[0]).addTo(map).bindPopup('Xuất phát: ' + start).openPopup();
            const end_marker = L.marker(coords[coords.length-1]).addTo(map).bindPopup('Đích: ' + end).openPopup();
            markers.push(start_marker, end_marker);

            // Vẽ đường đi
            polyline = L.polyline(coords, { color: 'blue' }).addTo(map);
            map.fitBounds(polyline.getBounds());
        } else {
            alert(coords.error || "Không tìm thấy địa điểm hoặc đường đi!");
        }
    })
    .catch(err => {
        console.error(err);
        alert("Lỗi hệ thống hoặc mất kết nối Server!");
    });
}


// 5. HÀM ADMIN: THAY ĐỔI TRỌNG SỐ / CẤM ĐƯỜNG (NÚT "XÁC NHẬN")
function changeWeight() {
    const selected = document.querySelector('input[name="action"]:checked');
    const street = document.getElementById('streetInput').value;

    if (!street) {
        alert("Vui lòng nhập tên đường!");
        return;
    }

    if (selected && selected.value == "change") {
        const level = document.getElementById('level').value
        fetch('/change-weight', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                street: street,
                level: level
            })
        })
        .then(res => res.json())
        .then(data => alert(data.message))
        .catch(err => console.error(err));
    } else {
        fetch('/ban-route', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({street: street})
        })
        .then(res => res.json())
        .then(data => {
            alert(data.message);
            if (data.routes) {
                data.routes.forEach(line => {
                    const ban_route = L.polyline(line, { color: 'red', weight: 3, dashArray: '5, 10' }).addTo(map);
                    ban_routes.push(ban_route);
                })
            }
        })
        .catch(err => console.error(err));
    }
}


// 6. HÀM RESET GRAPH (NÚT "RESET" - MÀU ĐỎ)
// Hàm này xóa cả đường vẽ VÀ gọi server để hủy cấm đường
function resetGraph() {
    if(!confirm("Bạn có chắc chắn muốn xóa hết các lệnh cấm đường và tắc đường không?")) return;

    // Xóa đường cấm màu đỏ trên map
    ban_routes.forEach(line => map.removeLayer(line));
    ban_routes = [];
    
    // Xóa sạch bản đồ (cả input)
    clearRouteOnly(false);

    // Gọi về server reset biến G
    fetch('/reset', {method: 'POST'})
    .then(res => res.json())
    .then(data => alert(data.message))
    .catch(err => console.error(err));
}


// 7. CÁC HÀM UI (SIDEBAR, SLIDER)
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const main = document.getElementById('main');
    sidebar.classList.toggle('appear');
    main.classList.toggle('minimize');
}

const levelSlider = document.getElementById('level');
const levelValue = document.getElementById('levelValue');

levelSlider.addEventListener('input', function () {
    levelValue.textContent = levelSlider.value;
});