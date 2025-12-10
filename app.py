from flask import Flask, render_template, request, jsonify   #  Import Flask và các hàm xử lý HTTP
import osmnx as ox                                           #  Thư viện lấy dữ liệu OSM
import networkx as nx                                        #  Xử lý đồ thị
import requests                                              #  Gọi API geocoding
from shapely.ops import unary_union                          #  Gộp nhiều polygon thành 1 polygon
import math                                                  #  Dùng tính khoảng cách
import traceback                                             #  In lỗi chi tiết

app = Flask(__name__)                                        #  Tạo app Flask

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

print("⏳ Đang tải dữ liệu bản đồ... ")

polygons = []                                                #  Lưu danh sách polygon từng phường
for p in places:
    try:
        # Lấy polygon. Cấu hình nominatim=True để dùng công cụ tìm kiếm tên linh hoạt hơn
        gdf = ox.geocode_to_gdf(p)
        polygons.append(gdf.geometry.iloc[0])
        print(f" - ✅ Đã tải thành công: {p}")
        
    except Exception as e:
        # 👉 DEBUG: In lỗi chi tiết ra để biết tại sao không tải được
        print(f" - ⚠️ Bỏ qua: {p}")
        print(f"   └── Lỗi chi tiết: {str(e)}")                          #  Nếu lỗi → bỏ qua

if not polygons:
    print("❌ LỖI: Không tải được bản đồ.")
    exit()

try:
    combined_polygon = unary_union(polygons)                 #  Gộp toàn bộ polygon thành một
    print("⏳ Đang xây dựng đồ thị giao thông...")
    cf = '["highway"~"motorway|trunk|primary|secondary|tertiary|residential|living_street|service|unclassified"]'
    G = ox.graph_from_polygon(combined_polygon, custom_filter=cf, simplify=False)
                                                             #  Tải graph đường ô tô từ polygon
    
    # Xử lý liên thông để tránh lỗi đường cụt
    if len(G) > 0:
        largest_cc = max(nx.strongly_connected_components(G), key=len)
                                                             #  Lấy thành phần liên thông lớn nhất
        G = G.subgraph(largest_cc).copy()                    #  Dùng graph liên thông để tránh NoPath
    
    G_original = G.copy()                                    #  Lưu graph gốc để lấy chiều dài chuẩn
    print(f"✅ Bản đồ sẵn sàng! {len(G.nodes)} nút.")

except Exception as e:
    print(f"❌ LỖI KHỞI TẠO: {e}")
    G = nx.MultiDiGraph()
    combined_polygon = None


# ======================================================
#           2. CẤU HÌNH TỐC ĐỘ
# ======================================================

street_speed = {'motorway': 60, 'trunk': 50, 'primary': 40,  #  Tốc độ mặc định cho từng loại đường
                'secondary': 35, 'tertiary': 30,
                'residential': 25, 'service': 20}

vehicle_speed_factor = {"car": 1.0, "motorbike": 0.9,        #  Hệ số giảm tốc ứng theo phương tiện
                        "bicycle": 0.5, "foot": 0.2}

banned_edges = set()                                         #  Lưu các đoạn bị cấm
traffic_factor = {}                                          #  Lưu hệ số tắc đường


# ======================================================
#           3. LOGIC TÌM ĐƯỜNG (CORE)
# ======================================================

def heuristic_time(n1, n2, max_speed=60):                    #  Heuristic cho A* (ước lượng thời gian)
    try:
        x1, y1 = G.nodes[n1]["x"], G.nodes[n1]["y"]
        x2, y2 = G.nodes[n2]["x"], G.nodes[n2]["y"]
        dist = math.sqrt((x1-x2)**2 + (y1-y2)**2) * 111000   #  Đổi độ → mét
        return dist / (max_speed * 1000 / 3600)              #  Đổi tốc độ → m/s
    except: return 0

def update_weights(vehicle):                                 #  Cập nhật trọng số (thời gian → dùng A*)
    coef = vehicle_speed_factor.get(vehicle, 1.0)
    for u, v, k, data in G.edges(keys=True, data=True):
        if (u, v, k) in banned_edges:                        #  Đoạn bị cấm → vô hạn
            data["weight"] = float("inf")
            continue
        
        hw = data.get("highway", "residential")
        if isinstance(hw, list): hw = hw[0]                  #  highway có thể là list
        base_speed = street_speed.get(hw, 25)                #  Nếu không có thì mặc định 25 km/h
        length = G_original.edges[u, v, k].get("length", 50)
        tf = traffic_factor.get((u, v, k), 1.0)              #  Tắc đường → tăng thời gian
        
        real_speed = base_speed * coef                       #  Tốc độ thực tế theo phương tiện
        if real_speed <= 0: real_speed = 5
        
        data["weight"] = (length / (real_speed * 1000 / 3600)) * tf
                                                             #  Trọng số = thời gian đi đoạn này

