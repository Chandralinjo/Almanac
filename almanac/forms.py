"""Ingredient form parsing, independently testable without a window."""
from .storage import validate_record


def parse_number(value, label, unknown=False):
    value = value.strip()
    if not value and unknown:
        return None
    # Accept the decimal comma commonly entered by Android locale keyboards.
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        raise ValueError(f'{label}: enter a number' + (' or leave blank for unknown' if unknown else '')) from None


def parse_form(values, conversion_rows, original):
    record = dict(original)
    record.update(name=values['name'].strip(), category=values['category'].strip(),
                  reference_amount=parse_number(values['reference_amount'], 'Reference amount'),
                  reference_unit=values['reference_unit'].strip(),
                  nutrition={n:parse_number(values[n], n.capitalize(), unknown=True)
                             for n in ('calories','protein','carbs','fat')})
    conversions, descriptions = {}, {}
    for unit, factor, description in conversion_rows:
        unit = unit.strip()
        if not unit and not factor.strip() and not description.strip():
            continue
        if not unit:
            raise ValueError('Every conversion needs an input unit')
        if unit in conversions:
            raise ValueError(f'Duplicate conversion unit: {unit}')
        conversions[unit] = parse_number(factor, f'Conversion for {unit}')
        descriptions[unit] = description.strip()
    record.update(conversions=conversions, conversion_descriptions=descriptions)
    return validate_record(record)


def blank_record():
    return dict(id='new', name='', category='', nutrition={n:None for n in ('calories','protein','carbs','fat')},
                reference_amount=100, reference_unit='g', conversions={}, conversion_descriptions={},
                source='Personal ingredient', source_id='')
