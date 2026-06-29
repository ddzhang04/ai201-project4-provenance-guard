"""POST /submit — content attribution endpoint."""

from flask import Blueprint, request, jsonify
from detection import pipeline
from models import database

submit_bp = Blueprint("submit", __name__)


@submit_bp.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    # Accept both "text" (spec field name) and "content" for compatibility
    content = (data.get("text") or data.get("content") or "").strip()
    creator_id = data.get("creator_id", "anonymous").strip()

    if not content:
        return jsonify({"error": "Missing 'text' field"}), 400

    if len(content) < 20:
        return jsonify({"error": "Content too short (minimum 20 characters)"}), 400

    if len(content) > 50000:
        return jsonify({"error": "Content too long (maximum 50,000 characters)"}), 400

    result = pipeline.run(content)
    content_id = database.log_submission(content, result, creator_id=creator_id)

    return jsonify({
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": result["attribution"],
        "ai_probability": result["ai_probability"],
        "confidence_score": result["confidence_score"],
        "transparency_label": result["label"],
        "signals_used": [s["signal_name"] for s in result["signals"]],
        "appeal_endpoint": f"/appeal (POST with content_id={content_id!r})",
    }), 200
