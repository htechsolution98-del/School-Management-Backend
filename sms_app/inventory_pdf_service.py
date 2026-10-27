import os
import io
from decimal import Decimal
from django.conf import settings
from django.utils import timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, Flowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


def generate_purchase_invoice_pdf(purchase):
    """
    Generate a professional Purchase Invoice / Receipt PDF using ReportLab.
    Includes School Logo, School Info, Supplier Details (GST, Phone), Date, Itemized Table, and Grand Total.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    school_title_style = ParagraphStyle(
        'SchoolTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#1E293B'),
    )

    school_meta_style = ParagraphStyle(
        'SchoolMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor('#475569'),
    )

    invoice_title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=21,
        alignment=TA_RIGHT,
        textColor=colors.HexColor('#4338CA'),
    )

    invoice_meta_style = ParagraphStyle(
        'InvoiceMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12.5,
        alignment=TA_RIGHT,
        textColor=colors.HexColor('#334155'),
    )

    section_header_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor('#1E293B'),
    )

    supplier_label_style = ParagraphStyle(
        'SupplierLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor('#64748B'),
    )

    supplier_val_style = ParagraphStyle(
        'SupplierVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#1E293B'),
    )

    th_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#FFFFFF'),
    )

    th_center_style = ParagraphStyle(
        'TableHeaderCenter',
        parent=th_style,
        alignment=TA_CENTER,
    )

    th_right_style = ParagraphStyle(
        'TableHeaderRight',
        parent=th_style,
        alignment=TA_RIGHT,
    )

    td_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor('#1E293B'),
    )

    td_bold_style = ParagraphStyle(
        'TableCellBold',
        parent=td_style,
        fontName='Helvetica-Bold',
    )

    td_center_style = ParagraphStyle(
        'TableCellCenter',
        parent=td_style,
        alignment=TA_CENTER,
    )

    td_right_style = ParagraphStyle(
        'TableCellRight',
        parent=td_style,
        alignment=TA_RIGHT,
    )

    story: list[Flowable] = []
    school = purchase.school
    supplier = purchase.supplier

    # -------------------------------------------------------------
    # 1. HEADER: School Logo & Info (Left) + Invoice Title & No (Right)
    # -------------------------------------------------------------
    school_name = (school.name if school and school.name else "School Management System").strip()
    school_addr_parts = []
    if school:
        if school.address:
            school_addr_parts.append(school.address.strip())
        city_state = ", ".join(filter(None, [getattr(school, 'city', None), getattr(school, 'state', None)]))
        if city_state:
            school_addr_parts.append(city_state)
        if getattr(school, 'pincode', None):
            school_addr_parts.append(f"PIN: {school.pincode}")

    school_addr_str = " | ".join(school_addr_parts)
    contact_parts = []
    if school:
        if school.phone:
            contact_parts.append(f"Phone: {school.phone}")
        if school.email:
            contact_parts.append(f"Email: {school.email}")
    contact_str = " | ".join(contact_parts)

    school_info_elements = [
        Paragraph(school_name, school_title_style),
        Spacer(1, 1.5 * mm),
    ]
    if school_addr_str:
        school_info_elements.append(Paragraph(school_addr_str, school_meta_style))
    if contact_str:
        school_info_elements.append(Paragraph(contact_str, school_meta_style))

    # Resolve School Logo if exists
    logo_img = None
    if school and getattr(school, 'logo', None):
        try:
            logo_path = school.logo.path if hasattr(school.logo, 'path') else None
            if logo_path and os.path.exists(logo_path):
                logo_img = RLImage(logo_path, width=18 * mm, height=18 * mm)
            elif hasattr(school.logo, 'file'):
                logo_img = RLImage(school.logo.file, width=18 * mm, height=18 * mm)
        except Exception:
            logo_img = None

    if logo_img:
        left_header_data = [[logo_img, school_info_elements]]
        left_header_col_widths = [22 * mm, 80 * mm]
    else:
        left_header_data = [[school_info_elements]]
        left_header_col_widths = [102 * mm]

    left_header_table = Table(left_header_data, colWidths=left_header_col_widths)
    left_header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    # Right side: Invoice meta
    status_label = purchase.status or "CONFIRMED"
    payment_status = purchase.payment_status or "PAID"
    purchase_date_str = purchase.purchase_date.strftime("%d %b, %Y") if hasattr(purchase.purchase_date, 'strftime') else str(purchase.purchase_date or "-")

    invoice_meta_elements = [
        Paragraph("PURCHASE INVOICE", invoice_title_style),
        Spacer(1, 2 * mm),
        Paragraph(f"<b>Invoice #:</b> {purchase.invoice_number}", invoice_meta_style),
        Paragraph(f"<b>Date:</b> {purchase_date_str}", invoice_meta_style),
        Paragraph(f"<b>Academic Year:</b> {purchase.academic_year.name if purchase.academic_year else 'N/A'}", invoice_meta_style),
        Paragraph(f"<b>Payment:</b> {payment_status.title()} &nbsp;|&nbsp; <b>Status:</b> {status_label.title()}", invoice_meta_style),
    ]

    header_master_data = [[left_header_table, invoice_meta_elements]]
    header_master = Table(header_master_data, colWidths=[105 * mm, 77 * mm])
    header_master.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    story.append(header_master)
    story.append(Spacer(1, 4 * mm))

    # Divider bar
    divider_data = [['']]
    divider = Table(divider_data, colWidths=[182 * mm], rowHeights=[1.5])
    divider.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#4338CA')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(divider)
    story.append(Spacer(1, 4 * mm))

    # -------------------------------------------------------------
    # 2. SUPPLIER / VENDOR DETAILS CARD
    # -------------------------------------------------------------
    sup_name = supplier.supplier_name if supplier else "Direct / Unregistered Supplier"
    sup_contact = supplier.contact_person if supplier and supplier.contact_person else "N/A"
    sup_phone = supplier.phone if supplier and supplier.phone else "N/A"
    sup_email = supplier.email if supplier and supplier.email else "N/A"
    sup_gst = supplier.gst_number if supplier and supplier.gst_number else "N/A"
    sup_addr = supplier.address if supplier and supplier.address else "N/A"

    supplier_card_data = [
        [
            Paragraph("<b>VENDOR / SUPPLIER DETAILS</b>", section_header_style),
            Paragraph("<b>BILLING & DELIVERY DETAILS</b>", section_header_style),
        ],
        [
            Paragraph(f"<b>Company / Vendor:</b> {sup_name}", supplier_val_style),
            Paragraph(f"<b>Institution:</b> {school_name}", supplier_val_style),
        ],
        [
            Paragraph(f"<b>Contact Person:</b> {sup_contact} &nbsp;|&nbsp; <b>Phone:</b> {sup_phone}", supplier_val_style),
            Paragraph(f"<b>Address:</b> {school_addr_str or 'Campus Inventory'}", supplier_val_style),
        ],
        [
            Paragraph(f"<b>GSTIN / Tax ID:</b> {sup_gst} &nbsp;|&nbsp; <b>Email:</b> {sup_email}", supplier_val_style),
            Paragraph(f"<b>Received By:</b> {purchase.created_by.get_full_name() if purchase.created_by else 'Admin / Clerk'}", supplier_val_style),
        ],
    ]

    supplier_table = Table(supplier_card_data, colWidths=[91 * mm, 91 * mm])
    supplier_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#F1F5F9')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#E2E8F0')),
    ]))

    story.append(supplier_table)
    story.append(Spacer(1, 5 * mm))

    # -------------------------------------------------------------
    # 3. ITEMIZED LINE ITEMS TABLE
    # -------------------------------------------------------------
    items_header = [
        Paragraph("#", th_center_style),
        Paragraph("Item Description & Code", th_style),
        Paragraph("Variant (Size / Color)", th_style),
        Paragraph("Qty", th_center_style),
        Paragraph("Unit Cost", th_right_style),
        Paragraph("Total (INR)", th_right_style),
    ]

    table_data = [items_header]
    line_items = purchase.items.all().select_related('item', 'size', 'color')

    for idx, line in enumerate(line_items, start=1):
        item_title = line.item.item_name if line.item else f"Item #{line.item_id}"
        item_code = line.item.item_code if line.item and line.item.item_code else ""
        item_cell = f"<b>{item_title}</b>"
        if item_code:
            item_cell += f"<br/><font size='7.5' color='#64748B'>Code: {item_code}</font>"

        variant_parts = []
        if line.size:
            variant_parts.append(f"Size: {line.size.name}")
        if line.color:
            variant_parts.append(f"Color: {line.color.name}")
        variant_str = " | ".join(variant_parts) if variant_parts else "Standard (N/A)"

        unit_cost_val = Decimal(str(line.unit_cost or 0))
        total_val = Decimal(str(line.total_amount or (unit_cost_val * line.quantity)))

        row = [
            Paragraph(str(idx), td_center_style),
            Paragraph(item_cell, td_style),
            Paragraph(variant_str, td_style),
            Paragraph(str(line.quantity), td_center_style),
            Paragraph(f"&#8377;{unit_cost_val:,.2f}", td_right_style),
            Paragraph(f"&#8377;{total_val:,.2f}", td_right_style),
        ]
        table_data.append(row)

    if len(line_items) == 0:
        table_data.append([
            Paragraph("1", td_center_style),
            Paragraph("No line items recorded on this purchase invoice.", td_style),
            Paragraph("-", td_style),
            Paragraph("0", td_center_style),
            Paragraph("&#8377;0.00", td_right_style),
            Paragraph("&#8377;0.00", td_right_style),
        ])

    items_table = Table(
        table_data,
        colWidths=[10 * mm, 68 * mm, 38 * mm, 18 * mm, 24 * mm, 24 * mm]
    )

    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4338CA')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
    ]

    # Alternating row colors
    for r_idx in range(1, len(table_data)):
        if r_idx % 2 == 0:
            t_style.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#F8FAFC')))

    items_table.setStyle(TableStyle(t_style))
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))

    # -------------------------------------------------------------
    # 4. TOTALS & NOTES SUMMARY BLOCK
    # -------------------------------------------------------------
    subtotal_val = Decimal(str(purchase.subtotal or 0))
    discount_val = Decimal(str(purchase.discount or 0))
    tax_val = Decimal(str(purchase.tax or 0))
    grand_total_val = Decimal(str(purchase.grand_total or subtotal_val - discount_val + tax_val))

    totals_rows = [
        [Paragraph("Subtotal:", td_right_style), Paragraph(f"&#8377;{subtotal_val:,.2f}", td_right_style)],
    ]
    if discount_val > 0:
        totals_rows.append([Paragraph("Discount:", td_right_style), Paragraph(f"- &#8377;{discount_val:,.2f}", td_right_style)])
    if tax_val > 0:
        totals_rows.append([Paragraph("Taxes (GST):", td_right_style), Paragraph(f"+ &#8377;{tax_val:,.2f}", td_right_style)])

    grand_total_label = Paragraph("<font size='10' color='#1E293B'><b>Grand Total:</b></font>", td_right_style)
    grand_total_val_p = Paragraph(f"<font size='11' color='#4338CA'><b>&#8377;{grand_total_val:,.2f}</b></font>", td_right_style)
    totals_rows.append([grand_total_label, grand_total_val_p])

    totals_table = Table(totals_rows, colWidths=[38 * mm, 34 * mm])
    totals_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#4338CA')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EEF2FF')),
    ]))

    notes_text = purchase.notes or "Goods received in good condition and stock updated in inventory ledger."
    notes_element = [
        Paragraph("<b>Notes / Remarks:</b>", section_header_style),
        Spacer(1, 1 * mm),
        Paragraph(notes_text, supplier_val_style),
    ]

    bottom_summary_table = Table(
        [[notes_element, totals_table]],
        colWidths=[110 * mm, 72 * mm]
    )
    bottom_summary_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    story.append(bottom_summary_table)
    story.append(Spacer(1, 12 * mm))

    # -------------------------------------------------------------
    # 5. SIGNATURE & STAMP BLOCK
    # -------------------------------------------------------------
    sig_line = [
        [
            Paragraph("____________________________<br/><b>Prepared / Entered By</b>", td_center_style),
            Paragraph("____________________________<br/><b>Verified / Stock In-Charge</b>", td_center_style),
            Paragraph("____________________________<br/><b>Principal / Authorized Signatory</b>", td_center_style),
        ]
    ]
    sig_table = Table(sig_line, colWidths=[60 * mm, 60 * mm, 62 * mm])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    story.append(KeepTogether(sig_table))

    # Build PDF document
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
