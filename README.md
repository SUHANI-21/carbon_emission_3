# AI-Powered Server Anomaly Detection & Carbon Emission Forecasting

An intelligent infrastructure monitoring system that combines **ensemble anomaly detection** with **SARIMA-based carbon emission forecasting** for server environments.

## Features

* Ensemble anomaly detection using:

  * Isolation Forest
  * One-Class SVM
  * PCA-based reconstruction detector
* Rolling-window temporal feature engineering
* Automatic historical context handling
* Per-server SARIMA forecasting
* Confidence interval prediction
* Lightweight deployment with compressed models
* Fallback forecasting for model convergence failures

---

## System Architecture

```text
Server Power Data
        ↓
Feature Engineering
        ↓
Ensemble Anomaly Detection
        ↓
Anomaly Score + Alert

Historical Carbon Data
        ↓
SARIMA Forecasting
        ↓
Future Carbon Emission Predictions
```

---

## Dataset

* Servers: `S1`, `S2`, `S3`
* Total records: `25,920`
* Sampling interval: `5 minutes`

### Features Used

* `Power_Usage_Watts`
* `hour`
* `day`
* `weekday`
* `Rolling_Mean`
* `Rolling_Std`

---

## Models

### 1. Ensemble Anomaly Detection

Combines:

* Isolation Forest
* SGD One-Class SVM
* PCA reconstruction error detector

Final prediction uses **majority voting (2/3 agreement)**.

### 2. Carbon Emission Forecasting

Per-server SARIMA models:

Captures:

* trends
* seasonality
* temporal dependencies

---

## Technologies Used

* Python
* pandas
* NumPy
* scikit-learn
* statsmodels
* joblib
* lz4

---

## Future Improvements

* Real-time streaming pipeline
* LSTM/Transformer forecasting
* Interactive monitoring dashboard
* Online learning support
* Alert notification system

---

