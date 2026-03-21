import logging

from app.models.user_model import User
from app.models.request_model import Request, FollowUp
from app.models.audit_model import AuditLog, AgentExecution, KnowledgeChunk

logger = logging.getLogger("nexus.models_package")

# model alias used by database.py import
request_model = None
user_model = None
audit_model = None
agent_model = None
