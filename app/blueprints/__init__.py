"""HTTP layer.

Each subpackage is one Flask blueprint: a thin controller that validates
input, enforces authorization, delegates to the service layer, and shapes the
response. Business logic lives in ``app.services`` (Phase 1+), never here.
"""
