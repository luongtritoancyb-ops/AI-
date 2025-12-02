from flask import Flask, render_template, request, jsonify
import osmnx as ox
import networkx as nx
import requests
from shapely.ops import unary_union # Di chuyển import lên đầu cho chuẩn

app = Flask(__name__)

# --- CẤU HÌNH BAN ĐẦU ---
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

# Hợp nhất các polygon
combined_polygon = unary_union(polygons)
print(f"✅ Đã hợp nhất {len(polygons)} vùng thành một vùng duy nhất.")

# Tạo đồ thị đường đi cho toàn vùng
G = ox.graph_from_polygon(combined_polygon, network_type="drive", simplify=True)
G_original = G.copy()
print(f"✅ Đã tải xong bản đồ với {len(G.nodes)} nút và {len(G.edges)} cạnh.")

street_speed = {
    'secondary': 40, 'tertiary': 30, 'residential': 20, 
    'service': 10, 'steps': 5, 'path': 5, 'footway': 5
}

# --- XỬ LÝ TRỌNG SỐ BAN ĐẦU ---
# Thay đổi thuộc tính 'length' của các cạnh thành thời gian di chuyển
for u, v, key, data in G.edges(keys=True, data=True):
    speed_min = 40
    if 'highway' in data:
        if isinstance(data['highway'], list):
            for i in data['highway']:
                if i in street_speed and street_speed[i] < speed_min:
                    speed_min = street_speed[i]
        else:
            hw_type = data['highway']
            if hw_type in street_speed:
                speed_min = street_speed[hw_type]
    
    # Tính thời gian (hoặc trọng số mới)
    data['length'] /= speed_min

# Lưu lại bản gốc để dùng cho chức năng Reset
G_original = G.copy()


# --- CÁC HÀM XỬ LÝ ---

def find_route(start_point, end_point):
    try:
        # Tìm 2 nodes gần nhất
        orig = ox.nearest_nodes(G, start_point['lng'], start_point['lat'])
        dest = ox.nearest_nodes(G, end_point['lng'], end_point['lat'])

        # Kiểm tra tính hợp lệ và sự tồn tại của đường đi
        orig_check = ox.nearest_nodes(G, start_point['lng'], start_point['lat'])
        dest_check = ox.nearest_nodes(G, end_point['lng'], end_point['lat'])

        if (orig != orig_check or dest != dest_check or not nx.has_path(G, orig, dest)):
            return {"error": "Không tìm thấy đường đi hoặc điểm nằm ngoài vùng hỗ trợ"}
        
        # Tìm đường ngắn nhất (Dijkstra)
        route = nx.shortest_path(G, orig, dest, weight='length')
        
        # --- [CẬP NHẬT MỚI] LẤY HÌNH DÁNG ĐƯỜNG CONG (GEOMETRY) ---
        route_coords = []
        
        # Thêm điểm click ban đầu
        route_coords.append([start_point['lat'], start_point['lng']])

        # Duyệt qua từng đoạn đường để lấy geometry
        for i in range(len(route) - 1):
            u = route[i]
            v = route[i+1]
            
            # Lấy dữ liệu cạnh (edge). Sử dụng key=0 (mặc định)
            edge_data = G.get_edge_data(u, v)[0]
            
            if 'geometry' in edge_data:
                # Nếu có geometry (đường cong), lấy tọa độ chi tiết
                xs, ys = edge_data['geometry'].xy
                # Zip lại thành [lat, lng] (Lưu ý: shapely trả về x=lng, y=lat)
                geom_coords = [[y, x] for x, y in zip(xs, ys)]
                route_coords.extend(geom_coords)
            else:
                # Nếu là đường thẳng, lấy tọa độ node đích
                route_coords.append([G.nodes[v]['y'], G.nodes[v]['x']])

        # Thêm điểm click kết thúc
        route_coords.append([end_point['lat'], end_point['lng']])
        
        return jsonify(route_coords)

    except Exception as e:
        print(f"Lỗi tìm đường: {e}")
        return {"error": str(e)}


def check_street_exists(street_name, data):
    if 'name' not in data:
        return False
    if isinstance(data['name'], list):
        for street in data['name']:
            if street_name.lower() == street.lower():
                return True
    else:
        if street_name.lower() == data['name'].lower():
            return True
    return False


# --- CÁC API ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/boundary')
def boundary():
    # --- [FIX LỖI TẠI ĐÂY] ---
    # Lỗi cũ: sử dụng biến 'place_name' không tồn tại.
    # Sửa: Sử dụng trực tiếp 'combined_polygon' đã load ở đầu file.
    try:
        poly_to_draw = combined_polygon
        
        # Nếu hợp nhất nhiều phường tạo thành MultiPolygon (do không liền mạch hoàn toàn),
        # ta lấy convex_hull (bao lồi) để vẽ viền bao quanh tránh lỗi crash.
        if poly_to_draw.geom_type == 'MultiPolygon':
            poly_to_draw = poly_to_draw.convex_hull
            
        coords = list(poly_to_draw.exterior.coords)
        latlng_coords = [[lat, lng] for lng, lat in coords]
        return jsonify(latlng_coords)
    except Exception as e:
        return {"error": str(e)}

