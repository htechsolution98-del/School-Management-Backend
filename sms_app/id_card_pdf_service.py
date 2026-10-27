import os
import io
from PIL import Image as PILImage, ImageDraw, ImageFont
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.db.models import Q

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode import qr
from reportlab.lib.utils import ImageReader


# Standard CR80 PVC dimensions (85.6mm x 53.98mm)
CR80_WIDTH_MM = 85.6
CR80_HEIGHT_MM = 53.98

CR80_LANDSCAPE = (CR80_WIDTH_MM * mm, CR80_HEIGHT_MM * mm)
CR80_PORTRAIT = (CR80_HEIGHT_MM * mm, CR80_WIDTH_MM * mm)


def get_student_photo_path(student):
    """Resolve local path or URL for student photo"""
    try:
        # 1. Check admission documents
        if student.admission:
            photo_doc = student.admission.documents.filter(
                Q(document_field__label__icontains="photo") | Q(document_field__label__icontains="picture")
            ).first()
            if photo_doc and photo_doc.file:
                return photo_doc.file.path if hasattr(photo_doc.file, 'path') and os.path.exists(photo_doc.file.path) else None

        # 2. Check student_documents
        sdoc = student.student_documents.filter(
            Q(title__icontains="photo") | Q(document_type__icontains="photo")
        ).first()
        if sdoc and sdoc.document:
            return sdoc.document.path if hasattr(sdoc.document, 'path') and os.path.exists(sdoc.document.path) else None
    except Exception:
        pass
    return None


def get_staff_photo_path(staff):
    """Resolve photo path for staff members if available"""
    # If staff has user profile picture or document
    try:
        if staff.user:
            profile = getattr(staff.user, 'userprofile', None)
            if profile and getattr(profile, 'profile_picture', None):
                p = profile.profile_picture
                if hasattr(p, 'path') and os.path.exists(p.path):
                    return p.path
    except Exception:
        pass
    return None


def resolve_card_data(user_type, user_obj, school, card_record=None, template=None):
    """
    Build dictionary of dynamic values for rendering on ID Card.
    """
    data = {
        'school_name': school.name if school else 'School Management',
        'school_code': getattr(school, 'code', '') or '',
        'school_phone': getattr(school, 'phone', '') or getattr(school, 'mobile', '') or '',
        'school_email': getattr(school, 'email', '') or '',
        'school_address': getattr(school, 'address', '') or '',
        'school_logo': school.logo.path if hasattr(school, 'logo') and school.logo and hasattr(school.logo, 'path') and os.path.exists(school.logo.path) else None,
        'card_number': card_record.card_number if card_record else f"ID-{int(timezone.now().timestamp())}",
        'issue_date': (card_record.issue_date if card_record else timezone.now().date()).strftime('%d-%m-%Y'),
        'valid_upto': (card_record.valid_upto.strftime('%d-%m-%Y') if card_record and card_record.valid_upto else (getattr(user_obj, 'academic_year', None).name if getattr(user_obj, 'academic_year', None) else '2026-2027')),
        'blood_group': (card_record.blood_group if card_record and card_record.blood_group else getattr(user_obj, 'blood_group', '')) or 'N/A',
        'emergency_contact': (card_record.emergency_contact if card_record and card_record.emergency_contact else getattr(user_obj, 'emergency_contact', '')) or getattr(user_obj, 'mobile', '') or 'N/A',
        'custom_1': card_record.custom_field_1_value if card_record else '',
        'custom_2': card_record.custom_field_2_value if card_record else '',
        'custom_3': card_record.custom_field_3_value if card_record else '',
    }

    if user_type == 'STUDENT':
        student = user_obj
        full_name = f"{student.name or ''} {student.father_name or ''} {student.surname or ''}".strip()
        data.update({
            'name': full_name or 'Student Name',
            'first_name': student.name or '',
            'surname': student.surname or '',
            'father_name': student.father_name or '',
            'id_no': student.gr_no or student.roll_no or f"STU-{student.id}",
            'gr_no': student.gr_no or 'N/A',
            'roll_no': student.roll_no or 'N/A',
            'class_div': f"{student.school_class.school_class if student.school_class else ''} - {student.division or ''}".strip(' -'),
            'class_name': student.school_class.school_class if student.school_class else '',
            'division': student.division or '',
            'dob': student.date_of_birth.strftime('%d-%m-%Y') if student.date_of_birth else 'N/A',
            'mobile': student.mobile or 'N/A',
            'address': getattr(student, 'address', '') or getattr(student.admission, 'address', '') if hasattr(student, 'admission') and student.admission else '',
            'user_type_label': 'STUDENT',
            'photo_path': get_student_photo_path(student),
        })
    else:
        staff = user_obj
        data.update({
            'name': staff.name or 'Staff Member',
            'id_no': f"EMP-{staff.id}",
            'gr_no': f"EMP-{staff.id}",
            'roll_no': 'N/A',
            'class_div': staff.department.name if staff.department else (staff.designation or 'Staff'),
            'department': staff.department.name if staff.department else '',
            'designation': staff.designation or 'Teacher / Staff',
            'dob': staff.date_of_birth.strftime('%d-%m-%Y') if staff.date_of_birth else 'N/A',
            'mobile': staff.mobile or 'N/A',
            'address': staff.address or '',
            'user_type_label': staff.designation or 'STAFF',
            'photo_path': get_staff_photo_path(staff),
        })

    return data


