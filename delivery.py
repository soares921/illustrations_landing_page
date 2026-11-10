"""
Delivery to Simplicity Life.

Kept separate on purpose: how sheets get to Simplicity Life (email, shared
Drive folder, etc.) hasn't been decided. When it is, it gets built here and
called from app.py after a request is submitted. Nothing else should change.
"""


def deliver(request, request_id, sheets):
    """
    sheets: list of (carrier, filename, pdf_bytes).
    Not built yet. Returns False so the app knows nothing was sent.
    """
    return False
