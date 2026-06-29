"""Provenance Guard — AI content attribution backend."""

import os
from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

from models.database import init_db
from routes.submit import submit_bp
from routes.appeal import appeal_bp
from routes.logs import logs_bp
from routes.certificate import certificate_bp

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)

    # Rate limiter — default limits on all routes
    # Reasoning: a creator on a writing platform submits a piece at most a few times
    # per minute. 10/min prevents accidental hammering; 100/day covers normal use.
    # The /submit endpoint has stricter limits because it calls the Groq API.
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
    )

    # Stricter limit on the expensive /submit endpoint (calls Groq API + writes DB)
    # 10 per minute: enough for active use, prevents flooding
    limiter.limit("10 per minute; 100 per day")(submit_bp)

    # Appeals: 5/minute — generous, but prevents programmatic bulk filing
    limiter.limit("5 per minute; 50 per day")(appeal_bp)

    app.register_blueprint(submit_bp)
    app.register_blueprint(appeal_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(certificate_bp)

    init_db()

    @app.route("/", methods=["GET"])
    def index():
        return jsonify({
            "service": "Provenance Guard",
            "version": "1.0.0",
            "description": "AI content attribution backend — classify, label, and manage appeals for creative content",
            "endpoints": {
                "POST /submit": "Submit content for attribution analysis",
                "POST /appeal": "Contest a classification decision",
                "POST /certificate": "Issue a provenance certificate (stretch)",
                "GET /log": "Audit log of all decisions",
                "GET /submission/<content_id>": "Look up a specific submission by content_id",
                "GET /analytics": "Detection patterns and statistics dashboard",
            },
            "signals": [
                "groq_llm (llama-3.3-70b-versatile)",
                "stylometric heuristics",
                "entropy / n-gram analysis",
            ],
            "rate_limits": {
                "/submit": "10/minute, 100/day per IP",
                "/appeal": "5/minute, 50/day per IP",
                "other": "50/hour, 200/day per IP",
            },
        })

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({
            "error": "Rate limit exceeded",
            "message": str(e.description),
        }), 429

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
