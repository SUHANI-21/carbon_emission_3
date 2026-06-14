"""
Smart prediction: Auto-fetch historical data from dataset if needed
- If user sends < 12 rows: fetch last 12 from training dataset for that server
- If user sends >= 12 rows: use their data for rolling stats
"""

import pandas as pd
import numpy as np
from datetime import datetime
from outlier_ensemble_detector import EnsembleOutlierDetector


class SmartPredictor:
    """
    Intelligent predictor that auto-handles historical data
    """
    
    def __init__(self, original_data_path='server_fin.csv', model_path='outlier_detector_model.pkl'):
        """
        Initialize predictor with access to original data
        
        Parameters:
        -----------
        original_data_path : str
            Path to original training CSV
        model_path : str
            Path to trained model
        """
        print("Loading original dataset...")
        self.original_data = pd.read_csv(original_data_path)
        print(f"✓ Loaded {len(self.original_data)} records from {original_data_path}")
        
        print("Loading trained model...")
        self.detector = EnsembleOutlierDetector.load(model_path)
        print(f"✓ Model loaded")
        
        self.window_size = 12  # 1 hour at 5-min intervals
    
    def get_last_history_from_dataset(self, server_id, count=12):
        """
        Fetch last N records for a server from original dataset
        
        Parameters:
        -----------
        server_id : str
            Server ID (e.g., 'S1', 'S2')
        count : int
            Number of historical records
        
        Returns:
        --------
        pd.DataFrame : Historical power usage data
        """
        server_data = self.original_data[self.original_data['Server_ID'] == server_id]
        if len(server_data) == 0:
            print(f"⚠ Server {server_id} not found in dataset!")
            return pd.DataFrame()
        
        history = server_data[['Power_Usage_Watts']].tail(count).reset_index(drop=True)
        print(f"  ✓ Fetched {len(history)} historical records for {server_id} from dataset")
        return history
    
    def calculate_rolling_stats(self, power_readings):
        """
        Calculate rolling mean and std from power readings
        
        Parameters:
        -----------
        power_readings : list or pd.Series
            Power usage values
        
        Returns:
        --------
        tuple : (rolling_mean, rolling_std)
        """
        if isinstance(power_readings, pd.DataFrame):
            power_readings = power_readings['Power_Usage_Watts'].tolist()
        elif isinstance(power_readings, pd.Series):
            power_readings = power_readings.tolist()
        
        rolling_mean = np.mean(power_readings)
        rolling_std = np.std(power_readings)
        return rolling_mean, rolling_std
    
    def predict(self, new_data):
        """
        Make predictions on new data with auto-history handling
        
        Parameters:
        -----------
        new_data : pd.DataFrame
            New records to predict. Must have columns:
            - 'Timestamp' (format: "DD-MM-YYYY HH:MM")
            - 'Server_ID'
            - 'Power_Usage_Watts'
        
        Returns:
        --------
        pd.DataFrame : Predictions with anomaly scores
        """
        print("\n" + "=" * 80)
        print("SMART PREDICTION WITH AUTO-HISTORY")
        print("=" * 80)
        
        results = []
        
        # Group by server to handle each server separately
        for server_id in new_data['Server_ID'].unique():
            server_data = new_data[new_data['Server_ID'] == server_id].reset_index(drop=True)
            n_new_records = len(server_data)
            
            print(f"\nServer: {server_id}")
            print(f"  New records received: {n_new_records}")
            
            # Prepare history
            if n_new_records >= self.window_size:
                # User provided enough history in their data
                print(f"  ✓ Using last {self.window_size} from user data as history")
                history = server_data[['Power_Usage_Watts']].head(self.window_size)
            else:
                # Fetch from original dataset
                n_needed = self.window_size - n_new_records
                history = self.get_last_history_from_dataset(server_id, count=n_needed)
                print(f"  → Insufficient history in user data ({n_new_records} < {self.window_size})")
                print(f"  → Fetching {n_needed} historical records from dataset for rolling stats")
            
            # Process each new record
            for idx, row in server_data.iterrows():
                timestamp_str = row['Timestamp']
                power_watts = row['Power_Usage_Watts']
                
                # Parse timestamp
                dt = datetime.strptime(timestamp_str, "%d-%m-%Y %H:%M")
                hour = dt.hour
                day = dt.day
                weekday = dt.weekday()
                
                # Calculate features
                interval_minutes = 5
                
                # Get rolling stats from history
                rolling_mean, rolling_std = self.calculate_rolling_stats(history)
                
                # Prepare feature vector (6 essential features only)
                features = pd.DataFrame([{
                    'Power_Usage_Watts': power_watts,
                    'hour': hour,
                    'day': day,
                    'weekday': weekday,
                    'Rolling_Mean': rolling_mean,
                    'Rolling_Std': rolling_std
                }])
                
                # Predict
                prediction = self.detector.predict(features, return_scores=False)
                scores = self.detector.get_anomaly_scores(features)
                
                result = {
                    'Timestamp': timestamp_str,
                    'Server_ID': server_id,
                    'Power_Usage_Watts': power_watts,
                    'Rolling_Mean': rolling_mean,
                    'Rolling_Std': rolling_std,
                    'Anomaly_Score': scores['ensemble'][0],
                    'Is_Anomaly': prediction[0] == -1
                }
                results.append(result)
                
                # Update history for next iteration (sliding window)
                history = pd.concat([
                    history.iloc[1:].reset_index(drop=True),
                    pd.DataFrame({'Power_Usage_Watts': [power_watts]})
                ], ignore_index=True)
        
        result_df = pd.DataFrame(results)
        
        # Print summary
        print("\n" + "=" * 80)
        print("PREDICTION RESULTS")
        print("=" * 80)
        print(f"\nTotal predictions: {len(result_df)}")
        print(f"Anomalies detected: {result_df['Is_Anomaly'].sum()}")
        print(f"\n{result_df.to_string()}")
        
        return result_df


