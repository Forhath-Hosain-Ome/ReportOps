"""
------------------------
Copies one filled worksheet from a throwaway per-stage workbook into a
shared output workbook — values, styles, merged ranges, column widths
and row heights.

openpyxl's Workbook.copy_worksheet() only works within the same
workbook, so merging sheets from N separate template files into one
output file needs a manual cell-by-cell copy.
"""

from copy import copy


def copy_sheet(src_ws, dst_wb, title: str):
    """Copy src_ws into dst_wb as a new sheet named `title`. Returns the
    new worksheet."""
    dst_ws = dst_wb.create_sheet(title=title)

    for col_letter, dim in src_ws.column_dimensions.items():
        dst_ws.column_dimensions[col_letter].width = dim.width
        dst_ws.column_dimensions[col_letter].hidden = dim.hidden

    for row_idx, dim in src_ws.row_dimensions.items():
        dst_ws.row_dimensions[row_idx].height = dim.height

    for merged_range in src_ws.merged_cells.ranges:
        dst_ws.merge_cells(str(merged_range))

    for row in src_ws.iter_rows():
        for cell in row:
            if cell.value is None and not cell.has_style:
                continue
            new_cell = dst_ws.cell(row=cell.row, column=cell.column, value=cell.value)
            if cell.has_style:
                new_cell.font = copy(cell.font)
                new_cell.border = copy(cell.border)
                new_cell.fill = copy(cell.fill)
                new_cell.number_format = cell.number_format
                new_cell.protection = copy(cell.protection)
                new_cell.alignment = copy(cell.alignment)

    return dst_ws