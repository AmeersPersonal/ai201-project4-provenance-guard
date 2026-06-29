"""
Flask API for Provenance Guard.

Routes:
  GET  /         what this service is
  POST /submit   classify content, save it, return the verdict and label
  POST /appeal   contest a decision, log it, mark it under_review
  GET  /log      the audit log (decisions with their appeals)

Run with: python src/main.py  (http://localhost:5000)
"""

import os
import sys

# db lives in src/db/db.py, so add that folder to the path to import it as `db`.
# `tool` sits next to this file and imports normally.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "db"))

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import db
import tool

load_dotenv()

ALLOWED_CONTENT_TYPES = {"text", "image_description", "metadata"}
MAX_CONTENT_CHARS = 20_000
EXCERPT_CHARS = 280

app = Flask(__name__)

# A /submit can fire off a paid LLM call, so we limit how fast one IP can hit
# it. The reasoning behind the actual numbers is written up in the README.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

db.init_db()


@app.get("/")
def index():
    return jsonify(
        {
            "service": "Provenance Guard",
            "description": "AI-vs-human content attribution with confidence, "
            "transparency labels, appeals, rate limiting and audit logging.",
            "endpoints": {
                "POST /submit": "Classify content. Body: {content, content_type?}",
                "POST /appeal": "Contest a decision. Body: {content_id, reasoning}",
                "GET /log": "Audit log of every decision and appeal.",
            },
            "content_types": sorted(ALLOWED_CONTENT_TYPES),
            "rate_limit": "10 per minute; 100 per day (on /submit)",
        }
    )


@app.post("/submit")
@limiter.limit("10 per minute; 100 per day")
def submit():
    payload = request.get_json(silent=True) or {}
    content = payload.get("content")
    content_type = payload.get("content_type", "text")

    if not isinstance(content, str) or not content.strip():
        return jsonify({"error": "`content` is required and must be a non-empty string."}), 400
    if len(content) > MAX_CONTENT_CHARS:
        return jsonify({"error": f"`content` exceeds {MAX_CONTENT_CHARS} characters."}), 400
    if content_type not in ALLOWED_CONTENT_TYPES:
        return jsonify(
            {"error": f"`content_type` must be one of {sorted(ALLOWED_CONTENT_TYPES)}."}
        ), 400

    verdict = tool.run_pipeline(content, content_type=content_type)
    excerpt = content[:EXCERPT_CHARS]
    content_id = db.insert_decision(
        content_type=content_type,
        excerpt=excerpt,
        result=verdict["result"],
        ai_probability=verdict["ai_probability"],
        confidence=verdict["confidence"],
        signals=verdict["signals"],
        label=verdict["label"],
    )

    return jsonify(
        {
            "content_id": content_id,
            "content_type": content_type,
            "result": verdict["result"],
            "ai_probability": verdict["ai_probability"],
            "confidence": verdict["confidence"],
            "label": verdict["label"],
            "signals": verdict["signals"],
            "status": "classified",
        }
    ), 201


@app.post("/appeal")
def appeal():
    payload = request.get_json(silent=True) or {}
    content_id = payload.get("content_id")
    reasoning = payload.get("reasoning")

    if not isinstance(content_id, str) or not content_id.strip():
        return jsonify({"error": "`content_id` is required."}), 400
    if not isinstance(reasoning, str) or not reasoning.strip():
        return jsonify({"error": "`reasoning` is required and must be non-empty."}), 400

    appeal_id = db.insert_appeal(content_id=content_id, reasoning=reasoning)
    if appeal_id is None:
        return jsonify({"error": f"No decision found for content_id '{content_id}'."}), 404

    return jsonify(
        {
            "appeal_id": appeal_id,
            "content_id": content_id,
            "status": "under_review",
            "message": "Appeal recorded. The original decision is now under review.",
            "decision": db.get_decision(content_id),
        }
    ), 201


@app.get("/log")
def log():
    entries = db.get_log()
    return jsonify({"count": len(entries), "log": entries})


@app.errorhandler(429)
def ratelimit_handler(exc):
    return jsonify(
        {
            "error": "Rate limit exceeded.",
            "detail": str(exc.description),
            "limit": "10 per minute; 100 per day on /submit",
        }
    ), 429


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=True)
