import asyncio
import json
import logging
import io
import numpy as np
from contextlib import asynccontextmanager
from typing import Dict, List, Set, Tuple

import pandas as pd
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Fix Pickle module resolution issues when loading models generated under __main__
import __main__
from carbon_forecaster import CarbonEmissionForecaster
from outlier_ensemble_detector import EnsembleOutlierDetector, StatisticalAutoencoder
setattr(__main__, 'StatisticalAutoencoder', StatisticalAutoencoder)
setattr(__main__, 'EnsembleOutlierDetector', EnsembleOutlierDetector)

logger = logging.getLogger("uvicorn.error")

# In-memory stores
history_store: Dict[str, List[dict]] = {"S1": [], "S2": [], "S3": []}
alerts_store: List[dict] = []
queues_by_server: Dict[str, List[asyncio.Queue]] = {"S1": [], "S2": [], "S3": []}
outliers_set: Set[Tuple[str, str]] = set()

forecaster: CarbonEmissionForecaster = None
ensemble_detector: EnsembleOutlierDetector = None
sim_data: pd.DataFrame = None

def load_data():
    global sim_data, outliers_set
    
    logger.info("Loading stream data from server_fin.csv...")
    try:
        df = pd.read_csv("server_fin.csv")
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%d-%m-%Y %H:%M')
        sim_data = df.sort_values('Timestamp').reset_index(drop=True)
        sim_data['Timestamp_str'] = sim_data['Timestamp'].dt.strftime('%d-%m-%Y %H:%M')
    except Exception as e:
        logger.error(f"Failed to load server_fin.csv: {e}")
    
    try:
        out_df = pd.read_csv("server_fin_outliers.csv")
        outliers_set = set(zip(out_df['Timestamp'], out_df['Server_ID']))
    except Exception as e:
        logger.error(f"Failed to load outliers: {e}")

async def data_simulator():
    if sim_data is None: return
    logger.info("Starting streaming simulation (1 row/sec)...")
    
    for idx, row in sim_data.iterrows():
        ts_str = row['Timestamp_str']
        server_id = row['Server_ID']
        power = float(row['Power_Usage_Watts'])
        carbon = float(row.get('Carbon_Emission', (power * 5 / 60) / 1000 * 0.82))
        
        is_anomaly = (ts_str, server_id) in outliers_set
        
        data_point = {
            "Timestamp": ts_str,
            "Server_ID": server_id,
            "Power_Usage_Watts": power,
            "Carbon_Emission": carbon,
            "Anomaly_Score": row.get('anomaly_score', 0.85 if is_anomaly else 0.2),
            "Is_Anomaly": is_anomaly
        }
        
        if server_id not in history_store: history_store[server_id] = []
        history_store[server_id].append(data_point)
        if len(history_store[server_id]) > 288:
            history_store[server_id].pop(0)
            
        if is_anomaly:
            alerts_store.append(data_point)
            
        dead_queues = []
        for q in queues_by_server.get(server_id, []):
            try: q.put_nowait(data_point)
            except Exception: dead_queues.append(q)
                
        for q in dead_queues: queues_by_server[server_id].remove(q)
        await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global forecaster, ensemble_detector
    load_data()
    
    try:
        forecaster = CarbonEmissionForecaster.load_model('carbon_models/unified_sarima.pkl')
        forecaster.trained_servers = ["S1", "S2", "S3"]
    except Exception as e:
        logger.warning(f"Could not load forecaster ({e})")
        
    try:
        ensemble_detector = EnsembleOutlierDetector.load('ensemble_model.pkl')
    except Exception as e:
        logger.warning(f"Could not load ensemble detector ({e})")
        
    sim_task = asyncio.create_task(data_simulator())
    yield
    sim_task.cancel()

