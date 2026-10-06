# SMS Shared Core Package

This package provides cross-cutting shared components for the SMS Microservices Architecture:
- `authentication`: Cookie & Header JWT Authenticator with tenant verification.
- `middleware`: Multi-tenant header isolation (`X-School-ID`) and query normalization.
- `exceptions`: Custom domain exception handler for REST Framework.
- `http`: Resilient inter-service REST client (`InterServiceRESTClient`).
- `utils`: Standardized text normalization, phone validation, and file handling utilities.
