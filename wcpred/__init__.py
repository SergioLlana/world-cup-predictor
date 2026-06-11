"""wcpred — World Cup score predictor optimised for Superbru scoring."""
from .model import DixonColes
from .predict import predict_match, predict_fixtures
from .scoring import points, best_prediction, closeness_index

__version__ = "1.0.0"
