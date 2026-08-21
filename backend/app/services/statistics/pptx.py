"""Deterministic two-slide headquarters presentation renderer."""

from io import BytesIO

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.schemas import StatsCategoriesOut, StatsDashboardOut

FONT = "Century Gothic"
RED = "E30613"
FRAME = "D9D9D9"
HEADER = "B4C7E7"
TOTAL = "595959"


def percentage_color(value: int) -> str:
    if value >= 100:
        return "63BE7B"
    if value >= 70:
        return "FFD966"
    if value >= 50:
        return "F4B183"
    return "E06666"


def _fill(cell, hex_color: str):
    cell.fill.solid()
    cell.fill.fore_color.rgb = RGBColor.from_string(hex_color)


def _style_cell(cell, *, size=8, bold=False, color="222222", align=PP_ALIGN.CENTER):
    cell.margin_left = cell.margin_right = Inches(0.03)
    cell.margin_top = cell.margin_bottom = Inches(0.02)
    for paragraph in cell.text_frame.paragraphs:
        paragraph.alignment = align
        for run in paragraph.runs:
            run.font.name = FONT
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = RGBColor.from_string(color)


def _shape(slide, shape_type, left, top, width, height, color, *, line_color=None):
    shape = slide.shapes.add_shape(shape_type, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(color)
    shape.line.color.rgb = RGBColor.from_string(line_color or color)
    return shape


def _add_chrome(slide, section: str):
    _shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, 13.333, 0.63, "EFEFEF")
    _shape(slide, MSO_SHAPE.RECTANGLE, 0.0, 7.43, 13.333, 0.07, RED)
    _shape(slide, MSO_SHAPE.RECTANGLE, 12.76, 0.08, 0.45, 0.46, "FFFFFF")
    _shape(slide, MSO_SHAPE.RECTANGLE, 12.73, 0.08, 0.02, 0.46, RED)
    badge = slide.shapes.add_textbox(Inches(12.78), Inches(0.17), Inches(0.4), Inches(0.2))
    badge.text_frame.paragraphs[0].text = section
    badge.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    for run in badge.text_frame.paragraphs[0].runs:
        run.font.name, run.font.size, run.font.bold = FONT, Pt(10), True
    mark = _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.28, 0.13, 0.32, 0.32, RED)
    mark.text_frame.paragraphs[0].text = "ЖКХ"
    for run in mark.text_frame.paragraphs[0].runs:
        run.font.name, run.font.size, run.font.bold, run.font.color.rgb = FONT, Pt(5), True, RGBColor(255, 255, 255)
    unit = slide.shapes.add_textbox(Inches(0.68), Inches(0.12), Inches(3.4), Inches(0.35))
    unit.text_frame.paragraphs[0].text = "УПРАВЛЕНИЕ ЖИЛИЩНО-КОММУНАЛЬНОГО ХОЗЯЙСТВА"
    for run in unit.text_frame.paragraphs[0].runs:
        run.font.name, run.font.size, run.font.bold = FONT, Pt(7), True


def _add_title(slide, text: str, top=0.72):
    box = slide.shapes.add_textbox(Inches(3.55), Inches(top), Inches(8.7), Inches(0.34))
    paragraph = box.text_frame.paragraphs[0]
    paragraph.text = text
    paragraph.alignment = PP_ALIGN.CENTER
    run = paragraph.runs[0]
    run.font.name = FONT
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = RGBColor.from_string("4D4D4D")


def _add_metadata(slide, dashboard: StatsDashboardOut):
    generated = dashboard.generated_at.strftime("%d.%m.%Y %H:%M UTC")
    box = slide.shapes.add_textbox(Inches(9.1), Inches(7.08), Inches(3.35), Inches(0.16))
    paragraph = box.text_frame.paragraphs[0]
    paragraph.text = f"Методика v2 · МСК · сформировано {generated}"
    paragraph.alignment = PP_ALIGN.RIGHT
    for run in paragraph.runs:
        run.font.name, run.font.size = FONT, Pt(6)
        run.font.color.rgb = RGBColor.from_string("777777")


