"""wcpred — World Cup score predictor optimised for Penka scoring."""
from .model import DixonColes
from .predict import predict_match, predict_fixtures
from .scoring import points, best_prediction, closeness_index

__all__ = ["DixonColes", "predict_match", "predict_fixtures",
           "points", "best_prediction", "closeness_index"]
__version__ = "1.0.0"
