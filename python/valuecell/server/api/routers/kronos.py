"""Kronos prediction router for ValueCell Server."""

import os
import sys
from typing import Optional

import pandas as pd
from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel, Field

from ..schemas import SuccessResponse

# Add Kronos to path
KRONOS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))),
    "Kronos"
)
logger.info(f"KRONOS_PATH: {KRONOS_PATH}, exists: {os.path.exists(KRONOS_PATH)}")
if KRONOS_PATH not in sys.path:
    sys.path.insert(0, KRONOS_PATH)

# Try to import Kronos
try:
    from model import Kronos, KronosTokenizer, KronosPredictor
    MODEL_AVAILABLE = True
    logger.info("Kronos model imported successfully")
except ImportError as e:
    MODEL_AVAILABLE = False
    logger.warning(f"Kronos model cannot be imported: {e}")
except Exception as e:
    MODEL_AVAILABLE = False
    logger.error(f"Kronos model import error: {e}")

# Global model instances
_tokenizer = None
_model = None
_predictor = None
_current_model_key = None  # Track which model is currently loaded

# Model base path
MODEL_BASE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))),
    "models", "kronos"
)

# Available model configurations
AVAILABLE_MODELS = {
    'kronos-mini': {
        'name': 'Kronos-mini',
        'model_id': os.path.join(MODEL_BASE_PATH, 'pretrained', 'kronos-mini'),
        'tokenizer_id': os.path.join(MODEL_BASE_PATH, 'pretrained', 'kronos-mini', 'tokenizer'),
        'context_length': 2048,
        'params': '4.1M',
        'description': 'Lightweight model, suitable for fast prediction'
    },
    'kronos-small': {
        'name': 'Kronos-small',
        'model_id': os.path.join(MODEL_BASE_PATH, 'pretrained', 'kronos-small'),
        'tokenizer_id': os.path.join(MODEL_BASE_PATH, 'pretrained', 'kronos-small', 'tokenizer'),
        'context_length': 512,
        'params': '24.7M',
        'description': 'Small model, balanced performance and speed'
    },
    'kronos-base': {
        'name': 'Kronos-base',
        'model_id': os.path.join(MODEL_BASE_PATH, 'pretrained', 'kronos-base'),
        'tokenizer_id': os.path.join(MODEL_BASE_PATH, 'pretrained', 'kronos-base', 'tokenizer'),
        'context_length': 512,
        'params': '102.3M',
        'description': 'Base model, provides better prediction quality'
    }
}


class PredictionRequest(BaseModel):
    """Prediction request model."""
    ticker: str = Field(..., description="Stock ticker symbol")
    model_key: str = Field(default="kronos-base", description="Model key to use for prediction")
    lookback: int = Field(default=400, ge=100, le=512, description="Lookback window size")
    pred_len: int = Field(default=120, ge=30, le=180, description="Prediction length")
    temperature: float = Field(default=1.0, ge=0.1, le=2.0, description="Prediction temperature")
    top_p: float = Field(default=0.9, ge=0.1, le=1.0, description="Top-p sampling parameter")
    sample_count: int = Field(default=1, ge=1, le=5, description="Number of samples")


class LoadModelRequest(BaseModel):
    """Load model request."""
    model_key: str = Field(default="kronos-base", description="Model key")
    device: str = Field(default="cpu", description="Device (cpu/cuda)")


class PredictionResult(BaseModel):
    """Single prediction result."""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0
    amount: Optional[float] = 0


class TimeRange(BaseModel):
    """Time range info."""
    input_start: str
    input_end: str
    pred_start: str
    pred_end: str


class PredictionResponse(BaseModel):
    """Prediction response model."""
    success: bool
    prediction_type: str
    chart: Optional[str] = None
    prediction_results: list[PredictionResult]
    actual_data: list[PredictionResult]
    has_comparison: bool
    time_range: Optional[TimeRange] = None
    message: str


class ModelStatusResponse(BaseModel):
    """Model status response."""
    available: bool
    loaded: bool
    message: str
    current_model: Optional[dict] = None


class AvailableModelsResponse(BaseModel):
    """Available models response."""
    models: dict
    model_available: bool


