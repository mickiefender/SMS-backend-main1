"""
Redis-based Real-time Notifications Service

Provides:
- Redis pub/sub for real-time notifications
- WebSocket notification broadcasting
- Push notification queue management
"""
import json
import logging
from typing import Dict, List, Optional, Any
from django.conf import settings

logger = logging.getLogger(__name__)


class RedisPubSubManager:
    """Manages Redis pub/sub for real-time notifications"""
    
    def __init__(self):
        self.redis_client = None
        self.pubsub = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Redis client for pub/sub"""
        try:
            import redis
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            self.pubsub = self.redis_client.pubsub()
            logger.info("Redis pub/sub client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Redis pub/sub client: {e}")
            self.redis_client = None
            self.pubsub = None
    
    def publish(self, channel: str, message: Dict[str, Any]) -> bool:
        """
        Publish a message to a Redis channel
        
        Args:
            channel: The channel name to publish to
            message: The message dict to publish
            
        Returns:
            True if successful, False otherwise
        """
        if not self.redis_client:
            logger.warning("Redis client not initialized, skipping publish")
            return False
        
        try:
            self.redis_client.publish(
                channel,
                json.dumps(message, default=str)
            )
            logger.debug(f"Published message to channel {channel}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish to channel {channel}: {e}")
            return False
    
    def subscribe(self, channel: str):
        """Subscribe to a Redis channel"""
        if not self.pubsub:
            logger.warning("Redis pubsub not initialized")
            return
        
        try:
            self.pubsub.subscribe(channel)
            logger.info(f"Subscribed to channel: {channel}")
        except Exception as e:
            logger.error(f"Failed to subscribe to channel {channel}: {e}")
    
    def unsubscribe(self, channel: str):
        """Unsubscribe from a Redis channel"""
        if not self.pubsub:
            return
        
        try:
            self.pubsub.unsubscribe(channel)
        except Exception as e:
            logger.error(f"Failed to unsubscribe from channel {channel}: {e}")
    
    def get_messages(self, timeout: float = 0.1):
        """Get messages from subscribed channels"""
        if not self.pubsub:
            return []
        
        try:
            message = self.pubsub.get_message(timeout=timeout)
            if message and message['type'] == 'message':
                return json.loads(message['data'])
        except Exception as e:
            logger.error(f"Error getting pub/sub message: {e}")
        
        return []


class NotificationService:
    """
    Service for managing real-time notifications via Redis
    """
    
    # Channel templates
    USER_NOTIFICATION_CHANNEL = "notifications:user:{user_id}"
    SCHOOL_CHANNEL = "notifications:school:{school_id}"
    CLASS_CHANNEL = "notifications:class:{class_id}"
    GLOBAL_CHANNEL = "notifications:global"
    
    def __init__(self):
        self.pubsub_manager = RedisPubSubManager()
    
    def _get_user_channel(self, user_id: int) -> str:
        """Get the notification channel for a specific user"""
        return self.USER_NOTIFICATION_CHANNEL.format(user_id=user_id)
    
    def _get_school_channel(self, school_id: int) -> str:
        """Get the notification channel for a school"""
        return self.SCHOOL_CHANNEL.format(school_id=school_id)
    
    def _get_class_channel(self, class_id: int) -> str:
        """Get the notification channel for a class"""
        return self.CLASS_CHANNEL.format(class_id=class_id)
    
    def send_notification(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        priority: str = "normal"
    ) -> bool:
        """
        Send a notification to a specific user
        
        Args:
            user_id: The user ID to send the notification to
            notification_type: Type of notification (e.g., 'fee', 'assignment', 'announcement')
            title: Notification title
            message: Notification message
            data: Additional data to include
            priority: Priority level ('low', 'normal', 'high', 'urgent')
            
        Returns:
            True if successful, False otherwise
        """
        notification = {
            'type': 'notification',
            'notification_type': notification_type,
            'title': title,
            'message': message,
            'data': data or {},
            'priority': priority,
            'timestamp': str(__import__('datetime').datetime.now()),
        }
        
        # Send to user's personal channel
        user_channel = self._get_user_channel(user_id)
        success = self.pubsub_manager.publish(user_channel, notification)
        
        # Also store in Redis for persistence
        self._store_notification(user_id, notification)
        
        return success
    
    def send_school_notification(
        self,
        school_id: int,
        notification_type: str,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        target_roles: Optional[List[str]] = None
    ) -> bool:
        """
        Send a notification to all users in a school
        
        Args:
            school_id: The school ID
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            data: Additional data
            target_roles: Optional list of roles to target (e.g., ['teacher', 'student'])
        """
        notification = {
            'type': 'school_notification',
            'school_id': school_id,
            'notification_type': notification_type,
            'title': title,
            'message': message,
            'data': data or {},
            'target_roles': target_roles or [],
            'timestamp': str(__import__('datetime').datetime.now()),
        }
        
        # Publish to school channel
        school_channel = self._get_school_channel(school_id)
        return self.pubsub_manager.publish(school_channel, notification)
    
    def send_class_notification(
        self,
        class_id: int,
        notification_type: str,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send a notification to all users in a class"""
        notification = {
            'type': 'class_notification',
            'class_id': class_id,
            'notification_type': notification_type,
            'title': title,
            'message': message,
            'data': data or {},
            'timestamp': str(__import__('datetime').datetime.now()),
        }
        
        class_channel = self._get_class_channel(class_id)
        return self.pubsub_manager.publish(class_channel, notification)
    
    def _store_notification(self, user_id: int, notification: Dict[str, Any]) -> bool:
        """Store notification in Redis for later retrieval"""
        if not self.pubsub_manager.redis_client:
            return False
        
        try:
            import redis
            from django.conf import settings
            
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            r = redis.from_url(redis_url, decode_responses=True)
            
            # Store in a list, keeping only the last 100 notifications
            key = f"user_notifications:{user_id}"
            r.lpush(key, json.dumps(notification))
            r.ltrim(key, 0, 99)  # Keep only 100 most recent
            
            # Set expiry for 30 days
            r.expire(key, 30 * 24 * 60 * 60)
            
            return True
        except Exception as e:
            logger.error(f"Failed to store notification: {e}")
            return False
    
    def get_user_notifications(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get stored notifications for a user"""
        if not self.pubsub_manager.redis_client:
            return []
        
        try:
            import redis
            from django.conf import settings
            
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            r = redis.from_url(redis_url, decode_responses=True)
            
            key = f"user_notifications:{user_id}"
            notifications = r.lrange(key, offset, offset + limit - 1)
            
            return [json.loads(n) for n in notifications]
        except Exception as e:
            logger.error(f"Failed to get user notifications: {e}")
            return []
    
    def mark_notification_read(self, user_id: int, notification_index: int) -> bool:
        """Mark a notification as read"""
        if not self.pubsub_manager.redis_client:
            return False
        
        try:
            import redis
            from django.conf import settings
            
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            r = redis.from_url(redis_url, decode_responses=True)
            
            # Add to read set
            key = f"user_notifications_read:{user_id}"
            r.sadd(key, notification_index)
            r.expire(key, 30 * 24 * 60 * 60)
            
            return True
        except Exception as e:
            logger.error(f"Failed to mark notification as read: {e}")
            return False
    
    def get_unread_count(self, user_id: int) -> int:
        """Get the count of unread notifications for a user"""
        if not self.pubsub_manager.redis_client:
            return 0
        
        try:
            import redis
            from django.conf import settings
            
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            r = redis.from_url(redis_url, decode_responses=True)
            
            # Check cache first
            cache_key = f"unread_count:{user_id}"
            cached = r.get(cache_key)
            if cached:
                return int(cached)
            
            # Calculate from stored notifications
            notifications_key = f"user_notifications:{user_id}"
            read_key = f"user_notifications_read:{user_id}"
            
            total = r.llen(notifications_key)
            read_count = r.scard(read_key)
            unread = total - read_count
            
            # Cache for 30 seconds
            r.setex(cache_key, 30, unread)
            
            return max(0, unread)
        except Exception as e:
            logger.error(f"Failed to get unread count: {e}")
            return 0
    
    def clear_user_notifications(self, user_id: int) -> bool:
        """Clear all notifications for a user"""
        if not self.pubsub_manager.redis_client:
            return False
        
        try:
            import redis
            from django.conf import settings
            
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            r = redis.from_url(redis_url, decode_responses=True)
            
            keys = [
                f"user_notifications:{user_id}",
                f"user_notifications_read:{user_id}",
                f"unread_count:{user_id}",
            ]
            
            r.delete(*keys)
            return True
        except Exception as e:
            logger.error(f"Failed to clear user notifications: {e}")
            return False


# Singleton instance
notification_service = NotificationService()


# Helper functions for common notification types

def notify_fee_payment(user_id: int, amount: str, fee_name: str, school_name: str):
    """Send fee payment notification"""
    notification_service.send_notification(
        user_id=user_id,
        notification_type='fee_payment',
        title='Payment Received',
        message=f'Payment of {amount} for {fee_name} has been recorded.',
        data={'amount': amount, 'fee_name': fee_name, 'school_name': school_name},
        priority='normal'
    )


def notify_new_assignment(user_id: int, assignment_title: str, due_date: str):
    """Send new assignment notification"""
    notification_service.send_notification(
        user_id=user_id,
        notification_type='assignment',
        title='New Assignment',
        message=f'You have a new assignment: {assignment_title}. Due: {due_date}',
        data={'assignment_title': assignment_title, 'due_date': due_date},
        priority='high'
    )


def notify_announcement(school_id: int, title: str, message: str):
    """Send school-wide announcement notification"""
    notification_service.send_school_notification(
        school_id=school_id,
        notification_type='announcement',
        title=title,
        message=message
    )


def notify_grade_posted(user_id: int, subject_name: str, grade: str):
    """Send grade posted notification"""
    notification_service.send_notification(
        user_id=user_id,
        notification_type='grade',
        title='Grade Posted',
        message=f'Your grade for {subject_name} has been posted: {grade}',
        data={'subject_name': subject_name, 'grade': grade},
        priority='normal'
    )


def notify_attendance_marked(user_id: int, date: str, status: str):
    """Send attendance notification"""
    notification_service.send_notification(
        user_id=user_id,
        notification_type='attendance',
        title='Attendance Marked',
        message=f'Your attendance for {date} has been marked: {status}',
        data={'date': date, 'status': status},
        priority='low'
    )


def notify_fee_reminder(user_id: int, fee_name: str, amount: str, due_date: str, days_until: int):
    """Send fee due date reminder notification"""
    notification_service.send_notification(
        user_id=user_id,
        notification_type='fee_reminder',
        title='Fee Payment Reminder',
        message=f'Reminder: {fee_name} fee of {amount} is due in {days_until} day(s) on {due_date}',
        data={'fee_name': fee_name, 'amount': amount, 'due_date': due_date, 'days_until': days_until},
        priority='high'
    )

