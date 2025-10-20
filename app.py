from flask import Flask, render_template, request, jsonify
import osmnx as ox
import networkx as nx
import requests

app = Flask(__name__)

# --- Tạo đồ thị ---
place_name = "Ba Đình, Hà Nội, Vietnam"
G = ox.graph_from_place(place_name, network_type="drive")
G_original = G.copy()

# --- Tốc độ mặc định cho các loại đường ---
street_speed = {
    'motorway': 80, 'trunk': 70, 'primary': 60,
    'secondary': 50, 'tertiary': 40,
    'residential': 30, 'service': 20,
    'footway': 5, 'path': 5
}

# --- Hệ số tốc độ cho từng phương tiện ---
vehicle_speed_factor = {
    "car": 1.0,
    "motorbike": 0.8,
    "bicycle": 0.4,
    "foot": 0.2
}


# --- Chuẩn hóa trọng số (thời gian di chuyển) ---
def update_edge_weights(vehicle_type="car"):
    for u, v, key, data in G.edges(keys=True, data=True):
        highway = data.get("highway", "residential")
        if isinstance(highway, list):
            highway = highway[0]

        base_speed = street_speed.get(highway, 30)
        speed = base_speed * vehicle_speed_factor.get(vehicle_type, 1.0)
        data["length"] = G_original.edges[u, v, key]["length"] / speed


# --- Tìm đường đi ngắn nhất ---
def find_route(start_point, end_point, vehicle_type="car"):
    update_edge_weights(vehicle_type)
    orig = ox.distance.nearest_nodes(G, start_point["lng"], start_point["lat"])
    dest = ox.distance.nearest_nodes(G, end_point["lng"], end_point["lat"])

    if not nx.has_path(G, orig, dest):
        return {"error": "Không tìm thấy đường đi phù hợp."}

    route = nx.shortest_path(G, orig, dest, weight="length")
    coords = [[G.nodes[n]["y"], G.nodes[n]["x"]] for n in route]
    return coords


# --- Trang chính ---
@app.route("/")
def index():
    return render_template("index.html")


# --- Đường bao ---
@app.route("/boundary")
def boundary():
    gdf = ox.geocode_to_gdf(place_name)
    polygon = gdf.geometry.iloc[0]
    coords = list(polygon.exterior.coords)
    latlng = [[lat, lng] for lng, lat in coords]
    return jsonify(latlng)


# --- Tìm đường bằng click ---
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


# --- Tìm đường bằng text ---
@app.route("/find-route-by-text", methods=["POST"])
def find_route_by_text():
    try:
        data = request.get_json()
        start, end = data["place1"], data["place2"]
        vehicle = data.get("vehicle", "car")

        def get_coord(place):
            url = "https://nominatim.openstreetmap.org/search"
            params = {"q": place, "format": "json", "limit": 1}
            res = requests.get(url, params=params, headers={"User-Agent": "FindRouteApp"})
            result = res.json()
            if not result:
                return None
            return {"lat": float(result[0]["lat"]), "lng": float(result[0]["lon"])}

        start_point = get_coord(start)
        end_point = get_coord(end)
        if not start_point or not end_point:
            return {"error": "Không xác định được tọa độ điểm nhập."}

        route = find_route(start_point, end_point, vehicle)
        return jsonify(route)
    except Exception as e:
        return {"error": str(e)}


# --- Thay đổi tốc độ ---
@app.route("/change-weight", methods=["POST"])
def change_weight():
    data = request.get_json()
    street = data.get("street")
    level = float(data.get("level", 1))
    exist = False

    for u, v, key, d in G.edges(keys=True, data=True):
        if "name" not in d:
            continue
        names = d["name"] if isinstance(d["name"], list) else [d["name"]]
        if street.lower() in [n.lower() for n in names]:
            exist = True
            d["length"] *= (1 + 0.5 * level)  # tăng thời gian đi do tắc đường

    if exist:
        return {"message": f"Đã thay đổi tốc độ cho đường '{street}'."}
    return {"message": f"Không tìm thấy đường '{street}'."}


# --- Cấm đường ---
@app.route("/ban-route", methods=["POST"])
def ban_route():
    data = request.get_json()
    street = data.get("street")
    removed = []
    for u, v, key, d in list(G.edges(keys=True, data=True)):
        if "name" in d:
            names = d["name"] if isinstance(d["name"], list) else [d["name"]]
            if street.lower() in [n.lower() for n in names]:
                removed.append((u, v, key))
                G.remove_edge(u, v, key)
    if removed:
        return {"message": f"Đã cấm đường '{street}'."}
    return {"message": f"Không tìm thấy đường '{street}'."}


# --- Reset ---
@app.route("/reset", methods=["POST"])
def reset():
    global G
    G = G_original.copy()
    return {"message": "Đã khôi phục đồ thị ban đầu."}


if __name__ == "__main__":
    app.run(debug=True)
