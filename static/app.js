Chart.defaults.color = '#a1a1aa';
Chart.defaults.font.family = "'JetBrains Mono', monospace";

const servers = ['S1', 'S2', 'S3'];
const MAX_LIVE_POINTS = 60; 

const liveCharts = {};
const analysisCharts = {};
const forecastCharts = {};
const gauges = {};
let isStreamConnected = false;

function initTabs() {
    const navs = document.querySelectorAll('.nav-btn');
    const contents = document.querySelectorAll('.tab-content');
    
    navs.forEach(nav => {
        nav.addEventListener('click', () => {
            navs.forEach(n => n.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));
            
            nav.classList.add('active');
            const target = document.getElementById(nav.dataset.target);
            target.classList.add('active');

            setTimeout(() => {
                servers.forEach(s => {
                    if (gauges[s]) gauges[s].resize();
                    if (liveCharts[s]) liveCharts[s].resize();
                    if (analysisCharts[s]) analysisCharts[s].resize();
                    if (forecastCharts[s]) forecastCharts[s].resize();
                });
            }, 10);
        });
    });
}

function initGauges() {
    servers.forEach(s => {
        const dom = document.getElementById(`gauge-${s}`);
        if (!dom) return;
        const myChart = echarts.init(dom, 'dark', { renderer: 'canvas' });
        
        const option = {
            backgroundColor: 'transparent',
            series: [{
                type: 'gauge', min: 0.005, max: 0.015, splitNumber: 4,
                axisLine: { lineStyle: { width: 14, color: [[0.3, '#10b981'], [0.7, '#f59e0b'], [1, '#ef4444']] } },
                pointer: { itemStyle: { color: 'auto' }, width: 6, length: '75%' },
                axisTick: { distance: -18, length: 8, lineStyle: { color: '#fff', width: 1 } },
                splitLine: { distance: -24, length: 14, lineStyle: { color: '#fff', width: 2 } },
                axisLabel: { color: 'inherit', distance: 30, fontSize: 10, formatter: v => v.toFixed(3) },
                detail: { valueAnimation: true, formatter: '{value}', color: 'inherit', fontSize: 26, offsetCenter: [0, '60%'] },
                data: [{ value: 0.0, name: 'KG CO2' }],
                title: { offsetCenter: [0, '85%'], fontSize: 11, color: '#a1a1aa' }
            }]
        };
        myChart.setOption(option);
        gauges[s] = myChart;
    });
}

function updateGauge(server, carbon) {
    if (!gauges[server]) return;
    gauges[server].setOption({ series: [{ data: [{ value: parseFloat(carbon).toFixed(4) }] }] });
}