def create_kronos_router() -> APIRouter:
    """Create and configure the Kronos router."""
    router = APIRouter(prefix="/kronos", tags=["kronos"])

    @router.get("/model-status", response_model=SuccessResponse[ModelStatusResponse])
    async def get_model_status():
        """Get current model status."""
        global _predictor, _current_model_key
        
        if MODEL_AVAILABLE:
            if _predictor is not None:
                model_info = AVAILABLE_MODELS.get(_current_model_key, {})
                return SuccessResponse.create(
                    data=ModelStatusResponse(
                        available=True,
                        loaded=True,
                        message="Kronos model loaded and available",
                        current_model={
                            "name": model_info.get("name", _predictor.model.__class__.__name__),
                            "device": str(next(_predictor.model.parameters()).device),
                            "model_key": _current_model_key
                        }
                    )
                )
            else:
                return SuccessResponse.create(
                    data=ModelStatusResponse(
                        available=True,
                        loaded=False,
                        message="Kronos model available but not loaded"
                    )
                )
        else:
            return SuccessResponse.create(
                data=ModelStatusResponse(
                    available=False,
                    loaded=False,
                    message="Kronos model library not available"
                )
            )

    @router.get("/available-models", response_model=SuccessResponse[AvailableModelsResponse])
    async def get_available_models():
        """Get available model configurations."""
        return SuccessResponse.create(
            data=AvailableModelsResponse(
                models=AVAILABLE_MODELS,
                model_available=MODEL_AVAILABLE
            )
        )

    @router.post("/load-model", response_model=SuccessResponse)
    async def load_model(request: LoadModelRequest):
        """Load a Kronos model."""
        global _tokenizer, _model, _predictor, _current_model_key
        
        if not MODEL_AVAILABLE:
            return SuccessResponse.create(
                msg="Kronos model library not available"
            )
        
        if request.model_key not in AVAILABLE_MODELS:
            return SuccessResponse.create(
                msg=f"Unsupported model: {request.model_key}"
            )
        
        try:
            model_config = AVAILABLE_MODELS[request.model_key]
            
            _tokenizer = KronosTokenizer.from_pretrained(model_config['tokenizer_id'])
            _model = Kronos.from_pretrained(model_config['model_id'])
            _predictor = KronosPredictor(_model, _tokenizer, device=request.device, max_context=model_config['context_length'])
            _current_model_key = request.model_key
            
            return SuccessResponse.create(
                msg=f"Model loaded: {model_config['name']} ({model_config['params']}) on {request.device}"
            )
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return SuccessResponse.create(
                msg=f"Failed to load model: {str(e)}"
            )

    @router.post("/predict", response_model=SuccessResponse[PredictionResponse])
    async def predict(request: PredictionRequest):
        """Run Kronos prediction for a stock."""
        global _predictor, _tokenizer, _model, _current_model_key
        
        if not MODEL_AVAILABLE:
            return SuccessResponse.create(
                data=PredictionResponse(
                    success=False,
                    prediction_type="error",
                    prediction_results=[],
                    actual_data=[],
                    has_comparison=False,
                    message="Kronos model library not available"
                )
            )
        
        # Get requested model key
        requested_model_key = request.model_key
        if requested_model_key not in AVAILABLE_MODELS:
            requested_model_key = 'kronos-base'
        
        # Load or switch model if needed
        if _predictor is None or _current_model_key != requested_model_key:
            try:
                model_config = AVAILABLE_MODELS[requested_model_key]
                logger.info(f"Loading model: {requested_model_key}")
                _tokenizer = KronosTokenizer.from_pretrained(model_config['tokenizer_id'])
                _model = Kronos.from_pretrained(model_config['model_id'])
                _predictor = KronosPredictor(_model, _tokenizer, device='cpu', max_context=model_config['context_length'])
                _current_model_key = requested_model_key
                logger.info(f"Model loaded: {model_config['name']}")
            except Exception as e:
                logger.error(f"Failed to auto-load model: {e}")
                return SuccessResponse.create(
                    data=PredictionResponse(
                        success=False,
                        prediction_type="error",
                        prediction_results=[],
                        actual_data=[],
                        has_comparison=False,
                        message=f"Failed to load model: {str(e)}"
                    )
                )
        
        try:
            # Fetch stock data using yfinance
            import yfinance as yf
            
            ticker = request.ticker
            # Handle ticker format (e.g., "NASDAQ:AAPL" -> "AAPL")
            if ":" in ticker:
                ticker = ticker.split(":")[1]
            
            # Download historical data
            stock = yf.Ticker(ticker)
            df = stock.history(period="2y", interval="1d")
            
            if df.empty:
                return SuccessResponse.create(
                    data=PredictionResponse(
                        success=False,
                        prediction_type="error",
                        prediction_results=[],
                        actual_data=[],
                        has_comparison=False,
                        message=f"No data available for ticker: {request.ticker}"
                    )
                )
            
            # Prepare data
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            if 'date' in df.columns:
                df['timestamps'] = pd.to_datetime(df['date'])
            elif 'datetime' in df.columns:
                df['timestamps'] = pd.to_datetime(df['datetime'])
            
            # Check data length and auto-adjust parameters if needed
            total_needed = request.lookback + request.pred_len
            actual_lookback = request.lookback
            actual_pred_len = request.pred_len
            
            if len(df) < total_needed:
                # Auto-adjust: prioritize lookback, reduce pred_len if needed
                available = len(df)
                # Minimum lookback should be at least 100 for meaningful predictions
                min_lookback = 100
                min_pred_len = 30
                
                if available < min_lookback + min_pred_len:
                    return SuccessResponse.create(
                        data=PredictionResponse(
                            success=False,
                            prediction_type="error",
                            prediction_results=[],
                            actual_data=[],
                            has_comparison=False,
                            message=f"Insufficient data: need at least {min_lookback + min_pred_len}, got {available}"
                        )
                    )
                
                # Adjust parameters: keep lookback as much as possible
                if available >= request.lookback + min_pred_len:
                    actual_pred_len = available - request.lookback
                else:
                    # Reduce both proportionally
                    actual_lookback = min(request.lookback, int(available * 0.75))
                    actual_pred_len = available - actual_lookback
                
                logger.info(f"Auto-adjusted parameters: lookback {request.lookback}->{actual_lookback}, pred_len {request.pred_len}->{actual_pred_len}")
            
            # Use latest data for prediction
            required_cols = ['open', 'high', 'low', 'close']
            if 'volume' in df.columns:
                required_cols.append('volume')
            
            # For future prediction, use all available data as input
            # and generate future timestamps for prediction
            x_df = df.iloc[-actual_lookback:][required_cols]
            x_timestamp = df.iloc[-actual_lookback:]['timestamps']
            
            # Generate future timestamps for prediction
            last_ts = x_timestamp.iloc[-1]
            # Calculate average time difference (to handle weekends/holidays)
            if len(x_timestamp) > 1:
                time_diffs = x_timestamp.diff().dropna()
                avg_diff = time_diffs.median()  # Use median to handle gaps
            else:
                avg_diff = pd.Timedelta(days=1)
            
            # Generate future timestamps
            future_timestamps = pd.date_range(
                start=last_ts + avg_diff, 
                periods=actual_pred_len, 
                freq='B'  # Business days
            )
            y_timestamp = pd.Series(future_timestamps)
            
            logger.info(f"Predicting {actual_pred_len} points from {last_ts} to {future_timestamps[-1]}")
            
            # Run prediction
            pred_df = _predictor.predict(
                df=x_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=actual_pred_len,
                T=request.temperature,
                top_p=request.top_p,
                sample_count=request.sample_count
            )
            
            logger.info(f"Prediction returned {len(pred_df)} points")
            
            # Prepare results - use generated future timestamps
            prediction_results = []
            for i, (_, row) in enumerate(pred_df.iterrows()):
                ts = future_timestamps[i] if i < len(future_timestamps) else pd.Timestamp.now()
                prediction_results.append(PredictionResult(
                    timestamp=ts.isoformat(),
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume']) if 'volume' in row else 0
                ))
            
            # No actual data for future predictions
            actual_data = []
            
            # Create chart JSON
            chart_data = _create_prediction_chart(
                df, pred_df, actual_lookback, actual_pred_len, 
                None, len(df) - actual_lookback, future_timestamps
            )
            
            return SuccessResponse.create(
                data=PredictionResponse(
                    success=True,
                    prediction_type=f"Kronos prediction for {request.ticker}",
                    chart=chart_data,
                    prediction_results=prediction_results,
                    actual_data=actual_data,
                    has_comparison=len(actual_data) > 0,
                    time_range=TimeRange(
                        input_start=str(x_timestamp.iloc[0]),
                        input_end=str(x_timestamp.iloc[-1]),
                        pred_start=str(future_timestamps[0]) if len(future_timestamps) > 0 else "",
                        pred_end=str(future_timestamps[-1]) if len(future_timestamps) > 0 else ""
                    ),
                    message=f"Prediction completed with {len(prediction_results)} points"
                )
            )
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            import traceback
            traceback.print_exc()
            return SuccessResponse.create(
                data=PredictionResponse(
                    success=False,
                    prediction_type="error",
                    prediction_results=[],
                    actual_data=[],
                    has_comparison=False,
                    message=f"Prediction failed: {str(e)}"
                )
            )

    return router


