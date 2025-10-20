// === Khởi tạo bản đồ ===
let map = L.map("map").setView([21.0362, 105.8342], 15);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

let startMarker = null;
let endMarker = null;
let routeLayer = null;

// === Vẽ đường bao ===
fetch("/boundary")
  .then(res => res.json())
  .then(coords => {
    L.polygon(coords, { color: "blue", weight: 2, fillOpacity: 0.05 }).addTo(map);
  });

// === Click chọn điểm ===
map.on("click", function (e) {
  if (!startMarker) {
    startMarker = L.marker(e.latlng, { draggable: true }).addTo(map);
  } else if (!endMarker) {
    endMarker = L.marker(e.latlng, { draggable: true }).addTo(map);
  }
});

// === Vẽ tuyến đường ===
function drawRoute(coords) {
  if (routeLayer) map.removeLayer(routeLayer);
  routeLayer = L.polyline(coords, { color: "red", weight: 4 }).addTo(map);
  map.fitBounds(routeLayer.getBounds());
}

// === Tìm đường khi click ===
document.getElementById("findRouteBtn").addEventListener("click", () => {
  if (!startMarker || !endMarker) {
    alert("Hãy chọn điểm bắt đầu và kết thúc!");
    return;
  }
  const vehicle = document.getElementById("vehicleSelect").value;
  const payload = {
    point1: { lat: startMarker.getLatLng().lat, lng: startMarker.getLatLng().lng },
    point2: { lat: endMarker.getLatLng().lat, lng: endMarker.getLatLng().lng },
    vehicle: vehicle,
  };
  fetch("/find-route-by-click", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
    .then(res => res.json())
    .then(data => data.error ? alert(data.error) : drawRoute(data))
    .catch(err => console.error(err));
});

// === Tìm đường bằng text ===
document.getElementById("findByTextBtn").addEventListener("click", () => {
  const place1 = document.getElementById("startPlace").value.trim();
  const place2 = document.getElementById("endPlace").value.trim();
  const vehicle = document.getElementById("vehicleSelect").value;
  if (!place1 || !place2) {
    alert("Nhập đầy đủ địa điểm!");
    return;
  }
  fetch("/find-route-by-text", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ place1, place2, vehicle })
  })
    .then(res => res.json())
    .then(data => data.error ? alert(data.error) : drawRoute(data))
    .catch(err => console.error(err));
});

// === Cấm đường ===
document.getElementById("banRouteBtn").addEventListener("click", () => {
  const street = prompt("Nhập tên đường cần cấm:");
  if (!street) return;
  fetch("/ban-route", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ street })
  })
    .then(res => res.json())
    .then(data => alert(data.message))
    .catch(err => console.error(err));
});

// === Thay đổi tốc độ ===
document.getElementById("changeWeightBtn").addEventListener("click", () => {
  const street = prompt("Nhập tên đường:");
  const level = prompt("Mức độ tắc đường (0-3):");
  if (!street || isNaN(level)) return;
  fetch("/change-weight", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ street, level })
  })
    .then(res => res.json())
    .then(data => alert(data.message))
    .catch(err => console.error(err));
});

// === Reset ===
document.getElementById("resetBtn").addEventListener("click", () => {
  fetch("/reset", { method: "POST" })
    .then(res => res.json())
    .then(data => alert(data.message))
    .catch(err => console.error(err));
});
