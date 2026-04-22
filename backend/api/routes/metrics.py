from flask import Blueprint, jsonify

from services.metrics_tracker import get_metrics_summary


metrics_bp = Blueprint("metrics", __name__)


@metrics_bp.get("/metrics/summary")
def metrics_summary():
    return jsonify(get_metrics_summary()), 200

