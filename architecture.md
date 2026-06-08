# School Management System Architecture

## Overview

This project is a Django-based School Management System with a REST API backend powered by Django REST Framework. It supports multi-tenant school management, role-based access control, admission workflows, staff/student management, fee processing, attendance, leave requests, announcements, and online payment integration via Razorpay.

## Core Layers

### Presentation Layer
- `templates/` contains HTML templates for email OTPs, receipts, login, and admission forms.
- Frontend clients integrate via REST APIs under `api/` and include:
  - Web applications
  - Mobile/Android clients
- API documentation is generated via `drf_yasg`.

### API Layer
- `sms/urls.py` defines the router and endpoint structure.
- Endpoints are exposed through DRF `ViewSet` and `APIView` classes in `sms_app/views.py`.
- Authentication and session handling use JWT tokens plus cookie-based JWT support.
- `LoginView` returns role/module metadata and issues access/refresh tokens.

### Business Logic Layer
- `sms_app/views.py` orchestrates application behavior for:
  - Authentication and OTP-based registration
  - School and staff administration
  - Admission form creation, publishing, submission, and verification
  - Document upload and fee amount resolution
  - Razorpay payment order creation and payment verification
  - Role-specific data access and action authorization
- Custom permissions map roles and module access to API endpoints.

### Data Layer
- `sms_app/models.py` contains the domain model definitions and relationships.
- Central entities include:
  - `CustomUser` (custom auth user) linked to `School`
  - `School`, `Feature`, `SchoolFeature`, `Module`, `UserModuleAccess`
  - `Staff`, `SchoolClass`, `Division`, `Subject`, `AcademicYear`
  - `OTP`, `TempUser`, `AdmissionForm`, `FormSection`, `FormField`, `DocumentField`
  - `Admission`, `AdmissionFieldValue`, `AdmissionDocument`, `AdmissionFee`, `AdmissionFeeStructure`
  - `Student`, `StudentFieldValue`, and auxiliary models for syllabus, timetable, leave, announcements

## Authentication & Registration Workflow

### OTP-based registration
1. Client POSTs to `/api/send-otp/` with `email` or `mobile`.
2. `SendOTPView` creates an `OTP` record and returns the generated code (currently exposed for testing).
3. Client POSTs to `/api/verify-otp/` with `email` or `mobile`, `otp`, `password`, `school_id`, and `school_slug`.
4. `VerifyOTPSerializer` validates the OTP and creates a new `CustomUser`.
5. `TempUser` record is created and user is assigned to the `temp_user` group.

### Login
1. Client POSTs to `/api/api-login/` with `email`/`mobile`/`username` and `password`.
2. `LoginView` validates credentials and issues JWT tokens.
3. The response includes:
   - `school_id`, `school_slug`
   - `roles` from Django groups
   - `modules` from `UserModuleAccess`
4. Web clients receive tokens in secure HttpOnly cookies; mobile clients receive JSON tokens.

## School and Module Administration Workflow

### School creation
- `SchoolView` allows super admins to create schools and assign an admin user.
- `SchoolSerializer` accepts `feature_ids` and bulk-creates `SchoolFeature` records.
- `UserModuleAccess` assignments are driven by features and staff roles.

### Feature/module access
- `ModuleView` exposes modules filtered by active school features.
- `UserModuleAccess` controls whether a user may access a given module code.
- `HasModuleAccess` guards views that require module-specific permission.

## Admission Form Workflow

### Form creation
- Principals call `/api/forms/` using `AdmissionFormViewSet`.
- `AdmissionFormSerializer` handles nested payloads for:
  - `sections` and `fields`
  - `document_fields`
  - `fee_structures_input` for `individual` fee mode
- The serializer stores form metadata, sections, form fields, document requirements, and fee structures atomically.

### Publishing and public access
- `FormStatus` toggles `AdmissionForm.is_active` and ensures only one form is active at a time.
- `FormFieldViewSet` returns the active admission form for the current user's school.
- `Admission_link` provides form access via `unique_link`, returning school identifiers.

## Temp User Admission Submission Workflow

### Admission data submission
1. A temp user submits admission data to `/api/submissions/`.
2. `AdmissionSubmissionSerializer`:
   - validates form fields against active form schema
   - ensures required fields are present
   - resolves `school_class` from either explicit input or mapped form field
   - updates existing admission if `admission_number` is supplied and fee not verified
   - creates a new `Admission` record with generated `admission_number`
   - stores `AdmissionFieldValue` records in bulk
