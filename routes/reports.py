"""
EduPulse Reports Routes — PDF generation using ReportLab.
"""
from flask import Blueprint, jsonify, Response, request, g
from firebase_config import db
from routes.auth_middleware import require_auth, require_role
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from io import BytesIO
import datetime

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reports')

_PURPLE = colors.HexColor('#7B2FFF')
_MINT   = colors.HexColor('#2DD4BF')
_RED    = colors.HexColor('#EF4444')
_AMBER  = colors.HexColor('#F59E0B')
_GREEN  = colors.HexColor('#10B981')
_LIGHT  = colors.HexColor('#F5F3FF')


def _risk_colour(level):
    return {'HIGH': _RED, 'MEDIUM': _AMBER, 'LOW': _GREEN}.get(level, _PURPLE)


@reports_bp.route('/student/<student_uid>', methods=['GET'])
@require_auth
def student_report(student_uid):
    role = g.user_data.get('role', '')
    if role not in ('admin', 'faculty_advisor', 'counsellor') and g.uid != student_uid:
        return jsonify({'error': 'Forbidden'}), 403

    user_doc = db.collection('users').document(student_uid).get()
    risk_doc = db.collection('riskScores').document(student_uid).get()
    if not user_doc.exists:
        return jsonify({'error': 'Student not found'}), 404

    u = user_doc.to_dict()
    r = risk_doc.to_dict() if risk_doc.exists else {}

    # Collect marks
    marks_docs = db.collection('marks').where('studentId', '==', student_uid).stream()
    marks = [d.to_dict() for d in marks_docs]

    # Collect attendance
    att_docs = db.collection('attendance').where('studentId', '==', student_uid).stream()
    att_records = [d.to_dict() for d in att_docs]

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    # Title
    title_style = ParagraphStyle('ETitle', parent=styles['Title'],
                                 fontSize=22, textColor=_PURPLE,
                                 spaceAfter=4)
    story.append(Paragraph("EduPulse — Student Report", title_style))
    story.append(HRFlowable(width="100%", color=_PURPLE, thickness=2))
    story.append(Spacer(1, 12))

    # Student info
    info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=11, leading=16)
    story.append(Paragraph(f"<b>Name:</b> {u.get('name', '')}", info_style))
    story.append(Paragraph(f"<b>Student ID:</b> {u.get('customId', '')}", info_style))
    story.append(Paragraph(f"<b>Email:</b> {u.get('email', '')}", info_style))
    story.append(Paragraph(f"<b>Class:</b> {u.get('classId', '')}", info_style))
    story.append(Paragraph(f"<b>Report Date:</b> {datetime.date.today().isoformat()}", info_style))
    story.append(Spacer(1, 12))

    # Risk summary
    level = r.get('level', 'N/A')
    score = r.get('score', 0)
    rc    = _risk_colour(level)
    story.append(Paragraph("Risk Score Summary", ParagraphStyle('H2',
        parent=styles['Heading2'], textColor=_PURPLE, spaceAfter=6)))
    risk_data = [['Risk Score', 'Level', 'Trend']]
    risk_data.append([str(score), level, r.get('trend', 'stable')])
    risk_table = Table(risk_data, colWidths=[5*cm, 5*cm, 5*cm])
    risk_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), _PURPLE),
        ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
        ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 0), (-1, 0), 11),
        ('BACKGROUND', (0, 1), (-1, 1), _LIGHT),
        ('TEXTCOLOR',  (0, 1), (0, 1), rc),
        ('FONTNAME',   (0, 1), (0, 1), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 1), (-1, 1), 12),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [_LIGHT]),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(risk_table)
    story.append(Spacer(1, 12))

    # Breakdown
    breakdown = r.get('breakdown', {})
    if breakdown:
        story.append(Paragraph("Factor Breakdown", ParagraphStyle('H2',
            parent=styles['Heading2'], textColor=_PURPLE, spaceAfter=6)))
        bd_data = [['Factor', 'Score', 'Weight']]
        factor_labels = {
            'examScore'      : ('Exam Marks', '30%'),
            'attendanceScore': ('Attendance', '20%'),
            'submissionScore': ('Assignment Submission', '15%'),
            'quizScore'      : ('Pulse Quiz', '15%'),
            'moodScore'      : ('Mood Map', '10%'),
            'engagementScore': ('App Engagement', '7%'),
            'gradeScore'     : ('Avg Grade', '3%'),
        }
        for key, (label, weight) in factor_labels.items():
            bd_data.append([label, f"{breakdown.get(key, 0):.1f}", weight])
        bd_table = Table(bd_data, colWidths=[8*cm, 4*cm, 4*cm])
        bd_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _PURPLE),
            ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
            ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _LIGHT]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(bd_table)
        story.append(Spacer(1, 12))

    # Recommendations
    recs = r.get('recommendations', [])
    if recs:
        story.append(Paragraph("Recommendations", ParagraphStyle('H2',
            parent=styles['Heading2'], textColor=_PURPLE, spaceAfter=6)))
        for rec in recs:
            story.append(Paragraph(f"• {rec}", info_style))
        story.append(Spacer(1, 12))

    # Marks table
    if marks:
        story.append(Paragraph("Academic Marks", ParagraphStyle('H2',
            parent=styles['Heading2'], textColor=_PURPLE, spaceAfter=6)))
        m_data = [['Subject', 'Component', 'Marks', 'Max', '%']]
        for m in marks[:20]:
            pct = f"{m['marks']/m['maxMarks']*100:.1f}" if m.get('maxMarks') else '-'
            m_data.append([
                m.get('subjectId', ''),
                m.get('component', ''),
                str(m.get('marks', '')),
                str(m.get('maxMarks', '')),
                pct,
            ])
        m_table = Table(m_data, colWidths=[4*cm, 4*cm, 3*cm, 3*cm, 3*cm])
        m_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _MINT),
            ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
            ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _LIGHT]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(m_table)

    doc.build(story)
    buffer.seek(0)
    fname = f"edupulse_report_{u.get('customId', student_uid)}.pdf"
    return Response(
        buffer.read(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'}
    )


@reports_bp.route('/class/<class_id>', methods=['GET'])
@require_role('faculty_advisor')
def class_report(class_id):
    cls_doc = db.collection('classes').document(class_id).get()
    if not cls_doc.exists:
        return jsonify({'error': 'Class not found'}), 404
    cls = cls_doc.to_dict()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    story.append(Paragraph("EduPulse — Class Risk Report", ParagraphStyle(
        'ETitle', parent=styles['Title'], fontSize=20, textColor=_PURPLE, spaceAfter=4)))
    story.append(HRFlowable(width="100%", color=_PURPLE, thickness=2))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>Class:</b> {cls.get('name', '')}", getSampleStyleSheet()['Normal']))
    story.append(Paragraph(f"<b>Date:</b> {datetime.date.today().isoformat()}", getSampleStyleSheet()['Normal']))
    story.append(Spacer(1, 12))

    student_uids = cls.get('students', [])
    data = [['Name', 'ID', 'Risk Score', 'Level', 'Trend']]
    for uid in student_uids:
        u_doc = db.collection('users').document(uid).get()
        r_doc = db.collection('riskScores').document(uid).get()
        if u_doc.exists:
            u = u_doc.to_dict()
            r = r_doc.to_dict() if r_doc.exists else {}
            data.append([
                u.get('name', ''),
                u.get('customId', ''),
                str(r.get('score', 0)),
                r.get('level', 'LOW'),
                r.get('trend', 'stable'),
            ])

    table = Table(data, colWidths=[5*cm, 3*cm, 3*cm, 3*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), _PURPLE),
        ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
        ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _LIGHT]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return Response(
        buffer.read(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="class_report_{class_id}.pdf"'}
    )