def solve_route_logic(p1, p2, vehicle, mode):
    """Hàm xử lý chung cho cả Click và Text"""
    update_weights(vehicle)                                  #  Cập nhật trọng số

    # Tìm node gần nhất
    try:
        orig = ox.nearest_nodes(G, p1["lng"], p1["lat"])     #  lng trước, lat sau
        dest = ox.nearest_nodes(G, p2["lng"], p2["lat"])
    except:
        return {"error": "Điểm chọn nằm ngoài vùng bản đồ!"}

    if orig == dest:
        return {"error": "Điểm đi và đến quá gần nhau!"}

    try:
        if mode == "shortest":
            path = nx.shortest_path(G, orig, dest, weight="length")
                                                             #  Đường ngắn nhất theo mét
        else:
            path = nx.astar_path(G, orig, dest,
                                 heuristic=lambda u,v: heuristic_time(u,v),
                                 weight="weight")            #  Đường nhanh nhất theo A*
    except nx.NetworkXNoPath:
        return {"error": "Không tìm thấy đường đi (Khu vực bị ngăn cách)."}

    # Xây dựng geometry đường đi
    coords = []
    total_time = 0
    total_dist = 0
    
    for i in range(len(path)-1):
        u, v = path[i], path[i+1]
        data = G.get_edge_data(u, v)[0]
        
        w = data.get("weight", 0)
        if w != float("inf"): total_time += w                #  Cộng thời gian
        total_dist += data.get("length", 0)                  #  Cộng chiều dài
        
        if "geometry" in data:
            xs, ys = data["geometry"].xy
            coords.extend([[y, x] for x, y in zip(xs, ys)])  #  Lấy polyline chuẩn
        else:
            coords.append([G.nodes[v]["y"], G.nodes[v]["x"]])

    coords.insert(0, [p1["lat"], p1["lng"]])                  #  Thêm point đầu
    coords.append([p2["lat"], p2["lng"]])                    #  Thêm point cuối

    return {
        "coords": coords,
        "time": round(total_time / 60, 2),                   #  phút
        "distance": round(total_dist / 1000, 2),             #  km
        "mode": mode,
        "start_point": p1,
        "end_point": p2
    }

# ======================================================
# 4. API ROUTES
# ======================================================

@app.route("/")
def index():
    return render_template("index.html")                     #  Render web UI

@app.route("/boundary")
def boundary():
    if combined_polygon is None: return jsonify([])
    try:
        poly = combined_polygon
        if poly.geom_type == 'MultiPolygon': poly = poly.convex_hull
                                                             #  Vẽ convex hull tránh răng cưa
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

# --- API TÌM BẰNG TEXT ---
@app.route("/find-route-by-text", methods=["POST"])
def find_route_text():
    try:
        data = request.json
        t1 = data.get("place1")
        t2 = data.get("place2")
        
        if not t1 or not t2:
            return jsonify({"error": "Vui lòng nhập tên 2 địa điểm!"})

        headers = {'User-Agent': 'RouteApp/1.0'}

        def get_latlon(query):                               #  Geocoding tên → lat/lng
            search_query = f"{query}, Hanoi"
            url = "https://nominatim.openstreetmap.org/search"
            res = requests.get(url, params={'q': search_query, 'format': 'json',
                                            'limit': 1}, headers=headers).json()
            if res:
                return {'lat': float(res[0]['lat']), 'lng': float(res[0]['lon'])}
            return None

        p1 = get_latlon(t1)
        p2 = get_latlon(t2)

        if not p1 or not p2:
            return jsonify({"error": f"Không tìm thấy địa điểm '{t1}' hoặc '{t2}'. Hãy nhập cụ thể hơn!"})

        return jsonify(solve_route_logic(
            p1, p2, data.get("vehicle", "car"),
            data.get("mode", "fastest")
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
            names = data.get('name', [])                     # 👉 Tên đường
            if not isinstance(names, list): names = [names]
            
            if any(street in str(n).lower() for n in names): # 👉 Match theo chuỗi
                banned_edges.add((u, v, k))                  # 👉 Đánh dấu cấm
                count += 1

                if "geometry" in data:                       # 👉 Trả về polyline để UI vẽ
                    xs, ys = data["geometry"].xy
                    viz.append([[y, x] for x, y in zip(xs, ys)])
                else:
                    n_u, n_v = G.nodes[u], G.nodes[v]
                    viz.append([[n_u['y'], n_u['x']], [n_v['y'], n_v['x']]])

        if count == 0:
            return jsonify({"message": "Không tìm thấy đường!", "status": "error"})

        return jsonify({"message": f"Đã cấm {count} đoạn!", "routes": viz})

    except Exception as e: return jsonify({"error": str(e)})

@app.route("/change-weight", methods=["POST"])
def change_weight():
    try:
        street = request.json.get("street", "").lower()
        level = int(request.json.get("level", 1))            # 👉 Mức độ tắc: 1 = nhẹ, 3 = nặng
        factor = {1:1.5, 2:3.0, 3:10.0}.get(level, 1.0)

        count = 0
        for u, v, k, data in G.edges(keys=True, data=True):
            names = data.get('name', [])
            if not isinstance(names, list): names = [names]
            
            if any(street in str(n).lower() for n in names):
                traffic_factor[(u, v, k)] = factor           #  Gán hệ số tắc đường
                count += 1

        return jsonify({"message": f"Đã báo tắc {count} đoạn!"})

    except Exception as e: return jsonify({"error": str(e)})

@app.route("/reset", methods=["POST"])
def reset():
    banned_edges.clear()
    traffic_factor.clear()
    return jsonify({"message": "Đã Reset!"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)                           #  Chạy local