3. The `Admission` record remains in `pending` state until further review.

### Document upload
1. Temp user uploads documents to `/api/documentsubmission/`.
2. `DocumentSubmissionView` normalizes the multipart payload and passes it to `AdmissionDocumentSubmissionSerializer`.
3. The serializer validates the admission belongs to the current temp user and creates or updates `AdmissionDocument` records.
4. After upload, the endpoint computes fee amount based on:
   - `AdmissionForm.fee_type == general` → fixed form fee
   - `AdmissionForm.fee_type == individual` → fee structure by selected class

## Payment Workflow

### Razorpay order creation
1. Student/temp user posts to `/api/razorpayorder/` with `admission_number` and optionally `amount`.
2. `RazorpayOrderView` verifies that no `AdmissionFee` exists for the admission.
3. It resolves the fee amount from the admission form and creates an `AdmissionFee` record.
4. Razorpay order is created using the configured `client`.
5. The response returns order metadata needed by the frontend.

### Payment verification
1. The frontend submits payment proof to `/api/verify-payment/`.
2. `VerifyPaymentView` validates the Razorpay signature with `RAZOR_PAY_SECRET_KEY`.
3. It updates the `AdmissionFee` record with payment details and marks the admission as `pay_process=True`.
4. Offline payments are also supported through `OffilinePaymentView`, which creates an `AdmissionFee` record and marks offline settlement.

## Fee Verification and Admissions Review Workflow

### Fee verification
- `FeeVerifyView` is restricted to the fee manager role.
- `FeesVerifySerializer` updates `Admission.fee_verified` and `fee_verified_at`.
- Admission records become eligible for downstream student creation after verification.

### Admission review for clerks
- `AdmissionReadOnlyViewSet` returns admissions with `fee_verified=True` but not yet clerk-verified.
- `ClerkVerifyView` updates the admission state as needed.
- `AdmissionReceiptViewSet` exposes paid admissions for receipt generation.

### Clerk updates
- `AdmissionUpdateViewSet` enables clerks to patch admission field values.
- `AdmissionDocumentViewSet` enables clerks to update uploaded admission documents.

## Data & Entity Relationships

### Tenant model
- `School` is the tenant root.
- `CustomUser.school` associates users to a school.
- Most querysets are filtered by `request.user.school` to enforce tenant isolation.

### Admission domain
- `AdmissionForm` defines the form template.
- `FormSection` and `FormField` define structured form sections and inputs.
- `DocumentField` defines required documents for a form.
- `Admission` stores submission metadata and payment state.
- `AdmissionFieldValue` stores individual answer values.
- `AdmissionDocument` stores uploaded files.
- `AdmissionFee` tracks payment records and Razorpay metadata.

### Temporary user flow
- `TempUser` wraps a newly registered `CustomUser` for admission submission.
- Temp users are created during OTP verification.
- Principals can activate/deactivate temp users via `TempUserListViewSet`.

## Key Workflow Summary

1. `SendOTPView` generates OTP → user verifies via `VerifyOTPView` → `TempUser` is created.
2. Temp user logs in via `LoginView` and receives JWT tokens.
3. Principal creates and publishes admission forms via `AdmissionFormViewSet`.
4. Temp user retrieves active form via `FormFieldViewSet`.
5. Temp user submits form data via `FormSubmissionViewSet`.
6. Temp user uploads documents via `DocumentSubmissionView`.
7. System calculates fee and creates a Razorpay order with `RazorpayOrderView`.
8. Frontend submits payment verification to `VerifyPaymentView`.
9. Fee manager verifies payment with `FeeVerifyView`.
10. Clerk reviews admissions with `AdmissionReadOnlyViewSet` and can update data/documents.

## Important Configuration
- `AUTH_USER_MODEL = 'sms_app.CustomUser'`
- `REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES` uses `sms_app.authentication.CookieJWTAuthentication`.
- `CORS_ALLOW_ALL_ORIGINS = True` for development/testing.
- `STATIC_URL`, `MEDIA_URL`, and `MEDIA_ROOT` are configured for static/media assets.

## Deployment Notes
- Uses environment variables for `DATABASE_URL` and `REDIS_URL`.
- Uses `whitenoise` middleware for static file serving.
- `ALLOWED_HOSTS = ['*']` is currently open for testing and should be tightened in production.
- `DEBUG = True` should be switched off in production.
