import os
import logging
import requests
from django.conf import settings

logger = logging.getLogger("inter_service_client")

SERVICE_PORT_MAP = {
    "auth-identity-service": os.getenv("AUTH_SERVICE_URL", "http://localhost:8001"),
    "tenant-subscription-service": os.getenv("TENANT_SERVICE_URL", "http://localhost:8002"),
    "academic-timetable-service": os.getenv("ACADEMIC_SERVICE_URL", "http://localhost:8003"),
    "student-admission-service": os.getenv("STUDENT_SERVICE_URL", "http://localhost:8004"),
    "staff-hr-service": os.getenv("STAFF_SERVICE_URL", "http://localhost:8005"),
    "examination-result-service": os.getenv("EXAM_SERVICE_URL", "http://localhost:8006"),
    "finance-accounting-service": os.getenv("FINANCE_SERVICE_URL", "http://localhost:8007"),
    "library-management-service": os.getenv("LIBRARY_SERVICE_URL", "http://localhost:8008"),
    "inventory-asset-service": os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8009"),
    "notification-messaging-service": os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8010"),
}


class InterServiceRESTClient:
    """
    Resilient REST client for synchronous Service-to-Service communication.
    Passes tenant context (X-School-ID) and Authorization header.
    """

    def __init__(self, service_name: str, timeout: int = 5):
        if service_name not in SERVICE_PORT_MAP:
            raise ValueError(f"Unknown service name: {service_name}")
        self.base_url = SERVICE_PORT_MAP[service_name]
        self.timeout = timeout

    def get(self, endpoint: str, headers: dict = None, params: dict = None):
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.error("InterService GET call to %s failed: %s", url, str(exc))
            raise

    def post(self, endpoint: str, data: dict = None, json: dict = None, headers: dict = None):
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            response = requests.post(url, data=data, json=json, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.error("InterService POST call to %s failed: %s", url, str(exc))
            raise