function initCharts() {
    const tooltipConfig = {
        callbacks: {
            label: function(context) {
                const ds = context.dataset;
                const power = context.parsed.y;
                let label = `${ds.label}: ${power.toFixed(1)}W`;
                
                if (ds.data.length > 0) {
                    const idx = context.dataIndex;
                    const startIdx = Math.max(0, idx - 12);
                    const slice = ds.data.slice(startIdx, idx + 1);
                    const mean = slice.reduce((a, b) => a + b, 0) / slice.length;
                    const deviation = power - mean;
                    const percent = mean > 0 ? (deviation / mean) * 100 : 0;
                    
                    if (Math.abs(deviation) > 0.1) {
                        const sign = deviation > 0 ? '+' : '';
                        label += `  (Dev: ${sign}${deviation.toFixed(1)}W, ${sign}${percent.toFixed(1)}%)`;
                    }

                    const isAnomaly = Array.isArray(ds.pointBackgroundColor) && ds.pointBackgroundColor[idx] === '#ef4444';
                    if (isAnomaly) {
                        label += deviation > 0 ? ' [HIGH SPIKE]' : ' [LOW DIP]';
                    }
                }
                return label;
            }
        }
    };

    servers.forEach(s => {
        const ctxL = document.getElementById(`live-${s}`);
        if(ctxL) {
            liveCharts[s] = new Chart(ctxL.getContext('2d'), {
                type: 'line', data: { labels: [], datasets: [{ label: 'Power (W)', data: [], borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.15)', borderWidth: 2, fill: true, tension: 0.3, pointBackgroundColor: [], pointRadius: [], pointBorderColor: [] }] },
                options: { responsive: true, maintainAspectRatio: false, animation: { duration: 0 }, scales: { x: { display: false }, y: { suggestedMin: 50, suggestedMax: 200, grid: { color: 'rgba(255,255,255,0.05)' } } }, plugins: { legend: { display: false }, tooltip: tooltipConfig } }
            });
        }

        const ctxA = document.getElementById(`analysis-${s}`);
        if(ctxA) {
            analysisCharts[s] = new Chart(ctxA.getContext('2d'), {
                type: 'line', data: { labels: [], datasets: [] },
                options: { responsive: true, maintainAspectRatio: false, scales: { x: { ticks: { maxTicksLimit: 12 } }, y: { grid: { color: 'rgba(255,255,255,0.05)' } } }, plugins: { title: { display: true, text: `Server ${s}`, color: '#fff' }, tooltip: tooltipConfig } }
            });
        }

        const ctxF = document.getElementById(`forecast-${s}`);
        if(ctxF) {
            forecastCharts[s] = new Chart(ctxF.getContext('2d'), {
                type: 'line', data: { labels: [], datasets: [] },
                options: { responsive: true, maintainAspectRatio: false, scales: { y: { grid: { color: 'rgba(255,255,255,0.05)' }, title: {display: true, text: 'CO2 Emission (kg)'} } }, plugins: { title: { display: true, text: `Server ${s} Forward Vector`, color: '#fff' } } }
            });
        }
    });
}

function showToast(anomalyMsg) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast flex flex-col gap-1';
    toast.innerHTML = `
        <div class="text-sm border-b border-red-500 pb-1 mb-1 shadow-sm"><span class="font-bold material-symbols-outlined text-sm align-middle">gpp_bad</span> ${anomalyMsg}</div>
        <div class="text-xs text-red-200 mt-1 font-mono break-all leading-tight">Mock Email Dispatched: 2023ci_shailshreesinha_b@nie.ac.in</div>
    `;
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 400); }, 5000);
}

function triggerEmail(data) {
    fetch('/dispatch_email', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ server_id: data.Server_ID, timestamp: data.Timestamp, power: data.Power_Usage_Watts, anomaly_score: data.Anomaly_Score }) }).catch(console.error);
}

function connectStreams() {
    if (isStreamConnected) return;
    isStreamConnected = true;

    servers.forEach(s => {
        const es = new EventSource(`/stream/${s}`);
        es.onmessage = (event) => {
            const data = JSON.parse(event.data);
            updateGauge(s, data.Carbon_Emission);
            
            const chart = liveCharts[s];
            if(!chart) return;
            
            chart.data.labels.push(data.Timestamp.split(' ')[1]);
            chart.data.datasets[0].data.push(data.Power_Usage_Watts);
            
            if (data.Is_Anomaly) {
                chart.data.datasets[0].pointBackgroundColor.push('#ef4444');
                chart.data.datasets[0].pointBorderColor.push('#ef4444');
                chart.data.datasets[0].pointRadius.push(6);
                showToast(`Anomaly parsed on ${s} [${data.Power_Usage_Watts}W]`);
                triggerEmail(data);
                if (document.getElementById('tab-logs').classList.contains('active')) updateAlertsTable();
            } else {
                chart.data.datasets[0].pointBackgroundColor.push('#10b981');
                chart.data.datasets[0].pointBorderColor.push('transparent');
                chart.data.datasets[0].pointRadius.push(0);
            }
            
            if (chart.data.labels.length > MAX_LIVE_POINTS) {
                chart.data.labels.shift();
                chart.data.datasets[0].data.shift();
                chart.data.datasets[0].pointBackgroundColor.shift();
                chart.data.datasets[0].pointBorderColor.shift();
                chart.data.datasets[0].pointRadius.shift();
            }
            chart.update();
        };
    });
}

function toggleAccordion(id) {
    const detailRow = document.getElementById(`detail-${id}`);
    if (detailRow.classList.contains('open')) detailRow.classList.remove('open');
    else {
        document.querySelectorAll('.alert-detail').forEach(d => d.classList.remove('open'));
        detailRow.classList.add('open');
    }
}

