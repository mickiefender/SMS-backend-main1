from rest_framework.pagination import CursorPagination


class FeedCursorPagination(CursorPagination):
    """
    Cursor pagination optimized for chronological and ranked feeds.
    Views override ordering when the request uses recommendations.
    """
    page_size = 12
    ordering = ('-published_at', '-pk')
    cursor_query_param = 'cursor'


class TrendingCursorPagination(CursorPagination):
    page_size = 12
    ordering = ('-trending_score', '-published_at', '-pk')
    cursor_query_param = 'cursor'


class CommentCursorPagination(CursorPagination):
    page_size = 20
    ordering = '-is_pinned', '-created_at'
    cursor_query_param = 'cursor'
