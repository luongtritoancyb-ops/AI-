from flask import Flask, render_template, request, jsonify
import osmnx as ox
import networkx as nx
from shapely.ops import unary_union

app = Flask(__name__)

# --- 🔹 Tạo đồ thị từ nhiều phường (mở rộng Thanh Xuân) ---
places = [
    "Quận Thanh Xuân, Hà Nội, Việt Nam",
    "Phường Khương Đình, Hà Nội, Việt Nam",
    "Phường Phương Liệt, Hà Nội, Việt Nam",
    "Phường Hạ Đình, Hà Nội, Việt Nam",
    "Phường Thượng Đình, Hà Nội, Việt Nam",
    "Phường Nhân Chính, Hà Nội, Việt Nam",
    "Phường Kim Giang, Hà Nội, Việt Nam"
]

print("⏳ Đang tải dữ liệu bản đồ các phường...")

polygons = []
for p in places:
    try:
        gdf = ox.geocode_to_gdf(p)
        polygons.append(gdf.geometry.iloc[0])
        print(f"✅ Đã tải: {p}")
    except Exception as e:
        print(f"⚠️ Không tìm thấy dữ liệu cho: {p} — bỏ qua.")

if not polygons:
    raise RuntimeError("❌ Không tải được bất kỳ khu vực nào!")

from shapely.ops import unary_union
combined_polygon = unary_union(polygons)
print(f"✅ Đã hợp nhất {len(polygons)} vùng thành một vùng duy nhất.")

# Tạo đồ thị đường đi cho toàn vùng
G = ox.graph_from_polygon(combined_polygon, network_type="drive", simplify=True)
G_original = G.copy()
print(f"✅ Đã tải xong bản đồ với {len(G.nodes)} nút và {len(G.edges)} cạnh.")

# --- 🔹 Thiết lập tốc độ mặc định cho từng loại đường ---
street_speed = {
    'motorway': 80, 'trunk': 70, 'primary': 60,
    'secondary': 50, 'tertiary': 40,
    'residential': 30, 'service': 20,
    'unclassified': 25, 'living_street': 20,
    'footway': 5, 'path': 5
}

# --- 🔹 Hệ số tốc độ cho từng loại phương tiện ---
vehicle_speed_factor = {
    "car": 1.0,
    "motorbike": 0.8,
    "bicycle": 0.4,
    "foot": 0.2
}

# --- 🔹 Hàm cập nhật trọng số cạnh (theo phương tiện) ---
def update_edge_weights(vehicle_type="car"):
    for u, v, key, data in G.edges(keys=True, data=True):
        highway = data.get("highway", "residential")
        if isinstance(highway, list):
            highway = highway[0]

        base_speed = street_speed.get(highway, 30)
        speed = base_speed * vehicle_speed_factor.get(vehicle_type, 1.0)
        length = G_original.edges[u, v, key].get("length", 1)

        # Trọng số = thời gian di chuyển (độ dài / vận tốc)
        data["weight"] = length / (speed * 1000 / 3600)  # quy đổi km/h -> m/s

# --- 🔹 Hàm tìm đường ngắn nhất ---
def find_route(start_point, end_point, vehicle_type="car"):
    update_edge_weights(vehicle_type)

    orig = ox.distance.nearest_nodes(G, start_point["lng"], start_point["lat"])
    dest = ox.distance.nearest_nodes(G, end_point["lng"], end_point["lat"])

    if not nx.has_path(G, orig, dest):
        return {"error": "❌ Không tìm thấy đường đi phù hợp."}

    route = nx.shortest_path(G, orig, dest, weight="weight")
    coords = [[G.nodes[n]["y"], G.nodes[n]["x"]] for n in route]
    return coords

# --- 🔹 Trang chính ---
@app.route("/")
def index():
    return render_template("index.html")

# --- 🔹 Vẽ đường bao toàn bộ vùng ---
@app.route("/boundary")
def boundary():
    coords = list(combined_polygon.exterior.coords)
    latlng = [[lat, lng] for lng, lat in coords]
    return jsonify(latlng)

# --- 🔹 Tìm đường bằng click ---
@app.route("/find-route-by-click", methods=["POST"])
def find_route_by_click():
    try:
        data = request.get_json()
        p1, p2 = data["point1"], data["point2"]
        vehicle = data.get("vehicle", "car")
        route = find_route(p1, p2, vehicle)
        return jsonify(route)
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    app.run(debug=True)
