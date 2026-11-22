"""Strict adapter for three-level, merged-header monthly inspection tables.

Only the operational detail table is authority. Date echoes, calendar placeholders,
historical sheets, subtotal formulas and Top-5 presentation are never records.
Source formula quantities require cached results, as in the existing Raw parser.
"""
from collections import Counter
from dataclasses import dataclass

from .parser import (ALIASES, DefectColumn, fail, inspection_day, optional_integer,
                     ratio, read_cell, semantic)
from .workbook_security import WorkbookValidationError, bounded_sheet


@dataclass(frozen=True)
class MonthlyMapping:
    header: int
    fields: dict
    defects: tuple
    headers: tuple
    echo_column: int
    total_row: int
    numbered: bool = True


def _quantity(ws, cached, row, col, *, required=False):
    return optional_integer(read_cell(ws, cached, row, col, input='hundred_percent'),
                            ws=ws, cell=ws.cell(row, col).coordinate,
                            input='hundred_percent', required=required)


class StructuredMonthly100Adapter:
    name = 'structured_monthly_100'
    # Explicit format policy, never inherited by unrelated future adapters.
    blank_defects_are_zero = True

    @staticmethod
    def recognizes(mapping):
        return isinstance(mapping, MonthlyMapping)

    @staticmethod
    def resolve(ws):
        bounded_sheet(ws)
        candidates = []
        aliases = {**ALIASES, 'item': {'item', 'iteam', 'itemname'},
                   'ratio': {'defectratio', 'defectpercentage'}}
        required = {'style', 'item', 'person', 'inspected', 'defect', 'pass', 'ratio'}
        for row in ws.iter_rows(max_row=min(ws.max_row, 38)):
            found = {}
            for cell in row:
                for key, labels in aliases.items():
                    if semantic(cell.value) in labels:
                        found.setdefault(key, []).append(cell.column)
            if not required.issubset(found):
                continue
            top = row[0].row
            # Multi-row vertical business headers prove this profile before its
            # defect schema is validated. Ordinary flat tables do not match.
            if not all(any(m.min_row == top and m.max_row == top+2
                           and m.min_col == m.max_col == col
                           for m in ws.merged_cells)
                       for key in required for col in found[key]):
                continue
            if any(len(found[key]) != 1 for key in required):
                fail('AMBIGUOUS_100_FORMAT', 'Monthly business headers are ambiguous.',
                     ws, input='hundred_percent')
            fields = {key: found[key][0] for key in required}
            style = fields['style']
            date_area = next((m for m in ws.merged_cells if m.min_row == top
                              and m.max_row == top+2 and m.min_col == style-2
                              and m.max_col == style-1), None)
            if date_area is None:
                continue
            fields['date'] = date_area.max_col
            candidates.append((top, fields, date_area.min_col))
        if not candidates:
            return None
        if len(candidates) != 1:
            fail('AMBIGUOUS_100_FORMAT', 'Multiple monthly operational headers found.',
                 ws, input='hundred_percent')
        top, fields, echo = candidates[0]
        if not (fields['item'] == fields['style']+1
                and fields['person'] == fields['item']+1
                and fields['inspected'] == fields['person']+1
                and fields['pass'] == fields['defect']+1
                and fields['ratio'] == fields['pass']+1):
            fail('DEFECT_SCHEMA_UNRECOGNIZED', 'Monthly operational fields are not contiguous.',
                 ws, input='hundred_percent')
        first, last = fields['inspected']+1, fields['defect']-1
        if last < first:
            fail('DEFECT_SCHEMA_UNRECOGNIZED', 'Monthly defect region is empty.',
                 ws, input='hundred_percent')
        spans = []
        for band in ws.merged_cells:
            if band.min_row != top or band.max_row != top:
                continue
            if band.max_col < first or band.min_col > last:
                continue
            if band.min_col < first or band.max_col > last:
                fail('DEFECT_COLUMN_INVALID', 'A category overlaps a business result column.',
                     ws, input='hundred_percent')
            if ws.cell(top, band.min_col).data_type == 'f':
                fail('DEFECT_COLUMN_INVALID', 'Category captions must be literal source labels.',
                     ws, ws.cell(top, band.min_col).coordinate, 'hundred_percent')
            spans.append((band.min_col, band.max_col,
                          ws.cell(top, band.min_col).value))
        definitions = []
        occurrences = Counter()
        for ordinal, col in enumerate(range(first, last+1), 1):
            number = ws.cell(top+1, col)
            if type(number.value) is not int or number.value != ordinal:
                fail('DEFECT_NUMBERING_INVALID', 'Monthly numbering must cover integer 1..N in source order.',
                     ws, number.coordinate, 'hundred_percent')
            categories = [label for lo, hi, label in spans if lo <= col <= hi]
            if not categories:
                if ws.cell(top, col).data_type == 'f':
                    fail('DEFECT_COLUMN_INVALID', 'Category captions must be literal source labels.',
                         ws, ws.cell(top, col).coordinate, 'hundred_percent')
                categories = [ws.cell(top, col).value]  # Explicit singleton category.
            if len(categories) != 1 or not isinstance(categories[0], str) or not categories[0].strip():
                fail('DEFECT_COLUMN_INVALID', 'Every monthly defect needs one explicit category.',
                     ws, ws.cell(top, col).coordinate, 'hundred_percent')
            label = ws.cell(top+2, col)
            if label.data_type == 'f' or not isinstance(label.value, str) or not label.value.strip():
                fail('DEFECT_COLUMN_INVALID', 'Every numbered monthly defect needs a literal label.',
                     ws, label.coordinate, 'hundred_percent')
            category, text = categories[0].strip(), label.value.strip()
            key = semantic(category), semantic(text)
            occurrences[key] += 1
            definitions.append(DefectColumn(col, category, text, ordinal,
                                            occurrences[key], number.value))
        # A numbered field beyond the proven region cannot be silently dropped.
        if any(type(c.value) is int for c in ws[top+1] if not first <= c.column <= last):
            fail('DEFECT_NUMBERING_INVALID', 'Numbered fields extend outside the monthly defect region.',
                 ws, input='hundred_percent')
        # This profile's auxiliary header cells are formulas only. Literal
        # fields outside the proven result boundary are not silently omitted.
        for row in ws.iter_rows(min_row=top, max_row=top+2):
            for cell in row:
                if (cell.column < echo or cell.column > fields['ratio']) and cell.value not in (None, '') and cell.data_type != 'f':
                    fail('DEFECT_COLUMN_INVALID', 'An unclassified monthly header is outside the operational table.',
                         ws, cell.coordinate, 'hundred_percent')
        totals = [r for r in range(top+3, ws.max_row+1)
                  if semantic(ws.cell(r, echo).value) == 'total']
        if len(totals) != 1:
            fail('AMBIGUOUS_100_FORMAT' if totals else 'DEFECT_SCHEMA_UNRECOGNIZED',
                 'Exactly one operational TOTAL boundary is required.', ws, input='hundred_percent')
        headers = [''] * fields['ratio']
        for key, col in fields.items():
            headers[col-1] = {'date': 'Inspection Date', 'item': 'Item Name',
                              'ratio': 'Defect Ratio'}.get(key, str(ws.cell(top, col).value).strip())
        for definition in definitions:
            headers[definition.column-1] = definition.label
        return MonthlyMapping(top+2, fields, tuple(definitions), tuple(headers), echo, totals[0])

    @staticmethod
    def parse(ws, cached, mapping):
        from .raw_parser import normalize_hundred

        fields, definitions = mapping.fields, mapping.defects
        records = []
        for row in ws.iter_rows(min_row=mapping.header+1, max_row=mapping.total_row):
            for cell in row:
                if (cell.column < mapping.echo_column or cell.column > fields['ratio']) and cell.value not in (None, '') and cell.data_type != 'f':
                    fail('DEFECT_COLUMN_INVALID', 'Unclassified data is outside the monthly operational table.',
                         ws, cell.coordinate, 'hundred_percent')
        for row in range(mapping.header+1, mapping.total_row):
            marker = semantic(ws.cell(row, mapping.echo_column).value)
            if marker == 'weeklysubtotal':
                if any(ws.cell(row, fields[k]).value not in (None, '') for k in ('style', 'item')):
                    fail('DEFECT_COLUMN_INVALID', 'A subtotal contains conflicting detail identity.',
                         ws, ws.cell(row, mapping.echo_column).coordinate, 'hundred_percent')
                continue
            # Ignore only proven blank/date-only placeholders. Result formulas
            # exist in those template rows and are not business-record evidence.
            identity = [ws.cell(row, fields[k]).value for k in ('style', 'item', 'person', 'inspected')]
            defect_values = [ws.cell(row, d.column).value for d in definitions]
            blank_defects = all(v in (None, '') or type(v) in (int, float) and v == 0
                                for v in defect_values)
            if all(v in (None, '') for v in identity) and blank_defects:
                continue
            style = read_cell(ws, cached, row, fields['style'], input='hundred_percent')
            if style is None or isinstance(style, str) and not style.strip():
                fail('REQUIRED_VALUE_MISSING', 'A monthly inspection record needs a style.',
                     ws, ws.cell(row, fields['style']).coordinate, 'hundred_percent')
            day = inspection_day(read_cell(ws, cached, row, fields['date'], input='hundred_percent'),
                                 ws=ws, cell=ws.cell(row, fields['date']).coordinate, input='hundred_percent')
            quantities = []
            for definition in definitions:
                try:
                    value = read_cell(ws, cached, row, definition.column, input='hundred_percent')
                    if value in (None, '') and StructuredMonthly100Adapter.blank_defects_are_zero:
                        value = 0  # This adapter's positively recognized numbered schema.
                    quantities.append(optional_integer(value, ws=ws,
                                      cell=ws.cell(row, definition.column).coordinate,
                                      input='hundred_percent', required=True))
                except WorkbookValidationError as exc:
                    if exc.code == 'FORMULA_VALUE_UNAVAILABLE':
                        raise
                    fail('DEFECT_QUANTITY_INVALID', exc.detail['detail'], ws,
                         ws.cell(row, definition.column).coordinate, 'hundred_percent')
            inspected = _quantity(ws, cached, row, fields['inspected'], required=True)
            defects = _quantity(ws, cached, row, fields['defect'], required=True)
            passed = _quantity(ws, cached, row, fields['pass'])
            if sum(quantities) != defects or passed is not None and passed != inspected-defects:
                fail('DEFECT_TOTAL_MISMATCH', 'Monthly detail quantities do not reconcile.',
                     ws, ws.cell(row, fields['defect']).coordinate, 'hundred_percent')
            item = read_cell(ws, cached, row, fields['item'], input='hundred_percent')
            person = read_cell(ws, cached, row, fields['person'], input='hundred_percent')
            source = [None] * len(mapping.headers)
            for key, value in [('date', day), ('style', style), ('item', item), ('person', person),
                               ('inspected', inspected), ('defect', defects), ('pass', passed),
                               ('ratio', ratio(defects, inspected))]:
                source[fields[key]-1] = value
            for definition, quantity in zip(definitions, quantities):
                source[definition.column-1] = quantity
            records.append({'date': day, 'style': style, 'item': None if item in (None, '') else str(item).strip(),
                            'person': None if person in (None, '') else str(person).strip(), 'factory': None,
                            'inspected': inspected, 'defect': defects, 'pass': passed,
                            'categories': quantities, 'source_values': source})
        block = normalize_hundred(ws, mapping, records, StructuredMonthly100Adapter.name,
                                  StructuredMonthly100Adapter.blank_defects_are_zero)
        expected = {fields['inspected']: block.inspected_qty, fields['defect']: block.defect_qty,
                    fields['pass']: block.pass_qty,
                    **{d.column: q for d, q in zip(definitions, block.defect_totals)}}
        for col, quantity in expected.items():
            cell = ws.cell(mapping.total_row, col)
            # Cached presentation totals are verification only, never a fallback
            # source of detail quantities. Uncached totals may be omitted safely.
            if cell.value in (None, '') or cell.data_type == 'f' and cached.cell(mapping.total_row, col).value is None:
                continue
            actual = _quantity(ws, cached, mapping.total_row, col, required=True)
            if actual != quantity:
                fail('DEFECT_TOTAL_MISMATCH', 'Cached monthly TOTAL differs from normalized detail records.',
                     ws, cell.coordinate, 'hundred_percent')
        return block
