"""
Memory-efficient Ensemble Outlier Detection Model
Combines: Isolation Forest, One-Class SVM (SGD), and Statistical Methods

"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import SGDOneClassSVM
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.decomposition import PCA
import joblib
import gc
import warnings
warnings.filterwarnings('ignore')


class StatisticalAutoencoder:
    """
    Memory-efficient statistical anomaly detector inspired by autoencoders.
    Uses PCA reconstruction error for anomaly scoring.
    """
    def __init__(self, n_components=5, contamination=0.1):
        self.n_components = n_components
        self.contamination = contamination
        self.pca = PCA(n_components=n_components, random_state=42)
        self.threshold = None
        self.is_fitted = False
        
    def fit(self, X):
        """Fit the statistical autoencoder"""
        self.pca.fit(X)
        self.reconstruction_errors = self._compute_reconstruction_error(X)
        self.threshold = np.percentile(
            self.reconstruction_errors, 
            (1 - self.contamination) * 100
        )
        self.is_fitted = True
        return self
    
    def _compute_reconstruction_error(self, X):
        """Compute reconstruction error (PCA-based)"""
        X_reduced = self.pca.transform(X)
        X_reconstructed = self.pca.inverse_transform(X_reduced)
        errors = np.sum((X - X_reconstructed) ** 2, axis=1)
        return errors
    
    def predict(self, X):
        """
        Predict anomalies. Returns -1 for anomalies, 1 for normal.
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted first")
        
        errors = self._compute_reconstruction_error(X)
        predictions = np.where(errors > self.threshold, -1, 1)
        return predictions
    
    def decision_function(self, X):
        """Get anomaly scores (reconstruction errors)"""
        return self._compute_reconstruction_error(X)


