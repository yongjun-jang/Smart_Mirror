/**
 * Smart Mirror - Traffic Dashboard JavaScript
 * 완성본: 택시, 버스, 지하철 및 도착 시간 기반 확률 계산 포함
 */

// ===== 1. 초기화 및 인터랙션 로직 =====
document.addEventListener("DOMContentLoaded", function () {
    // 페이지 로드 시 지하철 정보 로드 (필요 시)
    // loadDefaultSubwaySchedule(); 

    // 화면 전체에 클릭 이벤트 연결 (사용자 활동 감지 및 CV 상태 갱신용)
    document.body.addEventListener("click", sendInteraction);
});

async function sendInteraction() {
    try {
        await fetch("/api/interaction", { 
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ type: "touch", timestamp: Date.now() })
        });
    } catch (e) {
        console.error("인터랙션 전송 실패:", e);
    }
}

// ===== 2. 공통 변수 (타이머 및 캐시) =====
let searchTimeout = null;
let searchTimeout2 = null;
let busSearchTimeout = null;

let cachedPlaces = [];
let cachedPlaces2 = [];
let cachedStops = [];

// ===== 3. 택시 및 목적지 검색 (자동완성) =====
function onDestinationInput() {
    const input = document.getElementById("destInput");
    if (!input) return;
    const query = input.value.trim();
    if (searchTimeout) clearTimeout(searchTimeout);
    if (query.length < 2) { hideDropdown(); return; }

    searchTimeout = setTimeout(() => { searchPlaces(query); }, 300);
}

async function searchPlaces(query) {
    const dropdown = document.getElementById("placeDropdown");
    try {
        const response = await fetch(`/api/search_destination?q=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (data.ok && data.all_places && data.all_places.length > 0) {
            cachedPlaces = data.all_places;
            showDropdown(cachedPlaces);
        } else {
            hideDropdown();
        }
    } catch (e) {
        console.error("검색 오류:", e);
        hideDropdown();
    }
}

function showDropdown(places) {
    const dropdown = document.getElementById("placeDropdown");
    dropdown.innerHTML = "";
    places.forEach((place, index) => {
        const item = document.createElement("div");
        item.className = "dropdown-item";
        item.innerHTML = `<div class="item-name">${place.name}</div><div class="item-address">${place.address}</div>`;
        item.onclick = () => selectPlace(index);
        dropdown.appendChild(item);
    });
    dropdown.style.display = "block";
}

function hideDropdown() {
    const dropdown = document.getElementById("placeDropdown");
    if (dropdown) dropdown.style.display = "none";
}

async function selectPlace(index) {
    const place = cachedPlaces[index];
    if (!place) return;
    hideDropdown();
    document.getElementById("destInput").value = place.name;
    try {
        const response = await fetch(`/api/search_destination?q=${encodeURIComponent(place.name)}`);
        const data = await response.json();
        if (data.ok) updateTaxiInfo(place, data.taxi);
    } catch (e) { console.error("장소 선택 오류:", e); }
}

function updateTaxiInfo(place, taxi) {
    document.getElementById("currentDestName").textContent = place.name;
    const duration = document.getElementById("currentDuration");
    const fare = document.getElementById("currentFare");

    if (taxi && taxi.ok) {
        duration.textContent = `${taxi.duration_min}분`;
        fare.textContent = `💰 ${taxi.taxi_fare.toLocaleString()}원`;
    } else {
        duration.textContent = "--";
        fare.textContent = "정보 없음";
    }
}

// ===== 4. 도착시간 기반 확률 계산 (Commute Probability) =====
function onDestinationInput2() {
    const input = document.getElementById("destInput2");
    const query = input.value.trim();
    if (searchTimeout2) clearTimeout(searchTimeout2);
    if (query.length < 2) { hideDropdown2(); return; }
    searchTimeout2 = setTimeout(() => { searchPlaces2(query); }, 300);
}

async function searchPlaces2(query) {
    const dropdown = document.getElementById("placeDropdown2"); // ID 확인 필수
    try {
        const response = await fetch(`/api/search_destination?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        if (data.ok && data.all_places && data.all_places.length > 0) {
            cachedPlaces2 = data.all_places;
            showDropdown2(cachedPlaces2); // 이 안에서 display = "block"을 해줘야 함
        } else {
            hideDropdown2();
        }
    } catch (e) { 
        console.error("확률용 목적지 검색 오류:", e); 
        hideDropdown2();
    }
}

function showDropdown2(places) {
    const dropdown = document.getElementById("placeDropdown2");
    if (!dropdown) return; // 요소가 없으면 중단
    
    dropdown.innerHTML = "";
    places.forEach((place, index) => {
        const item = document.createElement("div");
        item.className = "dropdown-item";
        item.innerHTML = `<div class="item-name">${place.name}</div><div class="item-address">${place.address}</div>`;
        item.onclick = () => {
            document.getElementById("destInput2").value = place.name;
            document.getElementById("destLat2").value = place.lat;
            document.getElementById("destLon2").value = place.lon;
            document.getElementById("destName2").value = place.name;
            hideDropdown2();
            
        };
        dropdown.appendChild(item);
    });
    dropdown.style.display = "block"; // 여기서 강제로 보이게 설정
}

function hideDropdown2() {
    const dropdown = document.getElementById("placeDropdown2");
    if (dropdown) dropdown.style.display = "none";
}

async function calcCommuteProb() {
    const resultEl = document.getElementById("probResult");
    const arrive = document.getElementById("arriveTime").value;
    const lat = document.getElementById("destLat2").value;
    const lon = document.getElementById("destLon2").value;

    // 1. 입력 검증
    if (!arrive || !lat) { 
        resultEl.textContent = "⚠️ 목록에서 목적지를 선택해주세요."; 
        return; 
    }
    
    resultEl.innerHTML = "⌛ 확률 계산 중...";

    try {
        const res = await fetch("/api/commute_probability", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                arrive_hhmm: arrive, 
                dest: { lat: parseFloat(lat), lon: parseFloat(lon) } 
            })
        });
        
        const data = await res.json();
        
        if (data.ok) {
            const p = data.probabilities; 
            
            // 데이터 구조(객체 혹은 숫자)에 유연하게 대응하는 헬퍼 함수
            const getVal = (val) => {
                if (val === undefined || val === null) return "--";
                // { p_on_time: 0.8 } 형태일 경우
                if (typeof val === 'object' && val.p_on_time !== undefined) {
                    return Math.round(val.p_on_time * 100) + "%";
                }
                // 0.8 형태일 경우
                return Math.round(val * 100) + "%";
            };

            const taxiStr = getVal(p.taxi);
            const busStr = getVal(p.bus);

            // 2. 화면 출력 최적화
            resultEl.innerHTML = `
                <div style="color: #4fa3f7; font-weight: bold; margin-bottom: 8px; border-bottom: 1px solid #2a3b57; padding-bottom: 5px;">
                    ${data.now || ''} → ${arrive} (${Math.round(data.time_budget_min || 0)}분 남음)
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                    <span>🚕 택시 정시 도착</span> <b>${taxiStr}</b>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span>🚌 버스 정시 도착</span> <b>${busStr}</b>
                </div>
            `;
        } else {
            resultEl.textContent = "❌ 계산 실패: " + (data.error || "알 수 없는 오류");
        }
    } catch (e) { 
        console.error("확률 계산 API 호출 실패:", e);
        resultEl.textContent = "⚠️ 연결 실패 (네트워크 확인)"; 
    }
}
async function confirmDestination2() {
    const lat = document.getElementById("destLat2")?.value;
    const lon = document.getElementById("destLon2")?.value;
    const name = document.getElementById("destName2")?.value;

    if (!lat || !lon) {
        alert("목적지를 목록에서 먼저 선택하세요.");
        return;
    }

    try {
        await fetch("/api/set_destination", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                lat: parseFloat(lat),
                lon: parseFloat(lon),
                name: name
            })
        });
        window.location.href = "/traffic";
        // ✅ 세션 저장 후 페이지 새로고침 → 택시 카드가 즉시 바뀜
        
    } catch (e) {
        console.error("목적지 저장 실패:", e);
        alert("목적지 저장 실패. 콘솔/서버 로그 확인!");
    }
}


