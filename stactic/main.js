let map = L.map("map").setView([21.0362,105.8342],15);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(map);

let startMarker=null,endMarker=null,routeLayer=null;

fetch("/boundary")
.then(r=>r.json())
.then(c=>L.polygon(c,{color:"blue"}).addTo(map));

map.on("click",e=>{
if(!startMarker) startMarker=L.marker(e.latlng).addTo(map);
else if(!endMarker) endMarker=L.marker(e.latlng).addTo(map);
});

function drawRoute(coords){
if(routeLayer) map.removeLayer(routeLayer);
routeLayer=L.polyline(coords,{color:"red",weight:4}).addTo(map);
map.fitBounds(routeLayer.getBounds());
}

function displayTime(data){
let min=Math.floor(data.time/60),sec=Math.round(data.time%60);
document.getElementById("travelTime").innerText=`Thời gian: ${min} phút ${sec} giây (${data.mode})`;
}

// CLICK FIND
document.getElementById("findRouteBtn").onclick=()=>{
if(!startMarker||!endMarker) return alert("Chọn đủ điểm!");
fetch("/find-route-by-click",{
method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({
point1:startMarker.getLatLng(),
point2:endMarker.getLatLng(),
vehicle:document.getElementById("vehicleSelect").value,
mode:document.getElementById("modeSelect").value
})
}).then(r=>r.json()).then(data=>{
if(data.error) return alert(data.error);
drawRoute(data.coords);
displayTime(data);
});
};

// TEXT FIND
document.getElementById("findByTextBtn").onclick=()=>{
let body={
place1:document.getElementById("startPlace").value,
place2:document.getElementById("endPlace").value,
vehicle:document.getElementById("vehicleSelect").value,
mode:document.getElementById("modeSelect").value
};
fetch("/find-route-by-text",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
.then(r=>r.json()).then(data=>{
if(data.error) return alert(data.error);
drawRoute(data.coords);
displayTime(data);
});
};

// BAN / CHANGE / RESET
document.getElementById("banRouteBtn").onclick=()=>{let s=prompt("Đường:");if(!s) return;fetch("/ban-route",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({street:s})}).then(r=>r.json()).then(a=>alert(a.message));};
document.getElementById("changeWeightBtn").onclick=()=>{let s=prompt("Đường:"),l=prompt("Mức tắc 0-3:");if(!s||isNaN(l)) return;fetch("/change-weight",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({street:s,level:l})}).then(r=>r.json()).then(a=>alert(a.message));};
document.getElementById("resetBtn").onclick=()=>{fetch("/reset",{method:"POST"}).then(r=>r.json()).then(a=>alert(a.message));};
document.getElementById("adminBtn").onclick=()=>document.getElementById("sidebar").classList.toggle("appear");
