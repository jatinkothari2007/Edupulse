"""
EduPulse AI Messenger — Uses Anthropic Claude API to generate
personalised messages for students based on their situation.
"""
import os
try:
    import anthropic as _anthropic
except ImportError:
    _anthropic = None
from firebase_config import db
from firebase_admin import firestore
import uuid


def _claude(prompt: str) -> str:
    """Call Claude API and return text response."""
    try:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key or _anthropic is None:
            return "We noticed you might need some support. Please reach out to your faculty advisor or counsellor."
        client = _anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        return "We're thinking of you. Please reach out if you need support."



def _save_ai_chat_message(student_uid: str, message_text: str):
    """Save AI message to a special AI conversation in Firestore."""
    conv_id = f"ai_{student_uid}"
    db.collection('conversations').document(conv_id).set({
        'participants': [student_uid, 'SYSTEM_AI'],
        'lastMessage': message_text[:100],
        'lastTimestamp': firestore.SERVER_TIMESTAMP,
        'isAI': True,
    }, merge=True)
    db.collection('conversations').document(conv_id) \
      .collection('messages').add({
          'id': str(uuid.uuid4()),
          'senderId': 'SYSTEM_AI',
          'senderName': 'EduPulse AI',
          'text': message_text,
          'encrypted': False,
          'timestamp': firestore.SERVER_TIMESTAMP,
          'isRead': False,
      })


def send_missed_class_message(student_uid: str, student_name: str, missed_count: int):
    prompt = (
        f"A student named {student_name} has missed {missed_count} consecutive classes. "
        "Write a short, warm, caring message (2-3 sentences) encouraging them to attend. "
        "Do not be harsh. Be genuinely concerned and supportive."
    )
    msg = _claude(prompt)
    _save_ai_chat_message(student_uid, msg)
    from utils.notifier import notify_ai_message
    notify_ai_message(student_uid, "Attendance Check-in", msg)


def send_missed_assignment_message(student_uid: str, student_name: str, assignment_title: str, due_date: str):
    prompt = (
        f"A student named {student_name} missed submitting their assignment '{assignment_title}' "
        f"which was due on {due_date}. Write a gentle reminder (2-3 sentences) encouraging submission "
        "or reaching out if they need help."
    )
    msg = _claude(prompt)
    _save_ai_chat_message(student_uid, msg)
    from utils.notifier import notify_ai_message
    notify_ai_message(student_uid, "Assignment Reminder", msg)


def send_missed_quiz_message(student_uid: str, student_name: str, quiz_date: str):
    prompt = (
        f"A student named {student_name} did not take their scheduled Pulse Quiz on {quiz_date}. "
        "Write a short caring message (2 sentences) reminding them of its importance for their wellbeing tracking."
    )
    msg = _claude(prompt)
    _save_ai_chat_message(student_uid, msg)
    from utils.notifier import notify_ai_message
    notify_ai_message(student_uid, "Pulse Quiz Reminder", msg)


def send_low_mood_message(student_uid: str, student_name: str, consecutive_days: int):
    prompt = (
        f"A student named {student_name} has reported low mood for {consecutive_days} consecutive days. "
        "Write a very warm, empathetic, supportive message (2-3 sentences) checking in on them "
        "and encouraging them to reach out to their counsellor."
    )
    msg = _claude(prompt)
    _save_ai_chat_message(student_uid, msg)
    from utils.notifier import notify_ai_message
    notify_ai_message(student_uid, "Wellbeing Check-in", msg)


def send_high_risk_message(student_uid: str, student_name: str, risk_score: float):
    prompt = (
        f"A student named {student_name} has a high academic risk score of {risk_score}/100. "
        "Write an encouraging, non-alarming message (2-3 sentences) motivating them to improve "
        "and reminding them support is available."
    )
    msg = _claude(prompt)
    _save_ai_chat_message(student_uid, msg)
    from utils.notifier import notify_ai_message
    notify_ai_message(student_uid, "Academic Support", msg)


def generate_quiz_questions(class_context: str = "") -> list:
    """
    Generate 10 case-based wellbeing quiz questions using Claude.
    Returns a list of {question, options:[a,b,c,d], correct} dicts.
    """
    prompt = (
        "Generate 10 case-based questions for a student wellbeing quiz. "
        "Questions should be personal and social in nature — about stress management, "
        "peer relationships, time management, emotional situations, and academic pressure. "
        "NOT academic subject questions. Each question should have 4 options. "
        'Format as a JSON array exactly like this: '
        '[{"question": "...", "options": {"a": "...", "b": "...", "c": "...", "d": "..."}, "correct": "a"}] '
        "Make questions thoughtful but not hard. Time limit is 10 minutes for all 10. "
        "Return ONLY the JSON array, no other text."
    )
    try:
        import json
        raw = _claude(prompt)
        # Extract JSON from response
        start = raw.find('[')
        end   = raw.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception:
        pass
    # Fallback questions
    return [
        {"question": "When you feel overwhelmed with assignments, what is the healthiest approach?",
         "options": {"a": "Ignore them and rest", "b": "Make a priority list and tackle one at a time",
                     "c": "Stay up all night", "d": "Ask a friend to do them"},
         "correct": "b"},
        {"question": "A friend seems upset but won't talk about it. What do you do?",
         "options": {"a": "Leave them alone completely", "b": "Tell others about it",
                     "c": "Gently let them know you're available", "d": "Force them to talk"},
         "correct": "c"},
        {"question": "You're stressed before an exam. Which technique helps most?",
         "options": {"a": "Cramming all night", "b": "Deep breathing and short study sessions",
                     "c": "Skipping sleep to study", "d": "Avoiding all study"},
         "correct": "b"},
        {"question": "How do you best handle a disagreement with a peer?",
         "options": {"a": "Shout until they agree", "b": "Avoid them forever",
                     "c": "Listen to their perspective and calmly share yours", "d": "Gossip about it"},
         "correct": "c"},
        {"question": "You missed an important deadline. What's the best step?",
         "options": {"a": "Hope no one notices", "b": "Make excuses",
                     "c": "Contact your teacher and explain honestly", "d": "Drop the course"},
         "correct": "c"},
        {"question": "What is the most effective way to manage your study time?",
         "options": {"a": "Study only when you feel like it", "b": "Create a consistent schedule",
                     "c": "Study all subjects at once", "d": "Only study the night before exams"},
         "correct": "b"},
        {"question": "Feeling lonely at college is:",
         "options": {"a": "A sign of weakness", "b": "Something to be ashamed of",
                     "c": "Common and worth addressing by joining activities", "d": "Permanent"},
         "correct": "c"},
        {"question": "A good way to balance social life and studies is:",
         "options": {"a": "Sacrifice one completely", "b": "Never take breaks",
                     "c": "Set boundaries and schedule both", "d": "Let studies suffer"},
         "correct": "c"},
        {"question": "When facing academic pressure, seeking counselling is:",
         "options": {"a": "A sign of failure", "b": "Unnecessary", "c": "A sign of strength and self-awareness", "d": "Only for severe problems"},
         "correct": "c"},
        {"question": "The best response to consistent procrastination is:",
         "options": {"a": "Accept it as your personality", "b": "Punish yourself", 
                     "c": "Break tasks into small steps and set timers", "d": "Ask others to force you"},
         "correct": "c"},
    ]
