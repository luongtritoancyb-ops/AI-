from flask import Flask, render_template, request, jsonify
import osmnx as ox
import networkx as nx
import requests
from shapely.ops import unary_union
import math
import traceback
import re

app = Flask(__name__)

# ======================================================
# 1. CẤU HÌNH & TẢI BẢN ĐỒ
# ======================================================
places = [
      "Quận Thanh Xuân, Hà Nội, Việt Nam",
    "Phường Nhân Chính, Hà Nội, Việt Nam",
    "Phường Thượng Đình, Hà Nội, Việt Nam",
    "Phường Hạ Đình, Hà Nội, Việt Nam",
    "Phường Kim Giang, Hà Nội, Việt Nam",
    "Phường Khương Đình, Hà Nội, Việt Nam",
    "Khương Trung, Thanh Xuân, Hà Nội, Việt Nam",
    "Khương Mai, Thanh Xuân, Hà Nội, Việt Nam",
    "Phường Phương Liệt, Hà Nội, Việt Nam"
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
    
    # [CẢI TIẾN 1] Mở rộng bộ lọc để lấy cả đường đi bộ, cầu thang, đường mòn
    cf = '["highway"~"motorway|trunk|primary|secondary|tertiary|residential|living_street|service|unclassified|footway|pedestrian|path|steps|cycleway"]'
    
    # Tải graph (network_type="all" kết hợp với bộ lọc cf đầy đủ)
    G = ox.graph_from_polygon(combined_polygon, network_type="all", custom_filter=cf, simplify=False)
    
    # Xử lý liên thông
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
# 2. CẤU HÌNH TỐC ĐỘ & LOGIC PHƯƠNG TIỆN
# ======================================================
# Tốc độ mặc định (Fallback) nếu bản đồ không ghi rõ
default_speeds = {
    'motorway': 80, 'trunk': 60, 'primary': 40, 'secondary': 35, 
    'tertiary': 30, 'residential': 25, 'service': 20,
    'footway': 5, 'pedestrian': 5, 'path': 5, 'steps': 2, 'cycleway': 15
}

vehicle_speed_factor = {"car": 1.0, "motorbike": 0.9, "bicycle": 0.6, "foot": 1.0}
banned_edges = set()
traffic_factor = {}

# [CẢI TIẾN 2] Hàm lấy tốc độ thực tế từ dữ liệu OSM (tag 'maxspeed')
def get_real_maxspeed(data, default_val):
    raw_speed = data.get("maxspeed", None)
    if raw_speed:
        try:
            # Xử lý trường hợp maxspeed là list ['40', '50'] -> lấy cái đầu
            if isinstance(raw_speed, list): raw_speed = raw_speed[0]
            # Lọc lấy số từ chuỗi (VD: "50 mph" -> 50)
            numbers = re.findall(r'\d+', str(raw_speed))
            if numbers:
                return int(numbers[0])
        except:
            pass
    return default_val

# ======================================================
# 3. LOGIC TÌM ĐƯỜNG (CORE)
# ======================================================
def heuristic_time(n1, n2, max_speed=60):
    try:
        x1, y1 = G.nodes[n1]["x"], G.nodes[n1]["y"]
        x2, y2 = G.nodes[n2]["x"], G.nodes[n2]["y"]
        R = 6371000
        phi1, phi2 = math.radians(y1), math.radians(y2)
        dphi = math.radians(y2 - y1)
        dlambda = math.radians(x2 - x1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        dist = 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return dist / (max_speed * 1000 / 3600)
    except: return 0

# [CẢI TIẾN 3] Logic cập nhật trọng số thông minh (Phân biệt loại xe vs loại đường)
def update_weights(vehicle):
    coef = vehicle_speed_factor.get(vehicle, 1.0)
    
    # Định nghĩa các loại đường chỉ dành cho đi bộ
    walk_only_roads = ['footway', 'pedestrian', 'path', 'steps']
    # Định nghĩa các loại đường cấm đi bộ (Cao tốc)
    car_only_roads = ['motorway', 'motorway_link', 'trunk', 'trunk_link']

    for u, v, k, data in G.edges(keys=True, data=True):
        # 1. Kiểm tra Cấm đường do Admin
        if (u, v, k) in banned_edges:
            data["weight"] = float("inf")
            continue
        
        # Lấy loại đường
        hw = data.get("highway", "residential")
        if isinstance(hw, list): hw = hw[0]

        # 2. KIỂM TRA QUYỀN TRUY CẬP (ACCESS PERMISSION)
        is_banned = False
        
        # Nếu là Xe Cơ Giới (Car/Motorbike) -> Cấm đi vào đường đi bộ/cầu thang
        if vehicle in ['car', 'motorbike'] and hw in walk_only_roads:
            is_banned = True
            
        # Nếu là Người đi bộ -> Cấm đi vào cao tốc
        if vehicle == 'foot' and hw in car_only_roads:
            is_banned = True

        if is_banned:
            data["weight"] = float("inf")
            continue

        # 3. TÍNH TỐC ĐỘ (Ưu tiên maxspeed thực tế)
        base = default_speeds.get(hw, 25)
        # Nếu là xe cơ giới, cố gắng lấy maxspeed thực tế từ map
        if vehicle in ['car', 'motorbike']:
            base = get_real_maxspeed(data, base)
        
        # Nếu là đi bộ, tốc độ cố định khoảng 5km/h (không phụ thuộc maxspeed đường)
        if vehicle == 'foot':
            real_speed = 5
        else:
            real_speed = base * coef

        if real_speed <= 0: real_speed = 5 # Fallback
        
        # 4. TÍNH TRỌNG SỐ (WEIGHT)
        length = G_original.edges[u, v, k].get("length", 50)
        tf = traffic_factor.get((u, v, k), 1.0)
        
        # Công thức: Thời gian (giây) = Quãng đường / Vận tốc
        data["weight"] = (length / (real_speed * 1000 / 3600)) * tf


def solve_route_logic(p1, p2, vehicle, mode): 
    update_weights(vehicle) # Cập nhật lại toàn bộ bản đồ theo loại xe

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
            # A* tìm đường nhanh nhất (weight = thời gian)
            path = nx.astar_path(G, orig, dest, heuristic=lambda u,v: heuristic_time(u,v), weight="weight")
    except nx.NetworkXNoPath:
        return {"error": "Không tìm thấy đường đi (Có thể do đường cấm hoặc đường một chiều)."}
    
    # Xây dựng Geometry
    coords = []
    total_time = 0
    total_dist = 0
    
    coords.append([p1["lat"], p1["lng"]])
    
    for i in range(len(path)-1):
        u, v = path[i], path[i+1]
        edges = G.get_edge_data(u, v)
        if edges:
            best_key = min(edges, key=lambda k: edges[k].get("weight", float("inf")))
            data = edges[best_key]
        else:
            data = {"length": 0, "weight": 0}

        w = data.get("weight", 0)
        # Nếu đường đi qua cạnh có trọng số vô cực (do lỗi logic nào đó), báo lỗi
        if w == float("inf"): 
            return {"error": "Lỗi: Đường đi chứa đoạn bị cấm!"}
            
        total_time += w
        total_dist += data.get("length", 0)
        
        if "geometry" in data:
            xs, ys = data["geometry"].xy
            segment_coords = [[y, x] for x, y in zip(xs, ys)]
            coords.extend(segment_coords)
        else:
            coords.append([G.nodes[v]["y"], G.nodes[v]["x"]])
    
    coords.append([p2["lat"], p2["lng"]])

    return {
        "coords": coords,
        "time": round(total_time / 60, 2),
        "distance": round(total_dist / 1000, 2),
        "mode": mode,
        "start_point": p1,
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

@app.route("/find-route-by-text", methods=["POST"])
def find_route_text():
    try:
        data = request.json
        t1 = data.get("place1")
        t2 = data.get("place2")
        
        if not t1 or not t2: return jsonify({"error": "Vui lòng nhập tên 2 địa điểm!"})

        headers = {'User-Agent': 'RouteApp/1.0'}
        def get_latlon(query):
            search_query = f"{query}, Hanoi" 
            url = "https://n...content-available-to-author-only...p.org/search"
            res = requests.get(url, params={'q': search_query, 'format': 'json', 'limit': 1}, headers=headers).json()
            if res: return {'lat': float(res[0]['lat']), 'lng': float(res[0]['lon'])}
            return None

        p1 = get_latlon(t1)
        p2 = get_latlon(t2)

        if not p1 or not p2:
            return jsonify({"error": f"Không tìm thấy địa điểm. Hãy nhập cụ thể hơn!"})

        return jsonify(solve_route_logic(
            p1, p2,
            data.get("vehicle", "car"), data.get("mode", "fastest")
        ))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)})

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
        if not street: return jsonify({"error": "Chưa nhập tên đường"})
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