def get_default_layout(orientation='PORTRAIT', user_type='STUDENT'):
    """
    Standard default layout if template has no custom layout configured.
    Coordinates are in percentage (0 to 100) of card width and height.
    """
    is_portrait = orientation.upper() == 'PORTRAIT'
    fields = [
        {
            'key': 'photo',
            'label': 'Photograph',
            'side': 'front',
            'visible': True,
            'x': 32 if is_portrait else 8,
            'y': 18 if is_portrait else 22,
            'width': 36 if is_portrait else 26,
            'height': 30 if is_portrait else 52,
            'border_radius': 4,
            'show_border': True,
        },
        {
            'key': 'name',
            'label': 'Full Name',
            'side': 'front',
            'visible': True,
            'x': 5 if is_portrait else 38,
            'y': 51 if is_portrait else 22,
            'width': 90 if is_portrait else 58,
            'height': 6,
            'font_size': 11,
            'font_weight': 'bold',
            'color': '#111827',
            'align': 'center' if is_portrait else 'left',
        },
        {
            'key': 'id_no',
            'label': 'G.R. / ID No',
            'prefix': 'G.R. No: ',
            'side': 'front',
            'visible': True,
            'x': 5 if is_portrait else 38,
            'y': 59 if is_portrait else 32,
            'width': 90 if is_portrait else 58,
            'height': 5,
            'font_size': 9,
            'font_weight': 'normal',
            'color': '#374151',
            'align': 'center' if is_portrait else 'left',
        },
        {
            'key': 'class_div',
            'label': 'Class / Designation',
            'prefix': 'Class: ' if user_type == 'STUDENT' else 'Dept: ',
            'side': 'front',
            'visible': True,
            'x': 5 if is_portrait else 38,
            'y': 66 if is_portrait else 41,
            'width': 90 if is_portrait else 58,
            'height': 5,
            'font_size': 9,
            'font_weight': 'bold',
            'color': '#1d4ed8',
            'align': 'center' if is_portrait else 'left',
        },
        {
            'key': 'roll_no',
            'label': 'Roll Number',
            'prefix': 'Roll No: ',
            'side': 'front',
            'visible': user_type == 'STUDENT',
            'x': 5 if is_portrait else 38,
            'y': 73 if is_portrait else 50,
            'width': 45 if is_portrait else 58,
            'height': 5,
            'font_size': 8.5,
            'font_weight': 'normal',
            'color': '#4b5563',
            'align': 'center' if is_portrait else 'left',
        },
        {
            'key': 'blood_group',
            'label': 'Blood Group',
            'prefix': 'Blood Group: ',
            'side': 'front',
            'visible': True,
            'x': 50 if is_portrait else 38,
            'y': 73 if is_portrait else 59,
            'width': 45 if is_portrait else 58,
            'height': 5,
            'font_size': 8.5,
            'font_weight': 'bold',
            'color': '#dc2626',
            'align': 'center' if is_portrait else 'left',
        },
        {
            'key': 'valid_upto',
            'label': 'Valid Upto',
            'prefix': 'Valid Upto: ',
            'side': 'front',
            'visible': True,
            'x': 5 if is_portrait else 38,
            'y': 80 if is_portrait else 68,
            'width': 90 if is_portrait else 58,
            'height': 5,
            'font_size': 8,
            'font_weight': 'bold',
            'color': '#059669',
            'align': 'center' if is_portrait else 'left',
        },
        # Back Side Fields
        {
            'key': 'emergency_contact',
            'label': 'Emergency Contact',
            'prefix': 'Emergency Contact: ',
            'side': 'back',
            'visible': True,
            'x': 8,
            'y': 15,
            'width': 84,
            'height': 6,
            'font_size': 9,
            'font_weight': 'bold',
            'color': '#dc2626',
            'align': 'left',
        },
        {
            'key': 'dob',
            'label': 'Date of Birth',
            'prefix': 'Date of Birth: ',
            'side': 'back',
            'visible': True,
            'x': 8,
            'y': 25,
            'width': 84,
            'height': 6,
            'font_size': 8.5,
            'font_weight': 'normal',
            'color': '#374151',
            'align': 'left',
        },
        {
            'key': 'address',
            'label': 'Residential Address',
            'prefix': 'Address: ',
            'side': 'back',
            'visible': True,
            'x': 8,
            'y': 35,
            'width': 84,
            'height': 16,
            'font_size': 8,
            'font_weight': 'normal',
            'color': '#4b5563',
            'align': 'left',
        },
        {
            'key': 'qr_code',
            'label': 'QR / Barcode',
            'side': 'back',
            'visible': True,
            'x': 35 if is_portrait else 65,
            'y': 55 if is_portrait else 25,
            'width': 30 if is_portrait else 25,
            'height': 30 if is_portrait else 45,
            'align': 'center',
        },
        {
            'key': 'instructions',
            'label': 'Terms / Instructions',
            'text': 'This card is the property of the school. If found, please return to the school administration office.',
            'side': 'back',
            'visible': True,
            'x': 8,
            'y': 86 if is_portrait else 75,
            'width': 84,
            'height': 10,
            'font_size': 6.5,
            'font_weight': 'normal',
            'color': '#6b7280',
            'align': 'center',
        }
    ]
    return {
        'show_lanyard_safe_zone': True,
        'lanyard_safe_zone_height_mm': 12,
        'custom_field_1_label': 'Bus Route',
        'custom_field_2_label': 'House Name',
        'custom_field_3_label': 'Allergies',
        'fields': fields
    }