def render_shtab(dashboard: StatsDashboardOut, categories: StatsCategoriesOut) -> BytesIO:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    slide = prs.slides.add_slide(blank)
    _add_chrome(slide, "1.1")
    _add_title(slide, "Обходы детских и спортивных площадок САО — итоги периода")

    rows = sorted(
        dashboard.districts,
        key=lambda r: (-r.issues_closed_pct, -r.coverage_pct, r.district_name),
    )
    headers = ["№", "Район", "Площадок", "Обойдено", "% охвата", "Выявлено",
               "Устранено", "На доработке", "Не устранено", "% устранения"]
    table = slide.shapes.add_table(
        len(rows) + 2, len(headers), Inches(0.35), Inches(1.12), Inches(12.63), Inches(5.0)
    ).table
    widths = [0.35, 2.25, 0.85, 0.85, 0.8, 0.85, 0.85, 1.05, 1.0, 0.95]
    for column, width in zip(table.columns, widths):
        column.width = Inches(width)
    for index, header in enumerate(headers):
        table.cell(0, index).text = header
        _fill(table.cell(0, index), HEADER)
        _style_cell(table.cell(0, index), bold=True, color="FFFFFF")
    for row_index, row in enumerate(rows, start=1):
        values = [row_index, row.district_name, row.total_sites, row.sites_inspected,
                  row.coverage_pct, row.issues_found, row.issues_closed,
                  row.issues_revision, row.issues_not_fixed, row.issues_closed_pct]
        for col, value in enumerate(values):
            table.cell(row_index, col).text = str(value)
            _style_cell(table.cell(row_index, col), align=PP_ALIGN.LEFT if col == 1 else PP_ALIGN.CENTER)
        for col in (4, 9):
            _fill(table.cell(row_index, col), percentage_color(int(values[col])))
    total_index = len(rows) + 1
    total = dashboard.totals
    total_values = ["", "ИТОГО", total.total_sites, total.sites_inspected,
                    total.coverage_pct, total.issues_found, total.issues_closed,
                    total.issues_revision, total.issues_not_fixed, total.issues_closed_pct]
    for col, value in enumerate(total_values):
        table.cell(total_index, col).text = str(value)
        _fill(table.cell(total_index, col), TOTAL)
        _style_cell(table.cell(total_index, col), bold=True)

    p = dashboard.period
    summary = (
        f"За период с {p.date_from:%d.%m.%Y} по {p.date_to:%d.%m.%Y} инспекторами САО "
        f"обойдено {total.sites_inspected} из {total.total_sites} площадок ({total.coverage_pct}%). "
        f"Выявлено нарушений: {total.issues_found}, из них устранено и принято "
        f"{total.issues_closed} ({total.issues_closed_pct}%), на доработке {total.issues_revision}, "
        f"работы не начаты или в работе {total.issues_open + total.issues_in_work}."
    )
    _shape(slide, MSO_SHAPE.RECTANGLE, 0.35, 6.32, 0.02, 0.7, RED)
    box = slide.shapes.add_textbox(Inches(0.48), Inches(6.34), Inches(12.0), Inches(0.6))
    box.text_frame.paragraphs[0].text = summary
    for run in box.text_frame.paragraphs[0].runs:
        run.font.name, run.font.size = FONT, Pt(11)
    _add_metadata(slide, dashboard)

    slide2 = prs.slides.add_slide(blank)
    _add_chrome(slide2, "1.2")
    _add_title(slide2, "Нарушения по категориям")
    category_rows = categories.categories
    category_table = slide2.shapes.add_table(
        len(category_rows) + 1, 4, Inches(1.2), Inches(1.15), Inches(10.9), Inches(4.7)
    ).table
    for idx, title in enumerate(("Категория", "Выявлено", "Устранено", "% устранения")):
        category_table.cell(0, idx).text = title
        _fill(category_table.cell(0, idx), HEADER)
        _style_cell(category_table.cell(0, idx), bold=True, color="FFFFFF", size=11)
    for row_index, row in enumerate(category_rows, start=1):
        for col, value in enumerate((row.name, row.found, row.closed, row.closed_pct)):
            category_table.cell(row_index, col).text = str(value)
            _style_cell(category_table.cell(row_index, col), size=10,
                        align=PP_ALIGN.LEFT if col == 0 else PP_ALIGN.CENTER)
        _fill(category_table.cell(row_index, 3), percentage_color(row.closed_pct))
    if category_rows:
        problem = sorted(category_rows, key=lambda r: (-r.not_fixed, r.sort_order, r.name))[0]
        _shape(slide2, MSO_SHAPE.RECTANGLE, 1.05, 6.1, 0.02, 0.55, RED)
        note = slide2.shapes.add_textbox(Inches(1.2), Inches(6.13), Inches(10.9), Inches(0.4))
        note.text_frame.paragraphs[0].text = (
            f"Наиболее проблемная категория: {problem.name} — не устранено {problem.not_fixed}."
        )
        for run in note.text_frame.paragraphs[0].runs:
            run.font.name, run.font.size, run.font.bold = FONT, Pt(13), True
    _add_metadata(slide2, dashboard)

    output = BytesIO()
    prs.save(output)
    output.seek(0)
    return output
