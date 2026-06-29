"""POST /appeal — contest a classification."""

from flask import Blueprint, request, jsonify
from models import database

appeal_bp = Blueprint("appeal", __name__)


@appeal_bp.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True) or {}
    # Accept both "content_id" (spec field name) and "submission_id" for compatibility
    submission_id = (data.get("content_id") or data.get("submission_id") or "").strip()
    creator_reasoning = data.get("creator_reasoning", "").strip()

    if not submission_id:
        return jsonify({"error": "Missing 'content_id'"}), 400

    if not creator_reasoning:
        return jsonify({"error": "Missing 'creator_reasoning' — explain why you believe the classification is wrong"}), 400

    if len(creator_reasoning) < 10:
        return jsonify({"error": "Please provide more detail in your reasoning (minimum 10 characters)"}), 400

    submission = database.get_submission(submission_id)
    if submission is None:
        return jsonify({"error": f"No submission found with id {submission_id!r}"}), 404

    if submission["appeal_status"] == "under_review":
        return jsonify({
            "message": "An appeal is already under review for this submission.",
            "content_id": submission_id,
            "status": "under_review",
        }), 200

    try:
        appeal_id = database.log_appeal(submission_id, creator_reasoning)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    return jsonify({
        "appeal_id": appeal_id,
        "content_id": submission_id,
        "status": "under_review",
        "message": (
            "Your appeal has been logged. The original classification has been flagged "
            "as 'under review'. A human reviewer will examine your content and reasoning. "
            "Automated re-classification is not performed — this system acknowledges "
            "the limits of AI detection."
        ),
        "original_attribution": submission["attribution"],
        "original_ai_probability": submission["ai_probability"],
    }), 200
