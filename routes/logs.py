"""GET /log — audit log endpoint. GET /analytics — dashboard."""

from flask import Blueprint, request, jsonify
from models import database

logs_bp = Blueprint("logs", __name__)


@logs_bp.route("/log", methods=["GET"])
def get_log():
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    entries = database.get_log(limit=limit, offset=offset)
    return jsonify({
        "entries": entries,
        "count": len(entries),
        "limit": limit,
        "offset": offset,
    }), 200


@logs_bp.route("/submission/<content_id>", methods=["GET"])
def get_submission(content_id: str):
    submission = database.get_submission(content_id)
    if submission is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(submission), 200


@logs_bp.route("/analytics", methods=["GET"])
def analytics():
    """Analytics dashboard: detection patterns, appeal rates, confidence stats."""
    stats = database.get_analytics()
    return jsonify(stats), 200
