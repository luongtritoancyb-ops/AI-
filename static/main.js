// --- 1. KHỞI TẠO BẢN ĐỒ & BIẾN TOÀN CỤC ---
var map = L.map('map').setView([21.000, 105.820], 14);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '© OpenStreetMap'
}).addTo(map);

var points = [];
var markers = [];
var ban_routes = [];
var routeLayer = null;

function showLoading(isShow) {
    const loader = document.getElementById('loading');
    if (loader) loader.style.display = isShow ? 'flex' : 'none';
}

// --- 2. VẼ RANH GIỚI PHƯỜNG ---
fetch('/boundary')
    .then(res => res.json())
    .then(coords => {
        if (coords && coords.length) {
            L.polygon(coords, {
                color: '#555', weight: 2, fillColor: '#3388ff',
                fillOpacity: 0.1, dashArray: '5, 5'
            }).addTo(map);
        }
    })
    .catch(err => console.error("Lỗi tải boundary:", err));

// --- 3. HELPER: DỌN DẸP BẢN ĐỒ ---
function clearRouteOnly(keepInput = false) {
    if (routeLayer) { map.removeLayer(routeLayer); routeLayer = null; }
    markers.forEach(m => map.removeLayer(m));
    markers = [];
    points = [];

    const resultBox = document.getElementById('result-box');
    if (resultBox) resultBox.style.display = 'none';

    if (!keepInput) {
        document.getElementById('startPlace').value = "";
        document.getElementById('endPlace').value = "";
    }
}
// Hàm global cho nút "Xóa đường vẽ"
window.clearMap = function () { clearRouteOnly(false); };

// --- 4. XỬ LÝ CLICK TÌM ĐƯỜNG ---
map.on('click', function (e) {
    if (routeLayer || points.length >= 2) clearRouteOnly(false);

    var latlng = e.latlng;
    points.push(latlng);

    var iconHtml = points.length === 1 ? '<i class="fas fa-map-marker-alt fa-3x"></i>' : '<i class="fas fa-flag-checkered fa-2x"></i>';
    var className = points.length === 1 ? 'custom-icon start-icon' : 'custom-icon end-icon';
    var customIcon = L.divIcon({ html: iconHtml, className: className, iconSize: [32, 42], iconAnchor: [16, 42] });

    markers.push(L.marker(latlng, { icon: customIcon }).addTo(map));

    if (points.length === 1) document.getElementById('startPlace').value = latlng.lat.toFixed(5) + ", " + latlng.lng.toFixed(5);
    else document.getElementById('endPlace').value = latlng.lat.toFixed(5) + ", " + latlng.lng.toFixed(5);

    if (points.length === 2) {
        callFindRouteAPI(points[0], points[1], false);
    }
});

function callFindRouteAPI(p1, p2, isTextMode) {
    showLoading(true);
    var vehicle = document.getElementById('vehicleSelect').value;
    var mode = document.getElementById('modeSelect').value;

    // Chuẩn bị body request tùy theo chế độ Text hay Click
    let bodyData = { vehicle: vehicle, mode: mode };
    if (isTextMode) {
        bodyData.place1 = p1; // p1 là string địa chỉ
        bodyData.place2 = p2;
    } else {
        bodyData.point1 = { lat: p1.lat, lng: p1.lng }; // p1 là object tọa độ
        bodyData.point2 = { lat: p2.lat, lng: p2.lng };
    }

    let endpoint = isTextMode ? '/find-route-by-text' : '/find-route-by-click';

    fetch(endpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bodyData)
    })
        .then(res => res.json())
        .then(data => {
            showLoading(false);
            if (data.error) { alert(data.error); if (!isTextMode) clearRouteOnly(false); }
            else { drawResult(data, isTextMode); }
        })
        .catch(err => { showLoading(false); alert("Lỗi kết nối Server!"); });
}

function drawResult(data, isTextMode) {
    if (isTextMode) clearRouteOnly(true); // Giữ text input

    routeLayer = L.polyline(data.coords, { color: 'blue', weight: 6, opacity: 0.8 }).addTo(map);
    map.fitBounds(routeLayer.getBounds());

    // Nếu là Text Mode thì cần thêm marker (vì chưa có)
    if (isTextMode) {
        var startIcon = L.divIcon({ html: '<i class="fas fa-map-marker-alt fa-3x"></i>', className: 'custom-icon start-icon', iconSize: [32, 42], iconAnchor: [16, 42] });
        var endIcon = L.divIcon({ html: '<i class="fas fa-flag-checkered fa-2x"></i>', className: 'custom-icon end-icon', iconSize: [32, 42], iconAnchor: [16, 42] });

        var startPt = data.coords[0];
        var endPt = data.coords[data.coords.length - 1];

        markers.push(L.marker(startPt, { icon: startIcon }).addTo(map));
        markers.push(L.marker(endPt, { icon: endIcon }).addTo(map));
    }

    const resultBox = document.getElementById('result-box');
    if (resultBox) {
        resultBox.style.display = 'block';
        document.getElementById('timeDisplay').innerText = data.time;
        document.getElementById('distDisplay').innerText = data.distance || "--";
        document.getElementById('modeDisplay').innerText = (data.mode === 'fastest') ? "Nhanh nhất" : "Ngắn nhất";
    }
}

// --- 5. EVENT LISTENERS ---

// Nút Tìm (Text)
const findTextBtn = document.getElementById('findByTextBtn');
if (findTextBtn) {
    findTextBtn.addEventListener('click', function () {
        var p1 = document.getElementById('startPlace').value;
        var p2 = document.getElementById('endPlace').value;
        if (!p1 || !p2) return alert("Vui lòng nhập địa điểm!");
        callFindRouteAPI(p1, p2, true);
    });
}

// Nút Cấm đường
const banBtn = document.getElementById('banRouteBtn');
if (banBtn) {
    banBtn.addEventListener('click', function () {
        var street = document.getElementById('streetInput').value;
        if (!street) return alert("Nhập tên đường cần cấm!");
        showLoading(true);
        fetch('/ban-route', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ street: street })
        }).then(r => r.json()).then(d => {
            showLoading(false); alert(d.message);
            if (d.routes) d.routes.forEach(l => ban_routes.push(L.polyline(l, { color: 'red', weight: 4, dashArray: '10,10' }).addTo(map)));
        });
    });
}

// Nút Báo tắc
const weightBtn = document.getElementById('changeWeightBtn');
if (weightBtn) {
    weightBtn.addEventListener('click', function () {
        var street = document.getElementById('streetInput').value;
        var level = document.getElementById('trafficLevel').value;
        if (!street) return alert("Nhập tên đường!");
        showLoading(true);
        fetch('/change-weight', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ street: street, level: level })
        }).then(r => r.json()).then(d => { showLoading(false); alert(d.message); });
    });
}

// Nút Reset
const resetBtn = document.getElementById('resetBtn');
if (resetBtn) {
    resetBtn.addEventListener('click', function () {
        if (!confirm("Reset toàn bộ dữ liệu giao thông?")) return;
        fetch('/reset', { method: 'POST' }).then(r => r.json()).then(d => {
            alert(d.message);
            ban_routes.forEach(l => map.removeLayer(l)); ban_routes = [];
            clearRouteOnly(false);
        });
    });
}

// Slider update text
const slider = document.getElementById('trafficLevel');
if (slider) {
    slider.addEventListener('input', function () {
        document.getElementById('levelValue').innerText = this.value;
    });
}

// Mobile Toggle
const toggleBtn = document.getElementById('toggle-sidebar');
if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
        document.getElementById('sidebar').classList.toggle('active');
    });
}