@app.route('/find-route-by-click', methods=['POST'])
def find_route_by_click():
    try:
        data = request.get_json()
        start_point = data['point1']
        end_point = data['point2']
        return find_route(start_point, end_point)
    except Exception as e:
        return {"error": str(e)}

@app.route('/find-route-by-text', methods=['POST'])
def find_route_by_text():
    try:
        data = request.get_json()
        start_place = data['place1']
        end_place = data['place2']

        headers = {'User-Agent': 'FindRouteApp'}
        url = 'https://nominatim.openstreetmap.org/search'
        
        # Tìm điểm đi
        params1 = {'q': start_place, 'format': 'json', 'limit': 1}
        res1 = requests.get(url, params=params1, headers=headers).json()
        if not res1: return {"error": "Điểm xuất phát không hợp lệ"}
        start_point = {'lat': float(res1[0]['lat']), 'lng': float(res1[0]['lon'])}

        # Tìm điểm đến
        params2 = {'q': end_place, 'format': 'json', 'limit': 1}
        res2 = requests.get(url, params=params2, headers=headers).json()
        if not res2: return {"error": "Điểm đích không hợp lệ"}
        end_point = {'lat': float(res2[0]['lat']), 'lng': float(res2[0]['lon'])}

        return find_route(start_point, end_point)
    except Exception as e:
        return {"error": str(e)}

@app.route('/change-weight', methods=['POST'])
def change_weight():
    try:
        data = request.get_json()
        street_name = data['street']
        level = float(data['level'])
        exist = False

        for u, v, key, data in G.edges(keys=True, data=True):
            if check_street_exists(street_name, data):
                exist = True
                # Tính lại speed_min cục bộ để thay đổi trọng số
                speed_min = 40 # Mặc định
                if 'highway' in data:
                    if isinstance(data['highway'], list):
                        for i in data['highway']:
                            if i in street_speed and street_speed[i] < speed_min:
                                speed_min = street_speed[i]
                    elif data['highway'] in street_speed:
                        speed_min = street_speed[data['highway']]
                
                # Công thức tính trọng số mới của bạn
                original_len = G_original.edges[u, v, key]['length'] # Lấy từ bản gốc cho chuẩn
                data['length'] = (original_len * speed_min) / (speed_min * (1 - level * 0.25))

        if exist:
            return {"message": "Trọng số đã được thay đổi"}
        return {"message": f"Không tìm thấy đường \"{street_name}\""}
    
    except Exception as e:
        return {"error": str(e)}

@app.route('/ban-route', methods=['POST'])
def ban_route():
    try:
        data = request.get_json()
        street_name = data['street']
        edge_to_remove = []
        routes_removed_viz = [] # Danh sách chứa tọa độ để vẽ lên bản đồ

        # 1. Tìm tất cả các cạnh trùng tên đường
        for u, v, key, edge_data in G.edges(keys=True, data=True):
            if check_street_exists(street_name, edge_data):
                # Lưu lại cả edge_data để tí nữa lấy geometry
                edge_to_remove.append((u, v, key, edge_data))

        if not edge_to_remove:
            return {"message": f"Không tìm thấy đường \"{street_name}\" trong khu vực."}

        # 2. Xử lý lấy tọa độ (geometry) và xóa cạnh
        for u, v, key, edge_data in edge_to_remove:
            # --- [LOGIC MỚI] LẤY HÌNH DÁNG CONG ---
            if 'geometry' in edge_data:
                # Nếu cạnh có thuộc tính geometry (đường cong)
                xs, ys = edge_data['geometry'].xy
                # Chuyển đổi sang dạng [[lat, lng], [lat, lng], ...]
                geom_coords = [[y, x] for x, y in zip(xs, ys)]
                routes_removed_viz.append(geom_coords)
            else:
                # Nếu là đường thẳng (không có geometry), lấy 2 đầu mút
                routes_removed_viz.append([
                    [G.nodes[u]['y'], G.nodes[u]['x']], 
                    [G.nodes[v]['y'], G.nodes[v]['x']]
                ])
            
            # Sau khi lấy tọa độ xong thì xóa cạnh khỏi đồ thị
            G.remove_edge(u, v, key)

        return {"message": f"Đã cấm đường {street_name}", "routes": routes_removed_viz}

    except Exception as e:
        print(f"Lỗi cấm đường: {e}")
        return {"error": str(e)}
    
@app.route('/reset', methods=['POST'])
def reset():
    try:
        global G
        # Khôi phục đồ thị G từ bản copy gốc (G_original)
        # Việc này sẽ hủy bỏ mọi lệnh cấm đường và thay đổi trọng số trước đó
        G = G_original.copy()
        print("Graph reset to original state.")
        return {"message": "Đã khôi phục lại đồ thị ban đầu (Xóa cấm đường/tắc đường)"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    app.run(debug=True)