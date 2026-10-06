from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sms_app.library_leave_views import (
    LibrarySettingViewSet,
    BookCategoryViewSet,
    AuthorViewSet,
    PublisherViewSet,
    RackViewSet,
    ShelfViewSet,
    BookCopyViewSet,
    BookReservationViewSet,
    LateBookFeesViews,
    BookIssuedView,
)

router = DefaultRouter()
router.register(r"settings", LibrarySettingViewSet, basename="library-settings")
router.register(r"categories", BookCategoryViewSet, basename="book-categories")
router.register(r"authors", AuthorViewSet, basename="authors")
router.register(r"publishers", PublisherViewSet, basename="publishers")
router.register(r"racks", RackViewSet, basename="racks")
router.register(r"shelves", ShelfViewSet, basename="shelves")
router.register(r"book-copies", BookCopyViewSet, basename="book-copies")
router.register(r"reservations", BookReservationViewSet, basename="book-reservations")
router.register(r"issued-books", BookIssuedView, basename="issued-books")

urlpatterns = [
    path("api/v1/library/", include(router.urls)),
]
