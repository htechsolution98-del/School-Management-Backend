import logging
from django.core.cache import cache
from rest_framework.response import Response

logger = logging.getLogger(__name__)

def get_library_school_version(school_id: int) -> int:
    """Get the current cache version for a specific school's library."""
    key = f"lib_ver_{school_id}"
    try:
        ver = cache.get(key)
        if ver is None:
            cache.set(key, 1, timeout=86400 * 30)
            return 1
        return int(ver)
    except Exception as e:
        logger.warning(f"Error reading library cache version: {e}")
        return 1

def invalidate_library_school_cache(school_id: int) -> None:
    """
    Atomically invalidates all cached library data (books, loans, masters, stats)
    for this school by incrementing its version counter.
    Works seamlessly on both Redis and local memory cache.
    """
    if not school_id:
        return
    key = f"lib_ver_{school_id}"
    try:
        try:
            cache.incr(key)
        except Exception:
            current = cache.get(key) or 1
            cache.set(key, int(current) + 1, timeout=86400 * 30)
        logger.info(f"Invalidated library cache for school_id={school_id}")
    except Exception as e:
        logger.warning(f"Error invalidating library cache: {e}")

def get_library_cached_data(school_id: int, scope: str, params_str: str = ""):
    """Fetch cached library data for the given school, scope, and query parameters."""
    if not school_id:
        return None
    ver = get_library_school_version(school_id)
    cache_key = f"lib_{scope}_{school_id}_v{ver}_{params_str}"
    try:
        return cache.get(cache_key)
    except Exception as e:
        logger.warning(f"Library cache read error: {e}")
        return None

def set_library_cached_data(school_id: int, scope: str, data, params_str: str = "", timeout: int = 300):
    """Cache library data for the given school, scope, and query parameters."""
    if not school_id or data is None:
        return
    ver = get_library_school_version(school_id)
    cache_key = f"lib_{scope}_{school_id}_v{ver}_{params_str}"
    try:
        cache.set(cache_key, data, timeout=timeout)
    except Exception as e:
        logger.warning(f"Library cache write error: {e}")

class CachedLibraryViewSetMixin:
    """
    Mixin for ModelViewSets to automatically cache list responses in Redis / LocMemCache
    and invalidate caches on any create, update, or delete operations.
    """
    cache_scope = "generic"

    def list(self, request, *args, **kwargs):
        from sms_app.models import Staff
        staff = Staff.objects.filter(user=request.user).first()
        if staff and staff.school:
            cached = get_library_cached_data(staff.school.id, self.cache_scope, request.GET.urlencode())
            if cached is not None:
                return Response(cached)
        
        response = super().list(request, *args, **kwargs)
        if staff and staff.school and response.status_code == 200:
            set_library_cached_data(staff.school.id, self.cache_scope, response.data, request.GET.urlencode())
        return response

    def perform_create(self, serializer):
        super().perform_create(serializer)
        from sms_app.models import Staff
        staff = Staff.objects.filter(user=self.request.user).first()
        if staff and staff.school:
            invalidate_library_school_cache(staff.school.id)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        from sms_app.models import Staff
        staff = Staff.objects.filter(user=self.request.user).first()
        if staff and staff.school:
            invalidate_library_school_cache(staff.school.id)

    def perform_destroy(self, instance):
        from sms_app.models import Staff
        staff = Staff.objects.filter(user=self.request.user).first()
        super().perform_destroy(instance)
        if staff and staff.school:
            invalidate_library_school_cache(staff.school.id)
