"""Contacts-related API routes."""

from flask import Blueprint

contacts_bp = Blueprint('contacts', __name__, url_prefix='/api/contacts')


@contacts_bp.route("/status", methods=["GET"])
def contacts_status():
    """Placeholder for Contacts routes."""
    return {"status": "not implemented"}, 501

