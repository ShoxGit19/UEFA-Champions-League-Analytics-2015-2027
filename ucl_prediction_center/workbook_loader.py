"""Read all worksheets and inspect formulas/types without saving via openpyxl."""
import hashlib
import warnings
import pandas as pd
from openpyxl import load_workbook

def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_source(path):
    fingerprint = file_hash(path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        book = load_workbook(path, read_only=True, data_only=True, keep_links=True)
        frames, schema = {}, {}
        try:
            for sheet in book:
                rows = list(sheet.iter_rows(values_only=True))
                headers = [str(c).strip() if c is not None else f'_UNNAMED_{i+1}' for i, c in enumerate(rows[0])] if rows else []
                data = [r for r in rows[1:] if any(v is not None for v in r)]
                frame = pd.DataFrame(data, columns=headers)
                # Retain actual Excel row indices even when blank rows exist.
                if rows:
                    frame.index = [i for i, r in enumerate(rows[1:]) if any(v is not None for v in r)]
                k = sheet.title.casefold()
                if k in frames:
                    raise ValueError(f'Ambiguous sheet name: {sheet.title}')
                frames[k] = frame
                schema[sheet.title] = {'rows': len(frame), 'columns': headers,
                    'dtypes': {str(c): str(frame[c].dtype) for c in frame.columns},
                    'missing_values': {str(c): int(frame[c].isna().sum()) for c in frame.columns}}
        finally:
            book.close()
    if 'matches' not in frames:
        raise ValueError('Workbook has no matches sheet.')
    return frames, schema, fingerprint, sorted({str(w.message) for w in caught})
