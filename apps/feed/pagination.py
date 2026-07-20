from rest_framework.pagination import CursorPagination


class FeedCursorPagination(CursorPagination):
    """
    Cursor pagination optimized for infinite scrolling feeds.
    Default ordering is by `-published_at` (newest first).
    """
    page_size = 12
    ordering = '-published_at'
    cursor_query_param = 'cursor'


class TrendingCursorPagination(CursorPagination):
    page_size = 12
    ordering = '-trending_score'
    cursor_query_param = 'cursor'


class CommentCursorPagination(CursorPagination):
    page_size = 20
    ordering = '-is_pinned', '-created_at'
    cursor_query_param = 'cursor'
