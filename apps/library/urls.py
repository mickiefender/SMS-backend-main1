from rest_framework.routers import DefaultRouter

from apps.library.views import LibraryBookViewSet, LibraryCategoryViewSet, LibraryLoanViewSet

router = DefaultRouter()
router.register('categories', LibraryCategoryViewSet, basename='library-category')
router.register('books', LibraryBookViewSet, basename='library-book')
router.register('loans', LibraryLoanViewSet, basename='library-loan')

urlpatterns = router.urls