async function updateAlertsTable() {
    try {
        const res = await fetch('/alerts');
        const alerts = await res.json();
        const tbody = document.getElementById('alerts-tbody');
        tbody.innerHTML = '';
        alerts.forEach((a, index) => {
            tbody.innerHTML += `
                <tr class="hover:bg-zinc-800/80 transition-colors alert-row w-full cursor-pointer border-l-2 border-transparent hover:border-red-500" onclick="toggleAccordion(${index})">
                    <td class="px-6 py-4 w-1/4"><span class="material-symbols-outlined text-sm align-middle text-zinc-500 mr-2">expand_more</span>${a.Timestamp}</td>
                    <td class="px-6 py-4 font-bold text-zinc-200 w-1/4">${a.Server_ID}</td>
                    <td class="px-6 py-4 text-red-400 w-1/4">${a.Power_Usage_Watts.toFixed(1)}W</td>
                    <td class="px-6 py-4 text-warning font-bold text-right w-1/4">${a.Anomaly_Score.toFixed(3)}</td>
                </tr>
                <tr id="detail-${index}" class="alert-detail w-full">
                    <td colspan="4" class="px-8 py-6 m-0 border-l-2 border-red-500">
                        <div class="flex flex-col gap-2">
                            <span class="text-white font-bold mb-2">Automated Dispatch Report</span>
                            <span class="text-zinc-400 text-xs uppercase">Target Route:</span>
                            <span class="font-mono text-sm text-blue-300">2023ci_shailshreesinha_b@nie.ac.in</span>
                            <span class="text-zinc-400 text-xs uppercase mt-2">Payload Trace:</span>
                            <pre class="bg-black p-3 rounded text-zinc-300 text-xs font-mono overflow-x-auto shadow-inner border border-zinc-900">${JSON.stringify({ "Status": "Mock Email Injected", "Action": "POST /dispatch_email", "Ensemble_Trigger": true, "Power_Divergence": a.Power_Usage_Watts + "W" }, null, 2)}</pre>
                        </div>
                    </td>
                </tr>
            `;
        });
    } catch {}
}

async function loadHistory(span) {
    for (const s of servers) {
        if(!analysisCharts[s]) continue;
        try {
            const res = await fetch(`/history/${s}?span=${span}`);
            const json = await res.json();
            
            const chart = analysisCharts[s];
            chart.data.labels = json.data.map(d => d.Timestamp.split(' ')[1]);
            
            const powerData = json.data.map(d => d.Power_Usage_Watts);
            const anomaliesData = json.data.filter(d => d.Is_Anomaly);
            
            // Generate Interactive Dynamic Analysis
            if (powerData.length > 0) {
                const avg = powerData.reduce((a, b) => a + b, 0) / powerData.length;
                const anomPercent = (anomaliesData.length / powerData.length) * 100;
                
                const avgEl = document.getElementById(`stat-${s.toLowerCase()}-avg`);
                const anomEl = document.getElementById(`stat-${s.toLowerCase()}-anoms`);
                if (avgEl) avgEl.innerText = `${avg.toFixed(1)} W`;
                if (anomEl) anomEl.innerText = `${anomPercent.toFixed(1)} %`;
            }
            
            chart.data.datasets = [{
                label: 'Historical Power Vol',
                data: powerData,
                borderColor: '#3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.15)',
                borderWidth: 2, fill: true, tension: 0.1,
                pointBackgroundColor: json.data.map(d => d.Is_Anomaly ? '#ef4444' : '#3b82f6'),
                pointRadius: json.data.map(d => d.Is_Anomaly ? 5 : 0),
            }];
            chart.update();
        } catch(e) {}
    }
}

