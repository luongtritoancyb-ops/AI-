from flask import Flask, render_template, request, jsonify
import osmnx as ox
import networkx as nx
import requests
from shapely.ops import unary_union
import math
import traceback

app = Flask(__name__)

# ======================================================
# 1. CẤU HÌNH & TẢI BẢN ĐỒ
# ======================================================

places = [
    "Quận Thanh Xuân, Hà Nội, Việt Nam",
    "Phường Khương Đình, Hà Nội, Việt Nam",
    "Phường Phương Liệt, Hà Nội, Việt Nam",
    "Phường Hạ Đình, Hà Nội, Việt Nam",
    "Phường Thượng Đình, Hà Nội, Việt Nam",
    "Phường Nhân Chính, Hà Nội, Việt Nam",
    "Phường Kim Giang, Hà Nội, Việt Nam"
]

print("⏳ Đang tải dữ liệu bản đồ... (Vui lòng đợi 1-2 phút)")

polygons = []
for p in places:
    try:
        gdf = ox.geocode_to_gdf(p)
        polygons.append(gdf.geometry.iloc[0])
        print(f" - ✅ Đã tải: {p}")
    except Exception as e:
        print(f" - ⚠️ Bỏ qua: {p}")

if not polygons:
    print("❌ LỖI: Không tải được bản đồ.")
    exit()

try:
    combined_polygon = unary_union(polygons)
    print("⏳ Đang xây dựng đồ thị giao thông...")
    
    G = ox.graph_from_polygon(combined_polygon, network_type="drive", simplify=True)
    
    # Xử lý liên thông để tránh lỗi đường cụt
    if len(G) > 0:
        largest_cc = max(nx.strongly_connected_components(G), key=len)
        G = G.subgraph(largest_cc).copy()
    
    G_original = G.copy()
    print(f"✅ Bản đồ sẵn sàng! {len(G.nodes)} nút.")

except Exception as e:
    print(f"❌ LỖI KHỞI TẠO: {e}")
    G = nx.MultiDiGraph()
    combined_polygon = None


# ======================================================
# 2. CẤU HÌNH TỐC ĐỘ
# ======================================================

street_speed = {'motorway': 60, 'trunk': 50, 'primary': 40, 'secondary': 35, 'tertiary': 30, 'residential': 25, 'service': 20}
vehicle_speed_factor = {"car": 1.0, "motorbike": 0.9, "bicycle": 0.5, "foot": 0.2}
banned_edges = set()
traffic_factor = {}

# ======================================================
# 3. LOGIC TÌM ĐƯỜNG (CORE)
# ======================================================

def heuristic_time(n1, n2, max_speed=60):
    try:
        x1, y1 = G.nodes[n1]["x"], G.nodes[n1]["y"]
        x2, y2 = G.nodes[n2]["x"], G.nodes[n2]["y"]
        dist = math.sqrt((x1-x2)**2 + (y1-y2)**2) * 111000 
        return dist / (max_speed * 1000 / 3600)
    except: return 0

def update_weights(vehicle):
    coef = vehicle_speed_factor.get(vehicle, 1.0)
    for u, v, k, data in G.edges(keys=True, data=True):
        if (u, v, k) in banned_edges:
            data["weight"] = float("inf")
            continue
        
        hw = data.get("highway", "residential")
        if isinstance(hw, list): hw = hw[0]
        base_speed = street_speed.get(hw, 25)
        length = G_original.edges[u, v, k].get("length", 50)
        tf = traffic_factor.get((u, v, k), 1.0)
        
        real_speed = base_speed * coef
        if real_speed <= 0: real_speed = 5
        
        data["weight"] = (length / (real_speed * 1000 / 3600)) * tf

def solve_route_logic(p1, p2, vehicle, mode):
    """Hàm xử lý chung cho cả Click và Text"""
    update_weights(vehicle)

    # Tìm node gần nhất
    try:
        orig = ox.nearest_nodes(G, p1["lng"], p1["lat"])
        dest = ox.nearest_nodes(G, p2["lng"], p2["lat"])
    except:
        return {"error": "Điểm chọn nằm ngoài vùng bản đồ!"}

    if orig == dest:
        return {"error": "Điểm đi và đến quá gần nhau!"}

    try:
        if mode == "shortest":
            path = nx.shortest_path(G, orig, dest, weight="length")
        else:
            path = nx.astar_path(G, orig, dest, heuristic=lambda u,v: heuristic_time(u,v), weight="weight")
    except nx.NetworkXNoPath:
        return {"error": "Không tìm thấy đường đi (Khu vực bị ngăn cách)."}
    
    # Xây dựng geometry
    coords = []
    total_time = 0
    total_dist = 0
    
    for i in range(len(path)-1):
        u, v = path[i], path[i+1]
        data = G.get_edge_data(u, v)[0]
        
        w = data.get("weight", 0)
        if w != float("inf"): total_time += w
        total_dist += data.get("length", 0)
        
        if "geometry" in data:
            xs, ys = data["geometry"].xy
            coords.extend([[y, x] for x, y in zip(xs, ys)])
        else:
            coords.append([G.nodes[v]["y"], G.nodes[v]["x"]])
    
    coords.insert(0, [p1["lat"], p1["lng"]])
    coords.append([p2["lat"], p2["lng"]])

    return {
        "coords": coords,
        "time": round(total_time / 60, 2),
        "distance": round(total_dist / 1000, 2),
        "mode": mode,
        "start_point": p1, # Trả lại tọa độ để vẽ marker
        "end_point": p2
    }