// ===== 5. 버스 정류장 기능 (TAGO API) =====
function onBusStopInput() {
    const input = document.getElementById("busStopInput");
    if (!input) return;
    const query = input.value.trim();
    if (busSearchTimeout) clearTimeout(busSearchTimeout);
    if (query.length < 1) { hideBusDropdown(); return; }

    busSearchTimeout = setTimeout(() => { searchBusStops(query); }, 300);
}

async function searchBusStops(query) {
    try {
        const response = await fetch(`/api/search_bus_stop?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        if (data.ok && data.all_stops) {
            cachedStops = data.all_stops;
            showBusDropdown(cachedStops);
        }
    } catch (e) { console.error("버스 검색 오류:", e); }
}

function showBusDropdown(stops) {
    const dropdown = document.getElementById("busStopDropdown");
    dropdown.innerHTML = "";
    stops.forEach((stop, index) => {
        const item = document.createElement("div");
        item.className = "dropdown-item";
        item.innerHTML = `<div class="item-name">${stop.nodeNm} <span style="font-size:12px; opacity:0.5;">#${stop.nodeNo || ''}</span></div>`;
        item.onclick = () => selectBusStop(index);
        dropdown.appendChild(item);
    });
    dropdown.style.display = "block";
}

function hideBusDropdown() {
    const dropdown = document.getElementById("busStopDropdown");
    if (dropdown) dropdown.style.display = "none";
}

async function selectBusStop(index) {
    const stop = cachedStops[index];
    if (!stop) return;
    hideBusDropdown();
    try {
        const response = await fetch(`/api/search_bus_stop?nodeId=${stop.nodeId}&nodeNm=${stop.nodeNm}`);
        const data = await response.json();
        if (data.ok) updateBusInfo(stop, data);
    } catch (e) { console.error("버스 정보 업데이트 오류:", e); }
}

function updateBusInfo(stop, data) {
    document.getElementById("currentStopName").textContent = stop.nodeNm;
    document.getElementById("currentETA").textContent = data.eta_min !== null ? `${data.eta_min}분` : "--";
    const arrivals = document.getElementById("busArrivals");
    arrivals.innerHTML = "";
    data.arrivals?.forEach(a => {
        const row = document.createElement("div");
        row.className = "row";
        row.style.display = "flex";
        row.style.justifyContent = "space-between";
        row.style.padding = "5px 0";
        row.innerHTML = `<span><b style="color:#4fa3f7">${a.routeNo}</b> → ${a.endNodeNm}</span><span>${a.arrTimeMin}분</span>`;
        arrivals.appendChild(row);
    });
}

// ===== 6. 외부 클릭 시 드롭다운 닫기 =====
document.addEventListener("click", function (e) {
    if (!e.target.closest(".search-container")) {
        hideDropdown(); 
        hideBusDropdown(); 
        hideDropdown2();
    }
});