def _create_prediction_chart(df, pred_df, lookback, pred_len, actual_df, start_idx, pred_timestamps=None):
    """Create a Plotly chart JSON for the prediction results."""
    import json
    
    try:
        import plotly.graph_objects as go
        
        # Historical data
        hist_df = df.iloc[start_idx:start_idx + lookback].copy()
        
        fig = go.Figure()
        
        # Convert timestamps to string format for Plotly
        hist_x = [ts.strftime('%Y-%m-%d') for ts in hist_df['timestamps']]
        
        # Historical candlestick
        fig.add_trace(go.Candlestick(
            x=hist_x,
            open=hist_df['open'].tolist(),
            high=hist_df['high'].tolist(),
            low=hist_df['low'].tolist(),
            close=hist_df['close'].tolist(),
            name='Historical',
            increasing_line_color='#26A69A',
            decreasing_line_color='#EF5350'
        ))
        
        # Prediction candlestick
        if pred_df is not None and len(pred_df) > 0:
            # Use provided timestamps or generate new ones
            if pred_timestamps is not None:
                pred_x = [ts.strftime('%Y-%m-%d') for ts in pred_timestamps[:len(pred_df)]]
            else:
                last_ts = hist_df['timestamps'].iloc[-1]
                time_diff = hist_df['timestamps'].iloc[1] - hist_df['timestamps'].iloc[0] if len(hist_df) > 1 else pd.Timedelta(days=1)
                generated_timestamps = pd.date_range(start=last_ts + time_diff, periods=len(pred_df), freq='B')
                pred_x = [ts.strftime('%Y-%m-%d') for ts in generated_timestamps]
            
            fig.add_trace(go.Candlestick(
                x=pred_x,
                open=[float(x) for x in pred_df['open'].tolist()],
                high=[float(x) for x in pred_df['high'].tolist()],
                low=[float(x) for x in pred_df['low'].tolist()],
                close=[float(x) for x in pred_df['close'].tolist()],
                name='Prediction',
                increasing_line_color='#66BB6A',
                decreasing_line_color='#FF7043'
            ))
        
        # Actual data
        if actual_df is not None and len(actual_df) > 0:
            actual_x = [ts.strftime('%Y-%m-%d') for ts in actual_df['timestamps']]
            fig.add_trace(go.Candlestick(
                x=actual_x,
                open=actual_df['open'].tolist(),
                high=actual_df['high'].tolist(),
                low=actual_df['low'].tolist(),
                close=actual_df['close'].tolist(),
                name='Actual',
                increasing_line_color='#FF9800',
                decreasing_line_color='#F44336'
            ))
        
        fig.update_layout(
            title='Kronos Prediction Results',
            xaxis_title='Time',
            yaxis_title='Price',
            template='plotly_white',
            height=420,
            showlegend=True,
            xaxis_rangeslider_visible=False
        )
        
        # Convert to dict and then to JSON to avoid binary encoding
        fig_dict = fig.to_dict()
        return json.dumps(fig_dict)
    except Exception as e:
        logger.error(f"Failed to create chart: {e}")
        import traceback
        traceback.print_exc()
        return None