# ======================================================
# 4. API ROUTES
# ======================================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/boundary")
def boundary():
    if combined_polygon is None: return jsonify([])
    try:
        poly = combined_polygon
        if poly.geom_type == 'MultiPolygon': poly = poly.convex_hull
        return jsonify([[lat, lng] for lng, lat in list(poly.exterior.coords)])
    except: return jsonify([])

@app.route("/find-route-by-click", methods=["POST"])
def find_route_click():
    try:
        data = request.json
        return jsonify(solve_route_logic(
            data["point1"], data["point2"],
            data.get("vehicle", "car"), data.get("mode", "fastest")
        ))
    except Exception as e:
        return jsonify({"error": str(e)})

# --- SỬA LỖI: API TÌM BẰNG TEXT HOẠT ĐỘNG THẬT ---
@app.route("/find-route-by-text", methods=["POST"])
def find_route_text():
    try:
        data = request.json
        t1 = data.get("place1")
        t2 = data.get("place2")
        
        if not t1 or not t2:
            return jsonify({"error": "Vui lòng nhập tên 2 địa điểm!"})

        # Hàm Geocoding: Chuyển Tên -> Tọa độ
        headers = {'User-Agent': 'RouteApp/1.0'}
        def get_latlon(query):
            # Thêm ngữ cảnh "Hanoi" để tìm chính xác
            search_query = f"{query}, Hanoi" 
            url = "https://nominatim.openstreetmap.org/search"
            res = requests.get(url, params={'q': search_query, 'format': 'json', 'limit': 1}, headers=headers).json()
            if res:
                return {'lat': float(res[0]['lat']), 'lng': float(res[0]['lon'])}
            return None

        p1 = get_latlon(t1)
        p2 = get_latlon(t2)

        if not p1 or not p2:
            return jsonify({"error": f"Không tìm thấy địa điểm '{t1}' hoặc '{t2}'. Hãy nhập cụ thể hơn!"})

        # Sau khi có tọa độ, gọi hàm logic chung
        return jsonify(solve_route_logic(
            p1, p2,
            data.get("vehicle", "car"), data.get("mode", "fastest")
        ))

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)})

# --- ADMIN API ---
@app.route("/ban-route", methods=["POST"])
def ban_route():
    try:
        street = request.json.get("street", "").lower()
        if not street: return jsonify({"error": "Chưa nhập tên đường"})
        count = 0
        viz = []
        for u, v, k, data in G.edges(keys=True, data=True):
            names = data.get('name', [])
            if not isinstance(names, list): names = [names]
            if any(street in str(n).lower() for n in names):
                banned_edges.add((u, v, k))
                count += 1
                if "geometry" in data:
                    xs, ys = data["geometry"].xy
                    viz.append([[y, x] for x, y in zip(xs, ys)])
                else:
                    n_u, n_v = G.nodes[u], G.nodes[v]
                    viz.append([[n_u['y'], n_u['x']], [n_v['y'], n_v['x']]])
        if count == 0: return jsonify({"message": "Không tìm thấy đường!", "status": "error"})
        return jsonify({"message": f"Đã cấm {count} đoạn!", "routes": viz})
    except Exception as e: return jsonify({"error": str(e)})

@app.route("/change-weight", methods=["POST"])
def change_weight():
    try:
        street = request.json.get("street", "").lower()
        level = int(request.json.get("level", 1))
        factor = {1:1.5, 2:3.0, 3:10.0}.get(level, 1.0)
        count = 0
        for u, v, k, data in G.edges(keys=True, data=True):
            names = data.get('name', [])
            if not isinstance(names, list): names = [names]
            if any(street in str(n).lower() for n in names):
                traffic_factor[(u, v, k)] = factor
                count += 1
        return jsonify({"message": f"Đã báo tắc {count} đoạn!"})
    except Exception as e: return jsonify({"error": str(e)})

@app.route("/reset", methods=["POST"])
def reset():
    banned_edges.clear(); traffic_factor.clear()
    return jsonify({"message": "Đã Reset!"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)