class EnsembleOutlierDetector:
    """
    Memory-efficient ensemble outlier detection combining:
    - Isolation Forest
    - SGD One-Class SVM
    - Statistical Autoencoder (PCA-based)
    """
    
    def __init__(self, contamination=0.1, batch_size=5000):
        """
        Initialize ensemble detector
        
        Parameters:
        -----------
        contamination : float, default=0.1
            Expected proportion of outliers in dataset
        batch_size : int, default=5000
            Batch size for processing large datasets
        """
        self.contamination = contamination
        self.batch_size = batch_size
        self.scalers = {}
        self.models = {
            'isolation_forest': IsolationForest(
                contamination=contamination,
                random_state=42,
                n_jobs=-1,
                max_samples='auto'
            ),
            'sgd_svm': SGDOneClassSVM(
                nu=contamination,
                random_state=42,
                max_iter=1000,
                tol=1e-3
            ),
            'statistical_ae': StatisticalAutoencoder(
                n_components=5,
                contamination=contamination
            )
        }
        self.feature_names = None
        self.is_fitted = False
        
    def _select_numeric_features(self, df):
        """Select core features needed for anomaly detection"""
        # Only select power and temporal/rolling features
        # Energy and Carbon are derived - don't add new info
        features_to_use = []
        for col in ['Power_Usage_Watts', 'hour', 'day', 'weekday', 'Rolling_Mean', 'Rolling_Std']:
            if col in df.columns:
                features_to_use.append(col)
        
        return features_to_use
    
    def _preprocess_data(self, df, fit=False):
        """
        Preprocess data: select features, handle missing values, scale
        
        Parameters:
        -----------
        df : pd.DataFrame
            Input data
        fit : bool
            Whether to fit scalers (only on training data)
        
        Returns:
        --------
        np.ndarray : Processed feature matrix
        list : Indices of rows kept (None if all rows kept)
        """
        # Select numeric features
        if self.feature_names is None:
            self.feature_names = self._select_numeric_features(df)
            print(f"[OK] Selected features: {self.feature_names}")
        
        X = df[self.feature_names].copy()
        kept_indices = None
        
        # Handle missing values: forward fill then backward fill
        X = X.ffill().bfill().fillna(X.mean())
        
        # Remove extreme outliers (obvious data issues) ONLY during fitting
        if fit:
            for col in X.columns:
                Q1 = X[col].quantile(0.01)
                Q3 = X[col].quantile(0.99)
                X = X[(X[col] >= Q1) & (X[col] <= Q3)]
            kept_indices = X.index.tolist()
        
        # Scale with RobustScaler (resistant to outliers)
        scaler_name = 'robust_scaler'
        if fit:
            self.scalers[scaler_name] = RobustScaler()
            X_scaled = self.scalers[scaler_name].fit_transform(X)
        else:
            if scaler_name not in self.scalers:
                raise ValueError("Model not fitted. Call fit() first.")
            X_scaled = self.scalers[scaler_name].transform(X)
        
        return X_scaled, kept_indices
    
    def fit(self, df):
        """
        Fit ensemble model on training data
        
        Parameters:
        -----------
        df : pd.DataFrame
            Training dataset
        """
        print("=" * 60)
        print("FITTING ENSEMBLE OUTLIER DETECTOR")
        print("=" * 60)
        
        # Preprocess
        print("\n[1/4] Preprocessing data...")
        X, _ = self._preprocess_data(df, fit=True)
        print(f"  [OK] Shape: {X.shape}")
        print(f"  [OK] Memory usage: {X.nbytes / 1024**2:.2f} MB")
        
        # Fit Isolation Forest
        print("\n[2/4] Fitting Isolation Forest...")
        self.models['isolation_forest'].fit(X)
        print("  [OK] Complete")
        gc.collect()
        
        # Fit SGD One-Class SVM (can handle large datasets efficiently)
        print("\n[3/4] Fitting SGD One-Class SVM...")
        self.models['sgd_svm'].partial_fit(X)
        print("  [OK] Complete")
        gc.collect()
        
        # Fit Statistical Autoencoder
        print("\n[4/4] Fitting Statistical Autoencoder...")
        self.models['statistical_ae'].fit(X)
        print("  [OK] Complete")
        gc.collect()
        
        self.is_fitted = True
        print("\n" + "=" * 60)
        print("[OK] ALL MODELS FITTED SUCCESSFULLY")
        print("=" * 60)
    
    def predict(self, df, return_scores=False):
        """
        Predict anomalies on new data
        
        Parameters:
        -----------
        df : pd.DataFrame
            Data to predict
        return_scores : bool, default=False
            If True, return anomaly scores for each model
        
        Returns:
        --------
        predictions : np.ndarray
            -1 for outliers, 1 for normal (majority voting)
        scores : dict (optional)
            Anomaly scores from each model
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted first. Call fit() first.")
        
        X, _ = self._preprocess_data(df, fit=False)
        
        # Get predictions from each model
        scores = {}
        
        # Isolation Forest: already returns -1/1
        scores['isolation_forest'] = self.models['isolation_forest'].predict(X)
        
        # SGD One-Class SVM: returns -1/1
        scores['sgd_svm'] = self.models['sgd_svm'].predict(X)
        
        # Statistical Autoencoder: returns -1/1
        scores['statistical_ae'] = self.models['statistical_ae'].predict(X)
        
        # Ensemble: majority voting (-1 = anomaly if at least 2 agree)
        ensemble_votes = (
            scores['isolation_forest'] == -1
        ).astype(int) + (
            scores['sgd_svm'] == -1
        ).astype(int) + (
            scores['statistical_ae'] == -1
        ).astype(int)
        
        predictions = np.where(ensemble_votes >= 2, -1, 1)
        
        n_anomalies = (predictions == -1).sum()
        n_total = len(predictions)
        print(f"  [OK] Detected {n_anomalies} anomalies ({n_anomalies/n_total*100:.2f}%)")
        
        if return_scores:
            return predictions, scores
        return predictions
    
    def get_anomaly_scores(self, df):
        """
        Get normalized anomaly scores (0-1, where 1 is most anomalous)
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted first.")
        
        X, _ = self._preprocess_data(df, fit=False)
        
        # Get decision functions (low score = anomaly)
        iso_scores = -self.models['isolation_forest'].score_samples(X)
        svm_scores = -self.models['sgd_svm'].decision_function(X)
        ae_scores = self.models['statistical_ae'].decision_function(X)
        
        # Normalize to 0-1 range
        iso_scores = (iso_scores - iso_scores.min()) / (iso_scores.max() - iso_scores.min() + 1e-8)
        svm_scores = (svm_scores - svm_scores.min()) / (svm_scores.max() - svm_scores.min() + 1e-8)
        ae_scores = (ae_scores - ae_scores.min()) / (ae_scores.max() - ae_scores.min() + 1e-8)
        
        # Average ensemble score
        ensemble_score = (iso_scores + svm_scores + ae_scores) / 3
        
        return {
            'isolation_forest': iso_scores,
            'sgd_svm': svm_scores,
            'statistical_ae': ae_scores,
            'ensemble': ensemble_score
        }
    
    def save(self, filepath):
        """Save the fitted model"""
        joblib.dump(self, filepath)
        print(f"[OK] Model saved to {filepath}")
    
    @staticmethod
    def load(filepath):
        """Load a fitted model"""
        model = joblib.load(filepath)
        print(f"[OK] Model loaded from {filepath}")
        return model


