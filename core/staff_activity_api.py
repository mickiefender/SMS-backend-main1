"""
Core API - Staff activity summary for the admin-staff dashboard.

GET /api/core/staff-activity/weekly/
    Returns the requesting staff member's real recorded activity over the
    last 7 days, grouped per day and action type, plus their most recent
    individual actions.
"""
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import StaffActivityLog

DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


class StaffActivityWeeklyView(APIView):
    """Weekly activity breakdown + recent actions for the current user."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        # 6 days ago .. today (inclusive) = a rolling 7-day window.
        window_start = (now - timedelta(days=6)).date()

        logs = StaffActivityLog.objects.filter(
            user=request.user,
            created_at__gte=window_start,
        )

        counts = (
            logs.annotate(day=TruncDate('created_at'))
            .values('day', 'action_type')
            .annotate(total=Count('id'))
        )

        by_day = {
            (window_start + timedelta(days=i)): {'tasks': 0, 'approvals': 0}
            for i in range(7)
        }
        for row in counts:
            entry = by_day.get(row['day'])
            if entry is None:
                continue
            if row['action_type'] == 'approval':
                entry['approvals'] = row['total']
            else:
                entry['tasks'] = row['total']

        weekly = [
            {
                'day': DAY_LABELS[date.weekday()],
                'tasks': entry['tasks'],
                'approvals': entry['approvals'],
            }
            for date, entry in sorted(by_day.items())
        ]

        recent = [
            {
                'id': log.id,
                'title': log.title,
                'action_type': log.action_type,
                'created_at': log.created_at,
            }
            for log in logs.order_by('-created_at')[:5]
        ]

        return Response({
            'weekly': weekly,
            'recent': recent,
            'totals': {
                'tasks': sum(d['tasks'] for d in weekly),
                'approvals': sum(d['approvals'] for d in weekly),
            },
        })
