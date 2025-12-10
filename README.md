# Route Master A* - Hệ Thống Dẫn Đường Thông Minh

> Ứng dụng mô phỏng hệ thống tìm đường và giám sát giao thông trong khu vực **Quận Thanh Xuân, Hà Nội**
Dự án sử dụng thuật toán A* và Dijkstra trên dữ liệu thực tế từ OpenStreetMap.

![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)
![Leaflet](https://img.shields.io/badge/Leaflet-1.9-orange.svg)
![Algorithm](https://img.shields.io/badge/Algorithm-A*-red.svg)

## Giới Thiệu

Đây là bài tập lớn môn học nhập môn trí tuệ nhân tạo. 
Khác với Google Maps, ứng dụng này cho phép **người quản trị (Admin)** can thiệp vào bản đồ để mô phỏng các tình huống thực tế như tắc đường hoặc cấm đường, từ đó thuật toán sẽ tự động tính toán lộ trình thay thế.

### Tính Năng Nổi Bật

#### 1. Tìm Đường Thông Minh (User Mode)
- **Đa phương thức nhập liệu:**
  - Click trực tiếp 2 điểm (A -> B) trên bản đồ.
  - Nhập địa chỉ cụ thể (Sử dụng API Geocoding).
- **Thuật toán linh hoạt:**
  -  **Nhanh nhất (A*):** Tối ưu theo thời gian di chuyển.
  -  **Ngắn nhất (Dijkstra):** Tối ưu theo khoảng cách địa lý.
- **Đa phương tiện:** Hỗ trợ Ô tô 🚗, Xe máy 🛵, Xe đạp 🚲, và Đi bộ 🚶 (Tự động điều chỉnh vận tốc và lộ trình phù hợp).

#### 2. Quản Lý Giao Thông (Admin Mode)
- ** Cấm đường:** Chặn một đoạn đường bất kỳ (Mô phỏng đường đang thi công, cấm đi lại). Thuật toán sẽ buộc phải tìm đường vòng.
- ** Báo tắc đường:** Tăng trọng số (weight) cho một tuyến đường cụ thể. Thuật toán A* sẽ cân nhắc tránh đường này nếu quá tắc.

---

## 🛠️ Công Nghệ Sử Dụng

### Backend (Python)
- **Flask:** Web Framework chính.
- **OSMnx:** Tải và xử lý dữ liệu bản đồ từ OpenStreetMap.
- **NetworkX:** Xây dựng đồ thị và thực thi thuật toán tìm đường (Shortest Path & A*).

### Frontend
- **Leaflet.js:** Hiển thị bản đồ tương tác.
- **HTML5 / CSS3:** Giao diện người dùng responsive.

---

## ⚙️ Cài Đặt & Chạy Ứng Dụng

### 1. Yêu cầu hệ thống
- Python 3.8 trở lên.
- Kết nối Internet ổn định (để tải dữ liệu bản đồ lần đầu).

### 2. Các bước cài đặt

**Bước 1:** Clone repository về máy:
```bash
git clone [https://github.com/DuySakura/Route-findingApp.git](https://github.com/DuySakura/Route-findingApp.git)
cd Route-findingApp