async function loadForecast(hours) {
    const steps = hours * 12;
    for (const s of servers) {
        if(!forecastCharts[s]) continue;
        try {
            const res = await fetch(`/forecast/${s}?steps=${steps}`);
            const forecast = await res.json();
            
            const maxVal = Math.max(...forecast.map(f => f.forecast));
            const peakEl = document.getElementById(`fc-${s.toLowerCase()}-peak`);
            if (peakEl && isFinite(maxVal)) peakEl.innerText = `${maxVal.toFixed(4)} kg`;
            
            const chart = forecastCharts[s];
            chart.data.labels = forecast.map((_, i) => `+${(i+1)*5}m`);
            
            chart.data.datasets = [
                {
                    label: 'Predicted CO2 (kg)',
                    data: forecast.map(d => d.forecast),
                    borderColor: '#f59e0b', backgroundColor: 'transparent',
                    borderWidth: 3, tension: 0.4
                },
                {
                    label: '80% Upper CI',
                    data: forecast.map(d => d.upper_ci),
                    borderColor: 'rgba(245, 158, 11, 0.4)', backgroundColor: 'transparent',
                    borderDash: [5, 5], pointRadius: 0
                },
                {
                    label: '80% Lower CI',
                    data: forecast.map(d => d.lower_ci),
                    borderColor: 'rgba(245, 158, 11, 0.4)', backgroundColor: 'rgba(245, 158, 11, 0.15)',
                    borderDash: [5, 5], fill: '-1', pointRadius: 0
                }
            ];
            chart.update();
        } catch (e) { console.error(e); }
    }
}

// Sandbox Upload Logic
function initUploader() {
    const form = document.getElementById('upload-form');
    if(!form) return;
    
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById('csv-file');
        const appendCheck = document.getElementById('append-data');
        const loader = document.getElementById('upload-loader');
        const tbody = document.getElementById('sandbox-tbody');
        
        if (!fileInput.files.length) return;
        loader.style.display = 'block';
        
        const fd = new FormData();
        fd.append('file', fileInput.files[0]);
        fd.append('append', appendCheck.checked ? 'true' : 'false');
        
        try {
            const res = await fetch('/upload_csv', { method: 'POST', body: fd });
            const data = await res.json();
            
            if (data.detail) { throw new Error(data.detail); }
            
            tbody.innerHTML = '';
            
            if (data.results && data.results.length > 0) {
                data.results.forEach(r => {
                    let evalHtml = '';
                    if (r.Status.includes("Building History")) { evalHtml = `<span class="text-blue-400 bg-blue-500/20 px-2 py-1 rounded">${r.Status}</span>`; } 
                    else if (r.Is_Anomaly) { evalHtml = `<span class="text-red-400 bg-red-500/20 px-2 py-1 rounded border border-red-500/50">ANOMALY [Score: ${r.Anomaly_Score.toFixed(2)}]</span>`; }
                    else { evalHtml = `<span class="text-primary bg-primary/20 px-2 py-1 rounded">SAFE [Score: ${r.Anomaly_Score.toFixed(2)}]</span>`; }
                    
                    tbody.innerHTML += `
                        <tr class="hover:bg-zinc-800/50 transition-colors">
                            <td class="px-4 py-3"><span class="text-zinc-500">${r.Timestamp.split(' ')[1] || r.Timestamp}</span> <span class="font-bold text-white ml-2">${r.Server_ID}</span></td>
                            <td class="px-4 py-3">${r.Power_Usage_Watts.toFixed(1)}W <span class="text-zinc-600 ml-2 text-[10px]">μ=${r.Rolling_Mean.toFixed(1)}W</span></td>
                            <td class="px-4 py-3">${evalHtml}</td>
                        </tr>
                    `;
                });
            } else { tbody.innerHTML = `<tr><td colspan="3" class="text-center p-8 text-zinc-500">Could not identify any valid inference data from CSV.</td></tr>`; }
        } catch (e) { tbody.innerHTML = `<tr><td colspan="3" class="text-center p-8 text-red-500 font-bold border border-red-500/50">ERROR: ${e.message}</td></tr>`; } 
        finally { loader.style.display = 'none'; }
    });
}

document.getElementById('btn-hist-1h')?.addEventListener('click', () => loadHistory('1h'));
document.getElementById('btn-hist-24h')?.addEventListener('click', () => loadHistory('24h'));
document.getElementById('btn-forecast-1h')?.addEventListener('click', () => loadForecast(1));
document.getElementById('btn-forecast-24h')?.addEventListener('click', () => loadForecast(24));

window.onload = () => {
    initTabs(); initGauges(); initCharts(); initUploader(); connectStreams(); updateAlertsTable();
};