def draw_card_on_canvas(pdf_canvas, card_left, card_bottom, card_width, card_height, template, data, side='front'):
    """
    Renders a single card (front or back side) onto a ReportLab canvas at the specified bounding box.
    """
    layout_raw = template.layout_config if isinstance(template.layout_config, dict) else {}
    if not layout_raw.get('fields'):
        layout: dict = get_default_layout(template.orientation, template.user_type)
    else:
        layout = layout_raw

    raw_fields = layout.get('fields')
    fields_list: list = raw_fields if isinstance(raw_fields, list) else []
    fields = [f for f in fields_list if isinstance(f, dict) and f.get('side', 'front') == side and f.get('visible', True)]
    bg_field = template.front_background if side == 'front' else template.back_background

    pdf_canvas.saveState()

    # 1. Background image or Default Styled Background
    if bg_field and hasattr(bg_field, 'path') and os.path.exists(bg_field.path):
        try:
            pdf_canvas.drawImage(bg_field.path, card_left, card_bottom, width=card_width, height=card_height, preserveAspectRatio=False)
        except Exception:
            draw_default_card_background(pdf_canvas, card_left, card_bottom, card_width, card_height, data, side)
    else:
        draw_default_card_background(pdf_canvas, card_left, card_bottom, card_width, card_height, data, side)

    # 2. Lanyard Hole Safe Zone (Top margin warning / slot indicator)
    if layout.get('show_lanyard_safe_zone', False) and side == 'front':
        try:
            safe_h_mm = float(layout.get('lanyard_safe_zone_height_mm', 12) or 12)
        except (ValueError, TypeError):
            safe_h_mm = 12.0
        safe_h = safe_h_mm * mm
        # Draw subtle slot punch guideline at top center
        slot_w = 14 * mm
        slot_h = 3.5 * mm
        slot_x = card_left + (card_width - slot_w) / 2.0
        slot_y = card_bottom + card_height - 6 * mm
        pdf_canvas.saveState()
        pdf_canvas.setStrokeColor(colors.HexColor('#9ca3af'))
        pdf_canvas.setFillColor(colors.HexColor('#f3f4f6'))
        pdf_canvas.setLineWidth(0.5)
        pdf_canvas.setDash([2, 2], 0)
        pdf_canvas.roundRect(slot_x, slot_y, slot_w, slot_h, 1.5 * mm, stroke=1, fill=1)
        pdf_canvas.restoreState()

    # 3. Dynamic Fields
    for field in fields:
        key = field.get('key')
        x_pct = float(field.get('x', 0))
        y_pct = float(field.get('y', 0))
        w_pct = float(field.get('width', 100))
        h_pct = float(field.get('height', 10))

        # Convert top-left percentage to ReportLab bottom-left points
        f_x = card_left + (x_pct / 100.0) * card_width
        f_w = (w_pct / 100.0) * card_width
        f_h = (h_pct / 100.0) * card_height
        f_y = card_bottom + card_height - ((y_pct + h_pct) / 100.0) * card_height

        if key == 'photo':
            photo_path = data.get('photo_path')
            draw_photo_box(pdf_canvas, f_x, f_y, f_w, f_h, photo_path, field)
        elif key == 'qr_code':
            qr_content = f"{data.get('school_name')}|{data.get('card_number')}|{data.get('id_no')}|{data.get('name')}"
            draw_qr_code(pdf_canvas, f_x, f_y, f_w, f_h, qr_content)
        elif key == 'school_logo':
            logo_path = data.get('school_logo')
            if logo_path and os.path.exists(logo_path):
                try:
                    pdf_canvas.drawImage(logo_path, f_x, f_y, width=f_w, height=f_h, preserveAspectRatio=True, mask='auto')
                except Exception:
                    pass
        elif key == 'instructions':
            text = field.get('text', '')
            draw_text_box(pdf_canvas, f_x, f_y, f_w, f_h, text, field)
        else:
            # Standard dynamic text fields
            raw_val = data.get(key, '')
            if key in ('name', 'full_name', 'first_name', 'surname'):
                prefix = ''
            else:
                prefix = str(field.get('prefix', '') or '')
                if prefix and not prefix.endswith((' ', '\t')):
                    prefix = prefix + ' '
            display_text = f"{prefix}{raw_val}" if raw_val else ''
            if display_text:
                draw_text_box(pdf_canvas, f_x, f_y, f_w, f_h, display_text, field)

    pdf_canvas.restoreState()


