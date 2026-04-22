from flask import Blueprint, jsonify

from storage.sqlite_db import DB_PATH


debug_bp = Blueprint("debug", __name__)


@debug_bp.get("/debug/ping")
def debug_ping():
    return jsonify({"status": "ok"}), 200


@debug_bp.get("/debug/db")
def debug_db():
    return jsonify({"db_path": str(DB_PATH)}), 200


__all__ = ["debug_bp"]

