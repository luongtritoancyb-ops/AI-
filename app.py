from flask import Flask, render_template, request, jsonify
import osmnx as ox
import networkx as nx
from shapely.ops import unary_union
import math

app = Flask(__name__)


# 🔹 1. TẢI DỮ LIỆU BẢN ĐỒ (OSM)
# Danh sách các phường/quận cần tải

places = [
    "Quận Thanh Xuân, Hà Nội, Việt Nam",
    "Phường Khương Đình, Hà Nội, Việt Nam",
    "Phường Phương Liệt, Hà Nội, Việt Nam",
    "Phường Hạ Đình, Hà Nội, Việt Nam",
    "Phường Thượng Đình, Hà Nội, Việt Nam",
    "Phường Nhân Chính, Hà Nội, Việt Nam",
    "Phường Kim Giang, Hà Nội, Việt Nam"
]

# Lấy polygon của từng khu vực
polygons = []
for p in places:
    try:
        gdf = ox.geocode_to_gdf(p)
        polygons.append(gdf.geometry.iloc[0])
    except:
        pass

# Hợp nhất tất cả polygon thành 1 vùng
combined_polygon = unary_union(polygons)

# Tạo đồ thị đường đi (graph) từ polygon
G = ox.graph_from_polygon(combined_polygon, network_type="drive", simplify=True)
G_original = G.copy()  # Lưu bản gốc để tham chiếu độ dài

# 2. THIẾT LẬP TỐC ĐỘ MẶC ĐỊNH

street_speed = {
    'motorway': 80, 'trunk': 70, 'primary': 60,
    'secondary': 50, 'tertiary': 40,
    'residential': 30, 'service': 20,
    'unclassified': 25, 'living_street': 20,
    'footway': 5, 'path': 5
}

# Hệ số vận tốc theo phương tiện
vehicle_speed_factor = {
    "car": 1.0,
    "motorbike": 0.8,
    "bicycle": 0.4,
    "foot": 0.2
}

# Lưu các tuyến bị cấm hoặc tắc
banned_edges = set()
traffic_factor = {}


# 3. HÀM HEURISTIC CHO A* (dựa vào thời gian)

def heuristic_time(n1, n2, vehicle_speed):
    # Khoảng cách địa lý giữa 2 node
    lat1, lon1 = G.nodes[n1]["y"], G.nodes[n1]["x"]
    lat2, lon2 = G.nodes[n2]["y"], G.nodes[n2]["x"]

    # Công thức Haversine
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    dist = R * c

    # Trả về thời gian ước lượng (giây)
    return dist / (vehicle_speed * 1000 / 3600)


# 4. CẬP NHẬT TRỌNG SỐ CẠNH (theo phương tiện, tắc, cấm)

def update_edge_weights(vehicle="car"):
    coef = vehicle_speed_factor.get(vehicle, 1.0)
    for u, v, k, data in G.edges(keys=True, data=True):
        edge = (u, v, k)
        # Cấm đường → trọng số vô hạn
        if edge in banned_edges:
            data["weight"] = float("inf")
            continue

        highway = data.get("highway", "residential")
        if isinstance(highway, list):
            highway = highway[0]
        base_speed = street_speed.get(highway, 30)
        speed = base_speed * coef
        length = G_original.edges[u, v, k].get("length", 1)
        factor = traffic_factor.get(edge, 1.0)
        data["weight"] = (length / (speed * 1000 / 3600)) * factor


# 5. HÀM XÂY DỰNG ĐƯỜNG CONG (geometry) CHUẨN

def build_route_geometry(route):
    final_coords = []
    for u, v in zip(route[:-1], route[1:]):
        edge_data = G.get_edge_data(u, v, 0)
        if "geometry" in edge_data:
            xs, ys = edge_data["geometry"].xy
            segment = list(zip(ys, xs))  # (lat, lng)
            final_coords.extend(segment)
        else:
            final_coords.append((G.nodes[u]["y"], G.nodes[u]["x"]))
            final_coords.append((G.nodes[v]["y"], G.nodes[v]["x"]))
    return final_coords


# 6. HÀM TÌM ĐƯỜNG (A* hoặc ngắn nhất)

def find_route(start, end, vehicle, mode):
    update_edge_weights(vehicle)
    orig = ox.distance.nearest_nodes(G, start["lng"], start["lat"])
    dest = ox.distance.nearest_nodes(G, end["lng"], end["lat"])

    try:
        if mode == "shortest":
            route = nx.shortest_path(G, orig, dest, weight="length")
        else:  # fastest
            route = nx.astar_path(
                G, orig, dest,
                heuristic=lambda n1, n2: heuristic_time(n1, n2, 50),
                weight="weight"
            )
    except:
        return {"error": "Không tìm được đường đi!"}

    coords = build_route_geometry(route)
    total_time = 0
    for u, v in zip(route[:-1], route[1:]):
        data = G.get_edge_data(u, v, 0)
        total_time += data.get("weight", data.get("length",0)/(50*1000/3600))
    return {"coords": coords, "time": round(total_time,1), "mode": mode}

# 🔹 7. ROUTE API

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/boundary")
def boundary():
    coords = list(combined_polygon.exterior.coords)
    return jsonify([[lat, lng] for lng, lat in coords])

@app.route("/find-route-by-click", methods=["POST"])
def find_by_click():
    data = request.get_json()
    return jsonify(find_route(
        data["point1"], data["point2"],
        data.get("vehicle","car"),
        data.get("mode","fastest")
    ))

@app.route("/find-route-by-text", methods=["POST"])
def find_by_text():
    data = request.get_json()
    lat1, lng1 = ox.geocode(data["place1"])
    lat2, lng2 = ox.geocode(data["place2"])
    start = {"lat":lat1,"lng":lng1}
    end = {"lat":lat2,"lng":lng2}
    return jsonify(find_route(
        start, end,
        data.get("vehicle","car"),
        data.get("mode","fastest")
    ))


# 8. CẬP NHẬT CẤM / TẮC ĐƯỜNG

@app.route("/ban-route", methods=["POST"])
def ban_route_api():
    street = request.json["street"].lower()
    for u,v,k,data in G.edges(keys=True, data=True):
        name = data.get("name","")
        if isinstance(name,list):
            name = " ".join(name)
        if street in str(name).lower():
            banned_edges.add((u,v,k))
    return jsonify({"message":"Đã cấm thành công!"})

@app.route("/change-weight", methods=["POST"])
def change_weight_api():
    street = request.json["street"].lower()
    level = int(request.json["level"])
    factor = [1.0,1.5,2.0,3.0][level]
    for u,v,k,data in G.edges(keys=True,data=True):
        name = data.get("name","")
        if isinstance(name,list):
            name = " ".join(name)
        if street in str(name).lower():
            traffic_factor[(u,v,k)] = factor
    return jsonify({"message":"Đã cập nhật tắc đường!"})

@app.route("/reset", methods=["POST"])
def reset_api():
    banned_edges.clear()
    traffic_factor.clear()
    return jsonify({"message":"Đã reset!"})


#  9. RUN SERVER

if __name__ == "__main__":
    app.run(debug=True)
