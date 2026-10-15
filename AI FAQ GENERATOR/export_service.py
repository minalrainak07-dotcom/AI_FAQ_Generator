import io
import os
import csv
import html
import logging
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)


def export_txt(title, faqs):
    """
    Format FAQs as a clean text file.
    """
    lines = []
    doc_title = title if title and str(title).strip() else "AI FAQ Generator"
    lines.append("=" * 60)
    lines.append(f"  {doc_title.strip()}")
    lines.append("=" * 60)
    lines.append("")

    if not faqs:
        lines.append("No FAQs available.")
        return "\n".join(lines)

    for idx, faq in enumerate(faqs, 1):
        q = str(faq.get('question', '')).strip()
        a = str(faq.get('answer', '')).strip()
        cat = str(faq.get('category', '')).strip() or 'General'

        lines.append(f"Q{idx} [{cat}]: {q}")
        lines.append(f"A{idx}: {a}")
        lines.append("-" * 60)
        lines.append("")

    return "\n".join(lines)


def export_csv(title, faqs):
    """
    Export FAQs as CSV string with Number, Question, Answer, and Category columns.
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(["Number", "Question", "Answer", "Category"])

    if faqs:
        for idx, faq in enumerate(faqs, 1):
            q = str(faq.get('question', '')).strip()
            a = str(faq.get('answer', '')).strip()
            cat = str(faq.get('category', '')).strip() or 'General'
            writer.writerow([idx, q, a, cat])

    return output.getvalue()


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to accurately compute total page count and draw clean footers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)

        width, height = letter
        margin = 36
        # Footer dividing line
        self.line(margin, 36, width - margin, 36)

        # Footer labels
        self.drawString(margin, 24, "AI FAQ Generator")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(width - margin, 24, page_str)
        self.restoreState()


def _get_registered_fonts():
    """
    Detect and register Unicode-capable fonts if available, falling back to Helvetica.
    """
    font_name = 'Helvetica'
    bold_font = 'Helvetica-Bold'

    # Candidate font paths to look for Unicode / multi-language support
    candidates = [
        ("NotoSans", "NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
        ("SegoeUI", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("Arial", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("Mangal", "C:/Windows/Fonts/mangal.ttf", "C:/Windows/Fonts/mangalb.ttf")
    ]

    for name, reg_path, bold_path in candidates:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont(name, reg_path))
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont(f"{name}-Bold", bold_path))
                    bold_font = f"{name}-Bold"
                else:
                    bold_font = name
                font_name = name
                break
            except Exception as e:
                logger.debug(f"Could not register font {name}: {e}")
                continue

    return font_name, bold_font


def export_pdf(title, faqs):
    """
    Generate professional PDF bytes containing formatted FAQs.
    """
    buffer = io.BytesIO()

    # Setup styles and document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=48
    )

    font_name, bold_font = _get_registered_fonts()
    styles = getSampleStyleSheet()

    # Custom styles
    app_header_style = ParagraphStyle(
        'AppHeader',
        parent=styles['Normal'],
        fontName=bold_font,
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#4A5568")
    )

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName=bold_font,
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1A202C"),
        spaceAfter=14
    )

    question_style = ParagraphStyle(
        'QuestionStyle',
        parent=styles['Normal'],
        fontName=bold_font,
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#2B6CB0"),
        spaceBefore=8,
        spaceAfter=4
    )

    category_badge_style = ParagraphStyle(
        'CategoryBadge',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#718096"),
        spaceAfter=4
    )

    answer_style = ParagraphStyle(
        'AnswerStyle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#2D3748"),
        leftIndent=10,
        spaceAfter=10
    )

    empty_style = ParagraphStyle(
        'EmptyStyle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#718096"),
        spaceBefore=20
    )

    story = []

    # App Branding Banner
    story.append(Paragraph("AI FAQ GENERATOR", app_header_style))
    story.append(Spacer(1, 4))

    doc_title = title if title and str(title).strip() else "Frequently Asked Questions"
    story.append(Paragraph(html.escape(doc_title.strip()), title_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=15))

    if not faqs:
        story.append(Paragraph("No FAQs available in this collection.", empty_style))
    else:
        for idx, faq in enumerate(faqs, 1):
            q_raw = str(faq.get('question', '')).strip()
            a_raw = str(faq.get('answer', '')).strip()
            cat_raw = str(faq.get('category', '')).strip() or 'General'

            safe_q = html.escape(q_raw)
            safe_a = html.escape(a_raw)
            safe_cat = html.escape(cat_raw)

            # Question and category
            story.append(Paragraph(f"<b>Q{idx}. {safe_q}</b>", question_style))
            story.append(Paragraph(f"Category: <i>{safe_cat}</i>", category_badge_style))
            story.append(Paragraph(safe_a, answer_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceBefore=4, spaceAfter=8))

    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