app = FastAPI(title="KINETIC_INTEL Backend API", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root(): return FileResponse("static/index.html")

class EmailPayload(BaseModel):
    server_id: str
    timestamp: str
    power: float
    anomaly_score: float

@app.post("/dispatch_email")
async def dispatch_email(payload: EmailPayload):
    logger.warning(f"📧 EMAIL SENT IN MOCK MODE")
    logger.warning(f"To: 2023ci_shailshreesinha_b@nie.ac.in")
    logger.warning(f"Subject: 🚨 CRITICAL: Anomaly Detected on {payload.server_id}")
    logger.warning(f"Body: Anomaly Score {payload.anomaly_score} recorded at {payload.timestamp}. Power usage was {payload.power}W.")
    return {"status": "success"}

@app.get("/stream/{server_id}")
async def stream_server_data(server_id: str, request: Request):
    if server_id not in queues_by_server: queues_by_server[server_id] = []
    q = asyncio.Queue()
    queues_by_server[server_id].append(q)
    
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected(): break
                data = await q.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            if q in queues_by_server.get(server_id, []):
                queues_by_server[server_id].remove(q)
                
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/history/{server_id}")
async def get_history(server_id: str, span: str = "1h"):
    if server_id not in history_store: return {"server_id": server_id, "count": 0, "ready": False, "data": []}
    limit = 12 if span == "1h" else 288
    data = history_store[server_id][-limit:]
    return {"server_id": server_id, "count": len(data), "ready": len(history_store[server_id]) >= 12, "data": data}

@app.get("/alerts")
async def get_alerts(): return alerts_store[::-1][:100]

@app.get("/forecast/{server_id}")
async def get_forecast(server_id: str, steps: int = 24):
    if forecaster is None or not forecaster.is_fitted: raise HTTPException(status_code=503, detail="Forecaster model missing")
    try:
        df_forecast = forecaster.forecast(server_id, steps=steps)
        return df_forecast.to_dict(orient="records")
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload_csv")
async def upload_csv(file: UploadFile = File(...), append: bool = Form(False)):
    if ensemble_detector is None: raise HTTPException(status_code=503, detail="Model missing")
    contents = await file.read()
    
    try:
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid CSV")
        
    col_map = {}
    for c in df.columns:
        cl = str(c).strip().lower().replace(" ", "_")
        if "timestamp" in cl or "time" in cl: col_map[c] = "Timestamp"
        elif "server" in cl: col_map[c] = "Server_ID"
        elif "power" in cl or "watt" in cl: col_map[c] = "Power_Usage_Watts"
    df = df.rename(columns=col_map)
        
    for col in ['Timestamp', 'Server_ID', 'Power_Usage_Watts']:
        if col not in df.columns: raise HTTPException(status_code=400, detail=f"Missing recognizable column for {col}. Found: {list(df.columns)}")
            
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%d-%m-%Y %H:%M', errors='coerce')
    df = df.dropna(subset=['Timestamp']).sort_values(['Server_ID', 'Timestamp'])
    
    results = []
    
    for server_id in df['Server_ID'].unique():
        server_rows = df[df['Server_ID'] == server_id].copy()
        
        hist_powers = [r['Power_Usage_Watts'] for r in history_store.get(server_id, [])]
        
        # Vectorized Rolling Window calculation
        all_powers_series = pd.Series(hist_powers + server_rows['Power_Usage_Watts'].tolist())
        r_mean_full = all_powers_series.rolling(window=12, min_periods=12).mean()
        r_std_full = all_powers_series.rolling(window=12, min_periods=12).std().fillna(0.0)
        
        # Trim back to the uploaded data bounds
        r_mean_vals = r_mean_full.iloc[len(hist_powers):].values
        r_std_vals = r_std_full.iloc[len(hist_powers):].values
        
        server_rows['hour'] = server_rows['Timestamp'].dt.hour
        server_rows['day'] = server_rows['Timestamp'].dt.day
        server_rows['weekday'] = server_rows['Timestamp'].dt.weekday
        server_rows['Rolling_Mean'] = r_mean_vals
        server_rows['Rolling_Std'] = r_std_vals
        
        # Separate rows that reached 12 history thresholds constraints
        valid_mask = server_rows['Rolling_Mean'].notna()
        valid_rows = server_rows[valid_mask]
        
        if not valid_rows.empty:
            features = valid_rows[['Power_Usage_Watts', 'hour', 'day', 'weekday', 'Rolling_Mean', 'Rolling_Std']]
            preds = ensemble_detector.predict(features, return_scores=False)
            scores = ensemble_detector.get_anomaly_scores(features)['ensemble']
            server_rows.loc[valid_mask, 'Is_Anomaly'] = (preds == -1)
            server_rows.loc[valid_mask, 'Anomaly_Score'] = scores
            server_rows.loc[valid_mask, 'Status'] = "Evaluated"
            
        # Defaults for missing validation rows
        server_rows.loc[~valid_mask, 'Is_Anomaly'] = False
        server_rows.loc[~valid_mask, 'Anomaly_Score'] = 0.0
        server_rows.loc[~valid_mask, 'Rolling_Mean'] = server_rows.loc[~valid_mask, 'Power_Usage_Watts']
        
        # Generate Building History tags
        invalid_indices = server_rows[~valid_mask].index
        for idx in invalid_indices:
            # Approx the specific accumulation x/12 via hist len offset mappings
            server_rows.at[idx, 'Status'] = f"Building History"
        
        # Extract vectorized metrics back to sequential dictionaries
        server_results = []
        for _, r in server_rows.iterrows():
            server_results.append({
                'Timestamp': r['Timestamp'].strftime('%d-%m-%Y %H:%M'),
                'Server_ID': server_id,
                'Power_Usage_Watts': r['Power_Usage_Watts'],
                'Rolling_Mean': float(r['Rolling_Mean']),
                'Is_Anomaly': bool(r['Is_Anomaly']),
                'Anomaly_Score': float(r['Anomaly_Score']),
                'Status': str(r['Status'])
            })
            
        results.extend(server_results)
        
        if append:
            if server_id not in history_store: history_store[server_id] = []
            if server_id not in queues_by_server: queues_by_server[server_id] = []
            
            forecaster_batch = []
            for r in server_results:
                carbon = (r['Power_Usage_Watts'] * 5 / 60) / 1000 * 0.82
                history_store[server_id].append({"Timestamp": r['Timestamp'], "Server_ID": server_id, "Power_Usage_Watts": r['Power_Usage_Watts'], "Carbon_Emission": carbon, "Is_Anomaly": r['Is_Anomaly']})
                forecaster_batch.append({"Timestamp": pd.to_datetime(r['Timestamp'], format='%d-%m-%Y %H:%M'), "Server_ID": server_id, "Carbon_Emission": carbon})
                if len(history_store[server_id]) > 288: history_store[server_id].pop(0)
            
            if forecaster and forecaster_batch:
                new_f_df = pd.DataFrame(forecaster_batch)
                new_f_df['hour'] = new_f_df['Timestamp'].dt.hour
                new_f_df['weekday'] = new_f_df['Timestamp'].dt.weekday
                forecaster.data = pd.concat([forecaster.data, new_f_df]).sort_values(['Server_ID', 'Timestamp']).reset_index(drop=True)
                if server_id not in forecaster.servers:
                    forecaster.servers.append(server_id)
                    forecaster.servers.sort()

    return {"results": results, "appended": append}