def draw_default_card_background(pdf_canvas, x, y, w, h, data, side='front'):
    """Draws a clean, modern default card design when clerk hasn't uploaded a background image."""
    pdf_canvas.saveState()
    # Card outer rounded border and white card stock
    pdf_canvas.setFillColor(colors.white)
    pdf_canvas.setStrokeColor(colors.HexColor('#d1d5db'))
    pdf_canvas.setLineWidth(0.8)
    pdf_canvas.roundRect(x, y, w, h, 3 * mm, stroke=1, fill=1)

    # Top header bar (deep modern indigo/blue gradient style)
    header_h = h * 0.17
    header_y = y + h - header_h
    pdf_canvas.setFillColor(colors.HexColor('#1e3a8a'))
    pdf_canvas.rect(x, header_y, w, header_h, stroke=0, fill=1)

    # School Name in Header
    pdf_canvas.setFillColor(colors.white)
    pdf_canvas.setFont('Helvetica-Bold', 9 if w < 60 * mm else 11)
    school_title = str(data.get('school_name', 'SCHOOL NAME'))[:32].upper()
    pdf_canvas.drawCentredString(x + w / 2.0, header_y + header_h * 0.35, school_title)

    # Footer stripe
    footer_h = h * 0.05
    pdf_canvas.setFillColor(colors.HexColor('#2563eb'))
    pdf_canvas.rect(x, y, w, footer_h, stroke=0, fill=1)

    pdf_canvas.restoreState()


