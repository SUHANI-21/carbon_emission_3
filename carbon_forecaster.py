import os
import gc
import warnings
import pandas as pd
import numpy as np
import joblib
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings('ignore')

class CarbonEmissionForecaster:
    """Unified Cluster Carbon Emission Forecaster"""
    
    def __init__(self, data_path='server_fin.csv'):
        print(f"Loading historical data from {data_path}...")
        self.data = pd.read_csv(data_path)
        self.data['Timestamp'] = pd.to_datetime(self.data['Timestamp'], format='%d-%m-%Y %H:%M', errors='coerce')
        self.data = self.data.sort_values(['Server_ID', 'Timestamp']).reset_index(drop=True)
        self.servers = sorted(self.data['Server_ID'].unique())
        self.trained_servers = self.servers[:]
        
        self.model = None
        self.fitted_model = None
        self.is_fitted = False
        
    def _prepare_exog(self, df):
        """Prepare exogenous features: dummy vars for strictly trained dimensions"""
        exog = pd.DataFrame(index=df.index)
        
        trained_srvs = getattr(self, 'trained_servers', self.servers)
        for server in trained_srvs:
            exog[f'is_{server}'] = (df['Server_ID'] == server).astype(float)
            
        if 'hour' in df.columns: exog['hour'] = df['hour'].astype(float)
        else: exog['hour'] = df['Timestamp'].dt.hour.astype(float)
            
        if 'weekday' in df.columns: exog['weekday'] = df['weekday'].astype(float)
        else: exog['weekday'] = df['Timestamp'].dt.weekday.astype(float)
            
        return exog.astype(float)

    def fit(self):
        print(f"Fitting Unified SARIMAX on {len(self.servers)} servers...")
        
        self.data['hour'] = self.data['Timestamp'].dt.hour
        self.data['weekday'] = self.data['Timestamp'].dt.weekday
        
        y = self.data['Carbon_Emission']
        exog = self._prepare_exog(self.data)
        
        # Free memory before matrix operation
        gc.collect()
        
        self.model = SARIMAX(
            endog=y,
            exog=exog,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 1, 12),
            enforce_stationarity=False,
            enforce_invertibility=False
        )
        self.fitted_model = self.model.fit(disp=False)
        self.is_fitted = True
        print("[OK] Unified Model training sequence complete.")

    def forecast(self, server_id, steps=24):
        """Forecast X steps into the future for a specific server."""
        if not self.is_fitted:
            raise ValueError("Model is not fitted. Cannot predict.")
            
        # Extract last timestamp for this specific server
        server_df = self.data[self.data['Server_ID'] == server_id]
        if len(server_df) == 0:
            raise ValueError(f"Server {server_id} has no historical data to offset from.")
            
        last_time = server_df['Timestamp'].iloc[-1]
        freq_str = '5min' 
        
        # Generate future time index
        future_dates = pd.date_range(start=last_time, periods=steps + 1, freq=freq_str)[1:]
        
        future_exog_df = pd.DataFrame({'Timestamp': future_dates, 'Server_ID': server_id})
        future_exog = self._prepare_exog(future_exog_df)
        
        forecast_res = self.fitted_model.get_forecast(steps=steps, exog=future_exog)
        mean_forecast = forecast_res.predicted_mean
        conf_int = forecast_res.conf_int(alpha=0.20) # 80% CI
        
        results = pd.DataFrame({
            'timestamp': future_dates.strftime('%d-%m-%Y %H:%M'),
            'forecast': np.maximum(0.001, mean_forecast.values), # Cap lower at near 0 to avoid neg carbon predictions gracefully
            'lower_ci': np.maximum(0.0, conf_int.iloc[:, 0].values),
            'upper_ci': conf_int.iloc[:, 1].values
        })
        
        return results

    def save_model(self, model_path='carbon_models/unified_sarima.pkl'):
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        joblib.dump(self, model_path)
        print(f"[OK] Saved unified model to {model_path}")

    @classmethod
    def load_model(cls, model_path='carbon_models/unified_sarima.pkl'):
        model = joblib.load(model_path)
        print(f"[OK] Loaded unified model from {model_path}")
        return model
