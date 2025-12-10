// --- 1. KHỞI TẠO BẢN ĐỒ & BIẾN TOÀN CỤC ---
// Tọa độ trung tâm Hà Nội (Thanh Xuân)
var map = L.map('map').setView([21.000, 105.820], 14);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap'
}).addTo(map);

// Các biến quản lý trạng thái
var points = [];        // Lưu tọa độ 2 điểm click (Start, End)
var markers = [];       // Lưu object Marker trên bản đồ (để xóa sau này)
var ban_routes = [];    // Lưu các đường màu đỏ (cấm đường)
var routeLayer = null;  // Lưu đường đi màu xanh (kết quả tìm kiếm)

// Hàm hiển thị màn hình Loading (Spinner)
function showLoading(isShow) {
    const loader = document.getElementById('loading');
    if (loader) loader.style.display = isShow ? 'flex' : 'none';
}

// --- 2. VẼ RANH GIỚI PHƯỜNG (KHI LOAD TRANG) ---
// Gọi API lấy dữ liệu boundary để vẽ viền mờ các phường
fetch('/boundary')
    .then(res => res.json())
    .then(coords => {
        if (!coords.error) {
            L.polygon(coords, {
                color: '#555', 
                weight: 1, 
                fillColor: '#3388ff',
                fillOpacity: 0.05, 
                dashArray: '5, 5'
            }).addTo(map);
        }
    })
    .catch(err => console.error("Lỗi tải boundary:", err));


// --- 3. HÀM DỌN DẸP BẢN ĐỒ (Helper) ---
// keepInput = true: Giữ lại text trong ô input (dùng khi tìm bằng text)
// keepInput = false: Xóa hết (dùng khi click mới hoặc reset)
function clearRouteOnly(keepInput = false) {
    // Xóa đường đi màu xanh cũ
    if (routeLayer) {
        map.removeLayer(routeLayer);
        routeLayer = null;
    }

    // Xóa các marker cũ (A và B)
    markers.forEach(m => map.removeLayer(m));
    markers = [];
    points = []; // Reset mảng điểm click

    // Ẩn hộp kết quả
    const resultBox = document.getElementById('result-box');
    if(resultBox) resultBox.style.display = 'none';

    // Xóa text trong ô input nếu cần
    if (!keepInput) {
        document.getElementById('startPlace').value = "";
        document.getElementById('endPlace').value = "";
    }
}


// --- 4. XỬ LÝ CLICK TRÊN BẢN ĐỒ (Logic cốt lõi) ---
map.on('click', function(e) {
    // Nếu đã có kết quả cũ, xóa đi để chọn lại từ đầu
    if (routeLayer || points.length >= 2) {
        clearRouteOnly(false); 
    }

    var latlng = e.latlng;
    points.push(latlng);

    // Tạo Marker
    var marker;
    if (points.length === 1) {
        // Điểm đầu: Icon mặc định xanh
        marker = L.marker(latlng).addTo(map).bindPopup('Điểm xuất phát').openPopup();
        document.getElementById('startPlace').value = latlng.lat.toFixed(5) + ", " + latlng.lng.toFixed(5);
    } else {
        // Điểm cuối: Icon đỏ
        marker = L.marker(latlng, {
            icon: L.icon({
                iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/markers-default/red-icon.png',
                iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34]
            })
        }).addTo(map).bindPopup('Điểm đến').openPopup();
        document.getElementById('endPlace').value = latlng.lat.toFixed(5) + ", " + latlng.lng.toFixed(5);
    }
    markers.push(marker);

    // Khi đủ 2 điểm -> GỌI API TÌM ĐƯỜNG NGAY LẬP TỨC
    if (points.length === 2) {
        showLoading(true);

        // Lấy thêm thông tin phương tiện và chế độ từ giao diện
        var vehicle = document.getElementById('vehicleSelect').value;
        var mode = document.getElementById('modeSelect').value;

        fetch('/find-route-by-click', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                point1: {lat: points[0].lat, lng: points[0].lng},
                point2: {lat: points[1].lat, lng: points[1].lng},
                vehicle: vehicle, 
                mode: mode        
            })
        })
        .then(res => res.json())
        .then(data => {
            showLoading(false);
            if (data.error) {
                alert(data.error);
                clearRouteOnly(false); // Lỗi thì xóa làm lại
            } else {
                // Vẽ đường màu xanh
                routeLayer = L.polyline(data.coords, { color: 'blue', weight: 6, opacity: 0.8 }).addTo(map);
                map.fitBounds(routeLayer.getBounds());

                // Cập nhật bảng kết quả (Hiển thị thời gian/quãng đường)
                const resultBox = document.getElementById('result-box');
                if(resultBox) {
                    resultBox.style.display = 'block';
                    document.getElementById('timeDisplay').innerText = data.time;
                    document.getElementById('distDisplay').innerText = data.distance || "--";
                    document.getElementById('modeDisplay').innerText = (data.mode === 'fastest') ? "Nhanh nhất" : "Ngắn nhất";
                }
            }
        })
        .catch(err => {
            showLoading(false);
            console.error(err);
            alert("Lỗi kết nối Server!");
        });
    }
});

// Nút "Tìm (Click)" chỉ mang tính chất hướng dẫn hoặc reset
const findClickBtn = document.getElementById('findRouteBtn');
if(findClickBtn) {
    findClickBtn.addEventListener('click', function() {
        alert("Hãy click trực tiếp 2 điểm trên bản đồ để tìm đường!");
    });
}


