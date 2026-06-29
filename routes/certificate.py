"""POST /certificate — provenance certificate (stretch feature)."""

from flask import Blueprint, request, jsonify
from models import database

certificate_bp = Blueprint("certificate", __name__)


@certificate_bp.route("/certificate", methods=["POST"])
def issue_certificate():
    """
    Issue a 'verified human' provenance certificate for a submission.

    The creator must provide a statement attesting to human authorship.
    A unique verification token is issued and stored — this token can be
    displayed alongside the content as a credential.

    This is a stretch feature: in a real system, the verification step
    would include additional identity checks.
    """
    data = request.get_json(silent=True) or {}
    submission_id = data.get("submission_id", "").strip()
    creator_statement = data.get("creator_statement", "").strip()

    if not submission_id:
        return jsonify({"error": "Missing 'submission_id'"}), 400

    if not creator_statement:
        return jsonify({
            "error": "Missing 'creator_statement' — provide a statement attesting to human authorship"
        }), 400

    if len(creator_statement) < 20:
        return jsonify({"error": "Statement too short (minimum 20 characters)"}), 400

    submission = database.get_submission(submission_id)
    if submission is None:
        return jsonify({"error": f"No submission found with id {submission_id!r}"}), 404

    # Only issue certificates when classification is not high-confidence AI
    if submission["attribution"] == "ai" and submission["confidence_score"] >= 0.80:
        return jsonify({
            "error": (
                "Certificates cannot be issued when the system has high confidence "
                "in AI authorship. Please file an appeal first."
            )
        }), 409

    try:
        cert = database.log_certificate(submission_id, creator_statement)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    return jsonify({
        **cert,
        "submission_id": submission_id,
        "label": {
            "variant": "provenance_certificate",
            "headline": "Verified Human Authorship",
            "body": (
                f"The creator of this content has attested to human authorship "
                f"and received a Provenance Guard certificate (ID: {cert['certificate_id']}). "
                f"Certificate issued: {cert['issued_at']}."
            ),
            "verification_token": cert["verification_token"],
        },
        "message": (
            "Your provenance certificate has been issued. Include your certificate_id "
            "and verification_token alongside your content so readers can verify it."
        ),
    }), 200
