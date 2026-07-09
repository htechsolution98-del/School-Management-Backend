"""
URL configuration for sms project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.routers import DefaultRouter

from django.urls import include
from django.views.generic import TemplateView

from django.urls import path, re_path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from django.conf import settings
from django.conf.urls.static import static
from sms_app.views import *


from sms_app.harsh_views import *

schema_view = get_schema_view(
    openapi.Info(
        title="My API",
        default_version='v1',
        description="Test API documentation",
    ),
    public=True,    
    permission_classes=[permissions.AllowAny],
)


router = DefaultRouter()
router.register(r'feature',FeatureView,basename='feature')
router.register(r'schoolfeature',SchoolFeatureView, basename='schoolfeature')
router.register(r'getfeature',GetFeatureView, basename='getfeature')
router.register(r'changefeaturestatus',ChangeFeatureStatusVIew, basename='changefeaturestatus')

# TO GET MODULE THAT SCHOOL ASSIGN 
router.register(r'getmodule',ModuleView,basename='getmodule')

router.register(r'SchoolView',SchoolView, basename='SchoolView') # DONE
# router.register(r'schoollist',SchoolListView,basename='schoollist')
# router.register(r'razardata',RazarDataView,basename='razardata')
router.register(r'StaffView',StaffView, basename='StaffView') # DONE
# router.register(r'studentSignUp',StudentSignUpView, basename='studentSignUp') # On Changing

# both api use togather when student form fill

# =========ADMISSIONS PROCESS ROUTER========

router.register(r'schoolclass', SchoolClassView, basename='schoolclass')  #only use principle METHOD [GET,POST,PUT,DELETE]
router.register(r'getclass', ClassView, basename='getclass')  #For Admission Form class Drop Down METHOD [GET]

# ===== api for admission  proccess =====

# PRINCIPLE CREATE ADMISSION FORM  [POST] Fapi-01
router.register(r'forms', AdmissionFormViewSet, basename='forms')

#  PRINCIPLE PUBLIC UNPUBLIC FORM [POST] Fapi-02
router.register(r'formstatus', FormStatus, basename='formstatus')


# MANUAL PAST STUDENT ENTERTY

router.register(r'manualstudent',ManualStudentView,basename='manualstudent')

# ADMISSION FORM FILL FIELDS SFapi-01
router.register(r'submissions', FormSubmissionViewSet, basename='submissions')
# ADMISSION FORM FILL DOCUMENT FIELDS Fapi-02
router.register(r'documentsubmission', DocumentSubmissionView, basename='documentsubmission')

# TEMP USER GET ADMISSION DATA TUapi-01
router.register(r'gettempuserdata', TempUserAdmissionViewSet, basename='gettempuserdata')

router.register(r'tempusers', TempUserListViewSet, basename='tempusers')


#GET SUBMITED DATA
router.register(r'admissionview', AdmissionReadOnlyViewSet, basename='admissionview')
router.register(r'admission-receipt', AdmissionReceiptViewSet, basename='admission-receipt')
#UPDATE FIELD VALUE BY CLARK
router.register(r'updatesubmition', AdmissionUpdateViewSet, basename='updatesubmition')
#UPDATE DOCUMENT VALUE BY CLARK
router.register(r'updateDocument', AdmissionDocumentViewSet, basename='updateDocument')


#AFTER ADMISSION SUDMISSION


# =================VERIFY API================= 
# Add GR Number --create student -create perents -create student,perent user

router.register(r'clerk_verify', ClerkVerifyView, basename='ClerkVerifyView') 

# router.register(r'PrincipleVerifyView', PrincipleVerifyView, basename='PrincipleVerifyView')

router.register(r'fee_verify', FeeVerifyView, basename='fee_verify')

router.register(r'setSubject', SetSubjectView, basename='setSubject')# For CLerk add subject METHOD [GET,POST,PUT,DELETE]  ----API Need---  api/schoolclass/ for class drop down
router.register(r'divisionSet', SetDivisionView, basename='divisionSet') #For Clerk Use METHOD [GET,POST,PUT,DELETE] ----API Need---  api/schoolclass/ for class drop down
router.register(r'divisionlist', ListDivisionView, basename='divisionlist') #For Clerk Use METHOD [GET,POST,PUT,DELETE] ----API Need---  api/schoolclass/ for class drop down

router.register(r'syllabus', SyllabusView, basename='syllabus') # For CLerk add syllabus METHOD [GET,POST,PUT,DELETE]   ----API Need---  api/schoolclass , setSubject for drop down
router.register(r'getteacher', GetTeacherView, basename='getteacher') # For teacher dwop down METHOD [GET]

router.register(r'assignClass', AssignClassView, basename='assignClass') # For CLerk assign Class METHOD [GET,POST,PUT,DELETE] ----API Need---  api/divisionSet/ , api/setSubject/ , api/getteacher/  for drop down

# ========= TIME TABLE ROUTER ============
# router.register(r'timetables', TimetableViewSet, basename='timetables')
# router.register(r'timetable-entries', TimetableEntryViewSet, basename='timetable-entries')
# router.register(r'holidays', HolidayViewSet, basename='holidays')
#get student for principle with filter [school filter add remainig]

# TIME TABLE
router.register(
    "timetable",
    TimeTableViewSet,
    basename="timetable"
)

router.register(r'get-student',GetStudentView,basename='get-student')

# FOR ATTENDANCE TRACKING METHOD [GET,POST,PUT,DELETE]
router.register(r'attendance', AttendanceView, basename='attendance') 

# router.register(r'announcements', AnnouncementView, basename='announcements')# For managing announcements
# router.register(r'get-announcements', GetAnnouncementView, basename='get-announcements')# For get announcement for student,staff with filter [school filter add remainig]   
router.register(r'razardata', RazarDataView, basename='razardata')# For get announcement for student,staff with filter [school filter add remainig]   

router.register(r'academic-year', AcademicYearViewSet, basename='academic-year') # For Only get
router.register(r'main-academic-year', AcademicYearMainView, basename='main-academic-year')

router.register(r'feetype', FeeTypeViewSet, basename='feetype')
router.register(r'fee-wise-class', FeeWiseClassViewSet, basename='fee-wise-class')

router.register(r'salary-component', SalaryComponentViewSet, basename='salary-component')
router.register(r'staff-list', StaffListView, basename='staff-list')
router.register(r'staff-salary-component', StaffSalaryComponentViewSet, basename='staff-salary-component')
router.register(r'staff-salary-payment', StaffSalaryPaymentViewSet, basename='staff-salary-payment')

router.register(r'student-fee', StudentFeeViewSet, basename='student-fee')
router.register(r'student-fee-payment', StudentFeePaymentViewSet, basename='student-fee-payment')
router.register(r'asset',AssetViewSet,basename='asset')
router.register(r'asset-maintenance',AssetMaintenanceViewSet,basename='asset-maintenance')
router.register(r'procurement',ProcurementViewSet,basename='procurement')
router.register(r'procurement-item',ProcurementItemViewSet,basename='procurement-item')
router.register(r'stock-items',StockItemsViewset,basename='stock-items')
router.register(r'stock-request',StockRequestViewset,basename='stock-request')
router.register(r'loss-prevention',LossPreventionViewset,basename='loss-prevention')
router.register(r'budget',BudgetViewset,basename='budget')
router.register(r'budget-expense',BudgetExpenseViewset,basename='budget-expense')
router.register(r'homework', HomeworkViewSet, basename='homework')
router.register(r'homework-submission', HomeworkSubmissionViewSet, basename='homework-submission')
router.register(r'studentget', StudentGetView, basename='studentget')



#FOR LOCATION AND TIME SET IN CLERK
router.register(r"attendance-location", AttendanceLocationViewSet, basename="attendance-location")



# for cerificate type to set
router.register(r"certificate-type", CertificateTypeSerializer, basename="certificate-type")

#student ask for certificate
router.register(r"certificate-request", CertificateRequestViewSet, basename="certificate-request")


router.register(r"clerk-certificate-request", ClerkCertificateRequestViewSet, basename="clerk-certificate-request")




router.register(r"leave-templates", LeaveTemplateViewSet, basename="leave-templates")

router.register(r"leave-types", LeaveTypeViewSet, basename="leave-types")

router.register(r'leave-request', LeaveRequestView, basename='leave-request') 

router.register(r'get-leave-requests', GetLeaveRequestView, basename='get-leave-requests')# For get leave request for clerk with filter [school filter add remainig]

router.register(r'change-leave-status', ChangeLeaveView, basename='change-leave-status')# For approve leave request for clerk METHOD [PUT]




# router.register(r'library-book-management', BookManageView, basename='library-book-management')

# router.register(r'late-book-fees', LateBookFeesViews, basename='late-book-fees')



# router.register(r'book-view-student', BookViewStudent, basename='book-view-student')




router.register(r"books/manage", BookManageView, basename="book-manage") # for add remove update or manage book by librarian

# Late fee policy: staff-side, one per school.
router.register(r"late-fees", LateBookFeesViews, basename="late-fees")

# Staff-side issuing + returning (counter operations).
# DRF auto-generates /book-issued/<id>/return/ from the @action below.
router.register(r"book-issued", BookIssuedView, basename="book-issued") #librarian see all book issued and status also issue book to someone and mark return

# Student-side read-only catalogue browsing.
router.register(r"books", BookViewStudent, basename="book-student") 

# Student-side issuing + own loan history.
# DRF auto-generates /my-books/<id>/return/ from the @action below.
router.register(r"my-books", BookIssueStudent, basename="book-issue-student")


router.register(r"reports", ReportsView, basename="report")






urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path('api/',include(router.urls)),
    path('api/dashboard-count/', DashboardCountAPIView.as_view(), name='dashboard-count'),
    path('api/access/',CustomLoginView.as_view()),  
    
    path('api/refresh/',TokenRefreshView.as_view()),
    
    #FOR ATTENDANCE LOCATION
    path('api/get-location/', GetLocationView.as_view()),
    # path('api/get-location/<int:pk>/', GetLocationView.as_view()),
    path('api/delete-location/<int:pk>/',DeleteUpdateLocationView.as_view()),
    
    path('api/api-login/', LoginView.as_view()),
    
    # path('school/<int:school_id>/', school_wise_report, name='school_wise_report'),
    
    path('api/send-otp/', SendOTPView.as_view()),
    path('api/verify-otp/', VerifyOTPView.as_view()),
    
    path('api/set-slot/', SetSlotView),
    
    # GET PUBLIC FROM DATA Fapi-03
    path('api/fields/', FormFieldViewSet.as_view()),
    
     path('api/admission/<uuid:unique_link>/',Admission_link.as_view()),#THIS API JUSR RETURN SCHOOL PERAMETER ###-----DONE
     
     path('api/admission/form/link/',ShareFormLink), #to get active form link for admission form fill up
     
     
     
     path('api/get-remaining-leaves/',GetStaffRemainingleave.as_view()),  # staff see remaining leave
     
     # To get remaining leave for staff when click on apply leave button for show remaining leave
     path('api/get-leave-requests-staff/',GetStaffLeaveRequest.as_view()),
     
     
     path("api/approve-all-leave/<int:pk>/",ChangeAllLeaveView.as_view()),
     path("api/announcement/",AnnouncementView.as_view()),
      path("api/announcement/<int:id>/", AnnouncementView.as_view()), 
     



    path('map/',TemplateView.as_view(template_name='map.html')),
    
    path('payment/',TemplateView.as_view(template_name='payment.html')),
    # path('log/',TemplateView.as_view(template_name='login.html')),
    
    # path('in/',TemplateView.as_view(template_name='index.html')),
    path('api/import-students/',upload_students.as_view()),
    path('api/today/',TodayAttendanceStatusView.as_view()),
    path('api/razor/order/',RazorpayOrderView.as_view()),
    path('api/payment/verify/',VerifyPaymentView.as_view()),
    path('api/my-fees/', MyStudentFeeView.as_view()),
    path('api/student-fee/razor/order/', StudentFeeRazorpayOrderView.as_view()),
    path('api/student-fee/razor/verify/', StudentFeeRazorpayVerifyView.as_view()),
    path('api/offline/payment/',OffilinePaymentView.as_view()),
    path('api/get_receipt/<int:student_id>/<int:form_id>/',get_receipt),
    path('api/schoollist/',SchoolListView.as_view()),
    path('face-enroll/',StaffFaceEnrollView.as_view()),
    path('face-verify/',StaffFaceVerifyView.as_view()),
    path('perstaff-leave/',GetRemainingLeavePerStaffView.as_view()),
    # path('homework-submission/',HomeworkSubmissionView.as_view()),
    path('api/student-documents/',StudentDocumentView.as_view()),
    path('api/exam-notification/',ExamView.as_view()),
    path('api/attendance-notification/',StudentNotificationView.as_view()),
    path('api/monthly-report/',MonthlyProgressReportView.as_view()),
    path('api/duefeesview/',DueFeesView.as_view()),
    path('api/payment-history/',PaymentHistoryView.as_view()),
    path('api/fee-payment/',FeesPaymentView.as_view()),
    path('api/verify-payment/',VerifypaymentView.as_view()),
    path('api/studymaterial/',StudyMaterialView.as_view()),
    path("teacher/classes/",TeacherClassesView.as_view()),
    
    # ITS FOR GET STIDENT FOR ATTENDANSE
    
    path(
        "api/get/attendance/students/",
        AttendanceStudentAPIView.as_view(),
        name="get-attendance-students"
    ),
    
    path(
        "api/student-attendance/",
        StudentAttendanceView.as_view(),
        name="student-attendance"
    ),
    
    
    path('api/specific-student-attendance/', StudentAttendanceListView.as_view()), # student see their attendance
    
    path('api/syllabus-student/', SyllabusListView.as_view()), # student see syallabus, for now study material
    
    
    
    path('api/classes/<int:class_id>/subjects/',SubjectByClassAPIView.as_view()), # in timetable first select class than subjects
    
    path('api/classes/',SchoolClassesView.as_view()), # classes to see for examtimetable
    
    
    
    
    
    path('api/exams/', ExamViewTeacher.as_view(), name="exam-list"), # GET  (Teacher: own class exams)
    
    path('api/examtimetable/', ExamCreateViewSet.as_view()), # teacher create timetable
    
    path('api/examtimetable-view/', ExamViewSet.as_view()), # student see exam timetable
    
    # path("exams/create/", ExamCreateViewSet.as_view(), name="exam-create"),      # POST (teacher/principal)
 
    # ---- Results: teacher side ----
    path('api/results/bulk-save/', ResultBulkCreateViewSet.as_view(), name="result-bulk-save"),
    # POST -> create/update marks for a class (upsert, always unpublished on edit)
    
    # path("results/", ResultViewTeacher.as_view()),
    path('api/results/roster/<int:exam_id>/', ExamResultRosterView.as_view(), name="result-roster"),
    # GET -> class roster + existing marks (prefill grid)
 
 
    path('api/results/publish/', ResultPublishViewSet.as_view(), name="result-publish"),
    # POST { "exam": <id> } -> publish all results for that exam
 
 
    path('api/results/rank/<int:exam_id>/', ExamRankListView.as_view(), name="result-rank"),
    # GET -> class-wise ranked list for an exam
 
    # ---- Results: student side ----
    path('api/results/my-results/', StudentResultViewSet.as_view(), name="student-results"),
    # GET -> logged-in student's published results
 
    path('api/results/report-card/<int:student_id>/', StudentResultPDFView.as_view(), name="result-pdf"),
    # GET -> downloadable PDF report card
    
    
    
    
    
    # path('api/razardata/',RazarDataView.as_view()),
    
    path('api/webhook/',RazorpayWebhookView.as_view()),
    
    path('payfee/',TemplateView.as_view(template_name='textfee.html')),
     # Swagger UI
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0)),

    # Redoc UI (optional)
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0)),

    # JSON/YAML schema
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0)),

]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )

 