def draw_photo_box(pdf_canvas, x, y, w, h, photo_path, field_cfg):
    """Draws student/staff photograph or modern avatar placeholder inside bounded box."""
    pdf_canvas.saveState()
    # Border & Background
    pdf_canvas.setFillColor(colors.HexColor('#f3f4f6'))
    pdf_canvas.setStrokeColor(colors.HexColor('#cbd5e1'))
    pdf_canvas.setLineWidth(1)
    border_r = field_cfg.get('border_radius', 4) * 0.5 * mm
    pdf_canvas.roundRect(x, y, w, h, border_r, stroke=1, fill=1)

    if photo_path and os.path.exists(photo_path):
        try:
            # Crop/fill photo inside box
            pdf_canvas.drawImage(photo_path, x, y, width=w, height=h, preserveAspectRatio=True, mask='auto')
            pdf_canvas.restoreState()
            return
        except Exception:
            pass

    # Draw placeholder silhouette
    pdf_canvas.setFillColor(colors.HexColor('#9ca3af'))
    pdf_canvas.circle(x + w / 2.0, y + h * 0.62, min(w, h) * 0.22, stroke=0, fill=1)
    # Head & shoulders base
    shoulder_w = w * 0.65
    shoulder_h = h * 0.3
    pdf_canvas.roundRect(x + (w - shoulder_w) / 2.0, y + h * 0.1, shoulder_w, shoulder_h, 3 * mm, stroke=0, fill=1)

    pdf_canvas.restoreState()


def draw_qr_code(pdf_canvas, x, y, w, h, content):
    """Draws ReportLab native QR code widget."""
    try:
        qr_widget = qr.QrCodeWidget(content)
        bounds = qr_widget.getBounds()
        qr_w = bounds[2] - bounds[0]
        qr_h = bounds[3] - bounds[1]
        drawing = Drawing(w, h, transform=[w / qr_w, 0, 0, h / qr_h, 0, 0])
        drawing.add(qr_widget)
        drawing.drawOn(pdf_canvas, x, y)
    except Exception:
        pass


def draw_text_box(pdf_canvas, x, y, w, h, text, field_cfg):
    """Renders single or multi-line text with font size, bold, color and alignment."""
    pdf_canvas.saveState()
    font_size = float(field_cfg.get('font_size', 8.5))
    is_bold = field_cfg.get('font_weight') == 'bold'
    font_family_cfg = str(field_cfg.get('font_family', '')).lower()
    if 'times' in font_family_cfg:
        font_name = 'Times-Bold' if is_bold else 'Times-Roman'
    elif 'courier' in font_family_cfg:
        font_name = 'Courier-Bold' if is_bold else 'Courier'
    else:
        font_name = 'Helvetica-Bold' if is_bold else 'Helvetica'
    color_hex = field_cfg.get('color', '#111827')
    align = field_cfg.get('align', 'left')

    try:
        pdf_canvas.setFillColor(colors.HexColor(color_hex))
    except Exception:
        pdf_canvas.setFillColor(colors.black)

    pdf_canvas.setFont(font_name, font_size)

    text_str = str(text)
    # Check vertical center inside height
    text_y = y + (h - font_size) / 2.0

    if align == 'center':
        pdf_canvas.drawCentredString(x + w / 2.0, text_y, text_str)
    elif align == 'right':
        pdf_canvas.drawRightString(x + w, text_y, text_str)
    else:
        pdf_canvas.drawString(x, text_y, text_str)

    pdf_canvas.restoreState()


def generate_single_card_pdf(template, card_record, user_data, include_back=True):
    """
    Generates single card PVC print PDF formatted to exact CR80 dimensions (54x86mm or 86x54mm).
    """
    buffer = io.BytesIO()
    is_portrait = template.orientation.upper() == 'PORTRAIT'
    card_size = CR80_PORTRAIT if is_portrait else CR80_LANDSCAPE
    card_w, card_h = card_size

    p = canvas.Canvas(buffer, pagesize=card_size)
    p.setTitle(f"ID_Card_{card_record.card_number}")

    # Page 1: Front
    draw_card_on_canvas(p, 0, 0, card_w, card_h, template, user_data, side='front')
    p.showPage()

    # Page 2: Back
    if include_back:
        draw_card_on_canvas(p, 0, 0, card_w, card_h, template, user_data, side='back')
        p.showPage()

    p.save()
    buffer.seek(0)
    return buffer.getvalue()