// --- 5. TÌM ĐƯỜNG BẰNG TEXT (Nút "Tìm (Text)") ---
const findTextBtn = document.getElementById('findByTextBtn');
if(findTextBtn) {
    findTextBtn.addEventListener('click', function() {
        var p1 = document.getElementById('startPlace').value;
        var p2 = document.getElementById('endPlace').value;
        var vehicle = document.getElementById('vehicleSelect').value;
        var mode = document.getElementById('modeSelect').value;

        if (!p1 || !p2) {
            alert("Vui lòng nhập địa điểm vào cả 2 ô!");
            return;
        }

        showLoading(true);
        fetch('/find-route-by-text', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                place1: p1,
                place2: p2,
                vehicle: vehicle,
                mode: mode
            })
        })
        .then(res => res.json())
        .then(data => {
            showLoading(false);
            if (data.error) {
                alert(data.error);
            } else {
                // Dọn dẹp cũ nhưng giữ lại text trong input
                clearRouteOnly(true);

                // Vẽ đường
                routeLayer = L.polyline(data.coords, { color: 'blue', weight: 6, opacity: 0.8 }).addTo(map);
                map.fitBounds(routeLayer.getBounds());

                // Tạo marker ảo ở đầu và cuối đường (vì tìm bằng text nên chưa có marker)
                var startPt = data.coords[0];
                var endPt = data.coords[data.coords.length - 1];
                
                var m1 = L.marker(startPt).addTo(map).bindPopup(p1).openPopup();
                var m2 = L.marker(endPt, {icon: L.icon({
                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/markers-default/red-icon.png',
                    iconSize: [25, 41], iconAnchor: [12, 41]
                })}).addTo(map).bindPopup(p2);
                markers.push(m1, m2);

                // Hiển thị kết quả
                const resultBox = document.getElementById('result-box');
                if(resultBox) {
                    resultBox.style.display = 'block';
                    document.getElementById('timeDisplay').innerText = data.time;
                    document.getElementById('distDisplay').innerText = data.distance || "--";
                    document.getElementById('modeDisplay').innerText = (data.mode === 'fastest') ? "Nhanh nhất" : "Ngắn nhất";
                }
            }
        })
        .catch(err => {
            showLoading(false);
            alert("Lỗi server hoặc không tìm thấy địa điểm!");
        });
    });
}


// --- 6. CÁC CHỨC NĂNG ADMIN (CẤM / TẮC) ---

// Chức năng: Cấm đường (Vẽ vạch đỏ)
const banBtn = document.getElementById('banRouteBtn');
if(banBtn) {
    banBtn.addEventListener('click', function() {
        var street = document.getElementById('streetInput').value;
        if (!street) { alert("Nhập tên đường cần cấm!"); return; }

        showLoading(true);
        fetch('/ban-route', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ street: street })
        })
        .then(res => res.json())
        .then(data => {
            showLoading(false);
            alert(data.message);
            // Nếu server trả về geometry các đoạn bị cấm -> Vẽ lên bản đồ
            if (data.routes) {
                data.routes.forEach(line => {
                    var banLine = L.polyline(line, { color: 'red', weight: 4, dashArray: '10, 10' }).addTo(map);
                    ban_routes.push(banLine);
                });
            }
        })
        .catch(err => {
            showLoading(false);
            console.error(err);
        });
    });
}

// Chức năng: Báo tắc đường (Thay đổi trọng số)
const weightBtn = document.getElementById('changeWeightBtn');
if(weightBtn) {
    weightBtn.addEventListener('click', function() {
        var street = document.getElementById('streetInput').value;
        var level = document.getElementById('trafficLevel').value; // Lấy từ slider
        
        if (!street) { alert("Nhập tên đường!"); return; }

        showLoading(true);
        fetch('/change-weight', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ street: street, level: level })
        })
        .then(res => res.json())
        .then(data => {
            showLoading(false);
            alert(data.message);
        });
    });
}

// Chức năng: Reset toàn bộ
const resetBtn = document.getElementById('resetBtn');
if(resetBtn) {
    resetBtn.addEventListener('click', function() {
        if(!confirm("Bạn có chắc muốn Reset toàn bộ dữ liệu giao thông (cấm/tắc)?")) return;
        
        fetch('/reset', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            alert(data.message);
            // Xóa các đường đỏ (ban routes)
            ban_routes.forEach(l => map.removeLayer(l));
            ban_routes = [];
            // Xóa đường tìm kiếm hiện tại
            clearRouteOnly(false);
        });
    });
}


// --- 7. UI EVENT LISTENERS (Giao diện phụ trợ) ---

// Cập nhật số hiển thị khi kéo thanh trượt mức độ tắc
const trafficSlider = document.getElementById('trafficLevel');
if(trafficSlider) {
    trafficSlider.addEventListener('input', function() {
        document.getElementById('levelValue').innerText = this.value;
    });
}

// Nút bật tắt sidebar trên mobile
const toggleBtn = document.getElementById('toggle-sidebar');
if(toggleBtn) {
    toggleBtn.addEventListener('click', function() {
        document.getElementById('sidebar').classList.toggle('active');
    });
}

// Hàm global để xóa đường vẽ thủ công (nút "Xóa đường vẽ")
window.clearMap = function() {
    clearRouteOnly(false);
};