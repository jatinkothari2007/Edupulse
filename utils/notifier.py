"""
EduPulse Notification Sender.
Writes notification documents to Firestore.
Real-time onSnapshot listeners on the frontend pick them up.
"""
import uuid
from datetime import datetime
from firebase_config import db
from firebase_admin import firestore


def send_notification(
    to_uid:     str,
    notif_type: str,
    title:      str,
    message:    str,
    from_uid:   str  = None,
    from_role:  str  = None,
    priority:   str  = 'medium',
    play_sound: bool = True,
    action_url: str  = None,
) -> str:
    """
    Sends a notification to a user.
    Returns the notification document ID.
    """
    notif_id = str(uuid.uuid4())
    db.collection('notifications') \
      .document(to_uid) \
      .collection('items') \
      .document(notif_id) \
      .set({
          'id'        : notif_id,
          'type'      : notif_type,
          'title'     : title,
          'message'   : message,
          'fromUserId': from_uid,
          'fromRole'  : from_role,
          'priority'  : priority,
          'isRead'    : False,
          'sound'     : play_sound,
          'createdAt' : firestore.SERVER_TIMESTAMP,
          'actionUrl' : action_url,
      })
    return notif_id


def notify_risk_alert(fa_uid: str, student_name: str, level: str, score: float, student_id: str):
    if level == 'HIGH':
        send_notification(
            to_uid=fa_uid,
            notif_type='risk_high',
            title='🔴 High Risk Alert',
            message=f'{student_name} has a HIGH risk score of {score}/100. Immediate attention needed.',
            priority='critical',
            play_sound=True,
            action_url='/pages/faculty/risk-scores',
        )
    elif level == 'MEDIUM':
        send_notification(
            to_uid=fa_uid,
            notif_type='risk_medium',
            title='🟡 Medium Risk Alert',
            message=f'{student_name} has a MEDIUM risk score of {score}/100.',
            priority='high',
            play_sound=True,
            action_url='/pages/faculty/risk-scores',
        )


def notify_risk_declined(fa_uid: str, student_name: str, old_score: float, new_score: float):
    send_notification(
        to_uid=fa_uid,
        notif_type='risk_declined',
        title='📉 Risk Score Declined',
        message=f'{student_name}\'s risk score worsened from {old_score} → {new_score}.',
        priority='high',
        play_sound=True,
        action_url='/pages/faculty/risk-scores',
    )


def notify_case_closed(fa_uid: str, student_name: str, closing_message: str):
    send_notification(
        to_uid=fa_uid,
        notif_type='case_closed',
        title='📋 Counselling Case Closed',
        message=f'Counsellor has closed case for {student_name}. Review required.',
        priority='high',
        play_sound=True,
        action_url='/pages/faculty/classes',
    )


def notify_quiz_scheduled(student_uid: str, quiz_title: str, scheduled_at: str):
    send_notification(
        to_uid=student_uid,
        notif_type='quiz_scheduled',
        title='📝 Pulse Quiz Scheduled',
        message=f'A new Pulse Quiz has been scheduled for {scheduled_at}.',
        priority='medium',
        play_sound=True,
        action_url='/pages/student/quiz',
    )


def notify_assignment_created(student_uid: str, title: str, due_date: str):
    send_notification(
        to_uid=student_uid,
        notif_type='assignment_created',
        title='📚 New Assignment',
        message=f'New assignment "{title}" due on {due_date}.',
        priority='medium',
        play_sound=True,
        action_url='/pages/student/assignments',
    )


def notify_video_call_scheduled(student_uid: str, counsellor_name: str, session_time: str):
    send_notification(
        to_uid=student_uid,
        notif_type='video_call_scheduled',
        title='📹 Video Call Scheduled',
        message=f'Your counsellor {counsellor_name} has scheduled a video session at {session_time}.',
        priority='high',
        play_sound=True,
        action_url='/pages/student/videocall',
    )


def notify_message_received(to_uid: str, from_name: str, preview: str):
    send_notification(
        to_uid=to_uid,
        notif_type='message_received',
        title=f'💬 Message from {from_name}',
        message=preview[:80] + ('…' if len(preview) > 80 else ''),
        priority='medium',
        play_sound=True,
        action_url='/pages/messaging',
    )


def notify_ai_message(student_uid: str, title: str, message: str):
    send_notification(
        to_uid=student_uid,
        notif_type='ai_message',
        title=f'🤖 {title}',
        message=message,
        priority='medium',
        play_sound=True,
        action_url='/pages/messaging',
    )