# ============================================================
# EXAMPLES
# ============================================================
if __name__ == "__main__":
    predictor = SmartPredictor()
    
    # ========================================================
    # EXAMPLE 1: Single record (needs history from dataset)
    # ========================================================
    print("\n\n")
    print("█" * 80)
    print("EXAMPLE 1: User sends 1 row for Server1")
    print("█" * 80)
    
    new_data_1 = pd.DataFrame({
        'Timestamp': ['15-11-2025 15:30'],
        'Server_ID': ['S1'],
        'Power_Usage_Watts': [145]
    })
    
    print("\nInput from user:")
    print(new_data_1.to_string())
    
    result_1 = predictor.predict(new_data_1)
    
    # ========================================================
    # EXAMPLE 2: Multiple records (use sliding window)
    # ========================================================
    print("\n\n")
    print("█" * 80)
    print("EXAMPLE 2: User sends 5 rows for Server1")
    print("█" * 80)
    
    new_data_2 = pd.DataFrame({
        'Timestamp': [
            '15-11-2025 15:30',
            '15-11-2025 15:35',
            '15-11-2025 15:40',
            '15-11-2025 15:45',
            '15-11-2025 15:50'
        ],
        'Server_ID': ['S1', 'S1', 'S1', 'S1', 'S1'],
        'Power_Usage_Watts': [110, 125, 95, 150, 105]
    })
    
    print("\nInput from user:")
    print(new_data_2.to_string())
    
    result_2 = predictor.predict(new_data_2)
    
    # ========================================================
    # EXAMPLE 3: Multiple servers mixed
    # ========================================================
    print("\n\n")
    print("█" * 80)
    print("EXAMPLE 3: Same power value (120W) sent for S1, S2, S3")
    print("█" * 80)
    print("This shows how rolling stats make model server-aware")
    
    new_data_3 = pd.DataFrame({
        'Timestamp': [
            '15-11-2025 15:30',
            '15-11-2025 15:30',
            '15-11-2025 15:30'
        ],
        'Server_ID': ['S1', 'S2', 'S3'],
        'Power_Usage_Watts': [120, 120, 120]  # SAME power for all servers
    })
    
    print("\nInput from user (SAME power for all servers):")
    print(new_data_3.to_string())
    print("\n⚠ Note: Same power (120W), but different context for each server!")
    
    result_3 = predictor.predict(new_data_3)
    
    print("\n\n" + "=" * 80)
    print("HOW IT WORKS")
    print("=" * 80)
    print("""
Step 1: User sends data (1+ rows)
        └─ Server_ID, Timestamp, Power_Usage_Watts

Step 2: Check history availability
        ├─ If user sent >= 12 rows: Use their data
        └─ If user sent < 12 rows: Fetch from dataset

Step 3: Calculate rolling statistics
        ├─ Rolling_Mean = mean of 12 power readings
        └─ Rolling_Std = std dev of 12 power readings

Step 4: Calculate derived features
        ├─ Energy_kWh from Power
        ├─ Carbon_Emission from Energy
        └─ Hour, Day, Weekday from Timestamp

Step 5: Predict
        ├─ Pass all 8 features to model
        ├─ Get anomaly_score (0-1)
        └─ Get is_anomaly (True/False)

ADVANTAGE:
✓ No need for user to provide history
✓ Automatically uses dataset as reference
✓ Maintains temporal context
✓ Works with any number of input rows
    """)