def generate_a4_grid_pdf(template, records_and_data_list, include_back=True, cards_per_page=8):
    """
    Generates mass printing PDF on standard A4 sheet (210x297mm) with crop marks for cutting.
    Arranges 8 to 10 cards per A4 page.
    """
    buffer = io.BytesIO()
    a4_w, a4_h = A4
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setTitle(f"ID_Cards_Batch_{timezone.now().strftime('%Y%m%d_%H%M%S')}")

    is_portrait = template.orientation.upper() == 'PORTRAIT'
    card_w = (CR80_HEIGHT_MM * mm) if is_portrait else (CR80_WIDTH_MM * mm)
    card_h = (CR80_WIDTH_MM * mm) if is_portrait else (CR80_HEIGHT_MM * mm)

    cols = 2 if not is_portrait else 3
    rows = 4 if not is_portrait else 3
    cards_per_sheet = cols * rows

    # Calculate layout margins
    total_grid_w = cols * card_w
    total_grid_h = rows * card_h
    start_margin_x = max(8 * mm, (a4_w - total_grid_w) / 2.0)
    start_margin_y = max(8 * mm, (a4_h - total_grid_h) / 2.0)

    # Chunk records into batches per page
    for chunk_idx in range(0, len(records_and_data_list), cards_per_sheet):
        chunk = records_and_data_list[chunk_idx:chunk_idx + cards_per_sheet]

        # 1. Front Side Page
        for idx, (rec, udata) in enumerate(chunk):
            r = idx // cols
            c = idx % cols
            card_x = start_margin_x + c * card_w
            card_y = start_margin_y + (rows - 1 - r) * card_h

            draw_card_on_canvas(p, card_x, card_y, card_w, card_h, template, udata, side='front')
            draw_crop_marks(p, card_x, card_y, card_w, card_h)

        p.showPage()

        # 2. Back Side Page (Matching aligned positions for duplex printing)
        if include_back:
            for idx, (rec, udata) in enumerate(chunk):
                r = idx // cols
                # For duplex back side, flip column order so front and back align when printed double-sided!
                c = (cols - 1) - (idx % cols)
                card_x = start_margin_x + c * card_w
                card_y = start_margin_y + (rows - 1 - r) * card_h

                draw_card_on_canvas(p, card_x, card_y, card_w, card_h, template, udata, side='back')
                draw_crop_marks(p, card_x, card_y, card_w, card_h)

            p.showPage()

    p.save()
    buffer.seek(0)
    return buffer.getvalue()


def draw_crop_marks(pdf_canvas, x, y, w, h):
    """Draws subtle crop / cutting guide marks at the 4 corners of each card."""
    pdf_canvas.saveState()
    pdf_canvas.setStrokeColor(colors.HexColor('#9ca3af'))
    pdf_canvas.setLineWidth(0.4)
    mark_len = 3 * mm

    # Bottom-Left
    pdf_canvas.line(x - mark_len, y, x, y)
    pdf_canvas.line(x, y - mark_len, x, y)

    # Bottom-Right
    pdf_canvas.line(x + w, y, x + w + mark_len, y)
    pdf_canvas.line(x + w, y - mark_len, x + w, y)

    # Top-Left
    pdf_canvas.line(x - mark_len, y + h, x, y + h)
    pdf_canvas.line(x, y + h, x, y + h + mark_len)

    # Top-Right
    pdf_canvas.line(x + w, y + h, x + w + mark_len, y + h)
    pdf_canvas.line(x + w, y + h, x + w, y + h + mark_len)

    pdf_canvas.restoreState()


def generate_eid_image(template, card_record, user_data, side='front'):
    """
    Renders high-resolution Digital E-ID Card as a PNG image using ReportLab & Pillow.
    """
    pdf_bytes = generate_single_card_pdf(template, card_record, user_data, include_back=(side == 'back'))
    return pdf_bytes