def main():
    """Example usage"""
    
    print("Loading data...")
    df = pd.read_csv('server_fin.csv')
    print(f"Dataset shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    
    # Use entire dataset for training
    print(f"\nUsing entire dataset for training: {df.shape}")
    
    # Initialize and fit ensemble (10% contamination = more sensitive)
    detector = EnsembleOutlierDetector(contamination=0.10, batch_size=5000)
    detector.fit(df)
    
    # Predict on entire dataset
    predictions, individual_scores = detector.predict(df, return_scores=True)
    scores = detector.get_anomaly_scores(df)
    
    # Add results to dataframe
    df['prediction'] = predictions
    df['anomaly_score'] = scores['ensemble']
    df['iso_forest'] = individual_scores['isolation_forest']
    df['sgd_svm'] = individual_scores['sgd_svm']
    df['stat_ae'] = individual_scores['statistical_ae']
    
    # Extract only anomalies for saving
    anomalies_df = df[df['prediction'] == -1].copy()
    
    # Save only anomalies to CSV
    anomalies_df.to_csv('server_fin_outliers.csv', index=False)
    print("\n[OK] Anomalies saved to 'server_fin_outliers.csv'")
    
    # Pickle/Save the trained model
    detector.save('ensemble_model.pkl')
    print("[OK] Model pickled and saved to 'ensemble_model.pkl'")
    
    # Display summary
    print("\n" + "=" * 60)
    print("ANOMALY DETECTION SUMMARY")
    print("=" * 60)
    print(f"\nTotal records in dataset: {len(df)}")
    print(f"Anomalies detected: {len(anomalies_df)}")
    print(f"Anomaly rate: {len(anomalies_df)/len(df)*100:.2f}%")
    
    # Model breakdown
    iso_anomalies = (individual_scores['isolation_forest'] == -1).sum()
    svm_anomalies = (individual_scores['sgd_svm'] == -1).sum()
    ae_anomalies = (individual_scores['statistical_ae'] == -1).sum()
    
    print(f"\nIndividual model detections:")
    print(f"  - Isolation Forest: {iso_anomalies} anomalies ({iso_anomalies/len(df)*100:.2f}%)")
    print(f"  - SGD One-Class SVM: {svm_anomalies} anomalies ({svm_anomalies/len(df)*100:.2f}%)")
    print(f"  - Statistical Autoencoder: {ae_anomalies} anomalies ({ae_anomalies/len(df)*100:.2f}%)")
    print(f"  - Ensemble (2+ agreement): {len(anomalies_df)} anomalies ({len(anomalies_df)/len(df)*100:.2f}%)")
    
    print(f"\nTop 20 most anomalous records:")
    print(anomalies_df.nlargest(20, 'anomaly_score')[['Timestamp', 'Server_ID', 'Power_Usage_Watts', 'Carbon_Emission', 'anomaly_score']])


if __name__ == "__main__":
    main()
