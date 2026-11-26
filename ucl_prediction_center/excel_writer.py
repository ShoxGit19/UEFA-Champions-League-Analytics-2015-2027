"""Surgical OOXML updates preserve unsupported Excel assets byte-for-byte.

openpyxl reads/verifies the workbook. Saving the original with it would discard
some Excel extensions, so only prediction XML/table and audit parts are patched.
A source hash and in-memory ZIP verification guard updates to the existing file.
"""
from datetime import datetime
from io import BytesIO
import hashlib
import json
import math
import os
from pathlib import Path,PurePosixPath
import posixpath
from xml.dom import minidom
from zipfile import ZipFile,ZIP_DEFLATED
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter,column_index_from_string
from openpyxl.utils.datetime import to_excel
from config import OUTPUT_COLUMNS
from workbook_loader import file_hash
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'
C='http://schemas.openxmlformats.org/package/2006/content-types'

class WorkbookLockedError(PermissionError):
    def __init__(self,message,receipt):
        super().__init__(message)
        self.receipt=receipt

def local(node,name): return node.nodeType==node.ELEMENT_NODE and node.localName==name

def children(node,name): return [n for n in node.childNodes if local(n,name)]

def descendants(node,name): return list(node.getElementsByTagNameNS('*',name))

def element(doc,name,namespace=S): return doc.createElementNS(namespace,name)

def parse(data): return minidom.parseString(data)

def serialized(doc): return doc.toxml(encoding='utf-8')

def resolve(base,target):
    return target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(base),target))

def string_value(cell,shared):
    if cell.getAttribute('t')=='s':
        v=descendants(cell,'v'); return shared[int(v[0].firstChild.data)] if v else ''
    return ''.join(n.firstChild.data for n in descendants(cell,'t') if n.firstChild)

def set_cell(doc,cell,value,allow_formula=False):
    formulas=descendants(cell,'f')
    if formulas and not allow_formula: raise ValueError(f'Refusing to replace formula at {cell.getAttribute("r")}; move it outside managed output columns.')
    if formulas:
        for attr in ['cm','vm']:
            if cell.hasAttribute(attr): cell.removeAttribute(attr)
    for child in list(cell.childNodes):
        if child.nodeType==child.ELEMENT_NODE and child.localName in {'v','is','f'}: cell.removeChild(child)
    if cell.hasAttribute('t'): cell.removeAttribute('t')
    if value is None or (not isinstance(value,(list,dict)) and pd.isna(value)): return
    if isinstance(value,(datetime,pd.Timestamp)):
        value=to_excel(pd.Timestamp(value).to_pydatetime().replace(tzinfo=None))
    if isinstance(value,(int,float,np.number)):
        if not math.isfinite(float(value)): raise ValueError('Non-finite Excel output')
        node=element(doc,'v'); node.appendChild(doc.createTextNode(str(value)));cell.appendChild(node)
    else:
        cell.setAttribute('t','inlineStr'); node=element(doc,'is'); text=element(doc,'t')
        text.setAttribute('xml:space','preserve');text.appendChild(doc.createTextNode(str(value)));node.appendChild(text);cell.appendChild(node)

def patch_sheet(data,records,columns,shared,preserve=True):
    doc=parse(data); root=doc.documentElement
    sheetdata=children(root,'sheetData')[0]
    rows={int(r.getAttribute('r')):r for r in children(sheetdata,'row')}
    header=rows.get(1)
    existing={}
    if header:
        for c in children(header,'c'):
            value=string_value(c,shared)
            if value in existing: raise ValueError('Duplicate predictions header: '+value)
            existing[value]=column_index_from_string(''.join(c for c in c.getAttribute('r') if c.isalpha()))
    if preserve:
        # Existing headers, positions and custom columns remain intact.
        positions=dict(existing); last=max(existing.values(),default=0)
        for name in columns:
            if name not in positions: last+=1;positions[name]=last
    else: positions={c:i+1 for i,c in enumerate(columns)}
    styles={}
    if 2 in rows:
        for cell in children(rows[2],'c'):
            styles[''.join(c for c in cell.getAttribute('r') if c.isalpha())]=cell.getAttribute('s')
    for ri in range(1,max(max(rows,default=1),len(records)+1)+1):
        if ri not in rows:
            row=element(doc,'row');row.setAttribute('r',str(ri));sheetdata.appendChild(row);rows[ri]=row
        row=rows[ri]; row.setAttribute('spans',f'1:{max(positions.values())}'); cells={c.getAttribute('r'):c for c in children(row,'c')}
        for name in columns:
            letter=get_column_letter(positions[name]); ref=f'{letter}{ri}'
            cell=cells.get(ref)
            if cell is None:
                cell=element(doc,'c');cell.setAttribute('r',ref)
                style=(styles.get(letter) or (styles.get('B') if name in {'DATE_TIME','PREDICTION_CREATED_AT'} else None)) if ri>1 else (children(header,'c')[0].getAttribute('s') if header and children(header,'c') else None)
                if style: cell.setAttribute('s',style)
                cells[ref]=cell;row.appendChild(cell)
            value=name if ri==1 else records[ri-2].get(name) if ri-2<len(records) else None
            set_cell(doc,cell,value,allow_formula=name in OUTPUT_COLUMNS[6:])
        # OOXML cells must be in column order, including pre-existing custom fields.
        for cell in children(row,'c'): row.removeChild(cell)
        for ref in sorted(cells,key=lambda v:column_index_from_string(''.join(c for c in v if c.isalpha()))): row.appendChild(cells[ref])
    lastcol=max(positions.values()); lastrow=max(len(records)+1,1)
    dim=children(root,'dimension')
    if dim:
        # Keep dimension large enough for preserved custom cells.
        endcol=max(lastcol,max((column_index_from_string(''.join(c for c in v.getAttribute('r') if c.isalpha())) for v in descendants(sheetdata,'c')),default=1))
        dim[0].setAttribute('ref',f'A1:{get_column_letter(endcol)}{max(rows)}')
    filters=children(root,'autoFilter')
    for f in filters: f.setAttribute('ref',f'A1:{get_column_letter(lastcol)}{lastrow}')
    return serialized(doc),positions,lastrow

def patch_table(data,positions,lastrow):
    doc=parse(data);root=doc.documentElement
    oldref=root.getAttribute('ref')
    if not oldref.startswith('A1:'): raise ValueError('Predictions table must start at A1')
    ref=f'A1:{get_column_letter(max(positions.values()))}{lastrow}'
    root.setAttribute('ref',ref)
    for f in children(root,'autoFilter'): f.setAttribute('ref',ref)
    tablecols=children(root,'tableColumns')[0]
    existing=children(tablecols,'tableColumn')
    for col in existing:
        if col.getAttribute('name') in OUTPUT_COLUMNS[6:]:
            for formula in children(col,'calculatedColumnFormula'): col.removeChild(formula)
    byposition={i+1:n for i,n in enumerate(existing)}
    nextid=max((int(n.getAttribute('id')) for n in existing),default=0)
    reverse={i:n for n,i in positions.items()}
    for pos in range(1,max(positions.values())+1):
        if pos not in byposition:
            nextid+=1;col=element(doc,'tableColumn');col.setAttribute('id',str(nextid));col.setAttribute('name',reverse[pos]);tablecols.appendChild(col)
    tablecols.setAttribute('count',str(len(children(tablecols,'tableColumn'))))
    return serialized(doc)

def audit_values(audit):
    rows=[]
    for k,v in audit.items():
        text=json.dumps(v,ensure_ascii=False,default=str) if isinstance(v,(dict,list)) else str(v)
        # Excel cell text has a 32767-character limit. Split long audit values.
        for i in range(0,max(1,len(text)),30000):
            rows.append({'KEY':k if i==0 else f'{k} (continued {i//30000+1})','VALUE':text[i:i+30000]})
    return rows

def update_workbook(path,predictions,audit,expected_hash):
    path=Path(path)
    if file_hash(path)!=expected_hash: raise RuntimeError('Workbook changed since it was read. Rerun to avoid overwriting edits.')
    with ZipFile(path) as source:
        originals={entry.filename:source.read(entry.filename) for entry in source.infolist()}
        infos=source.infolist(); archive_comment=source.comment
    parts=dict(originals); shared=[]
    if 'xl/sharedStrings.xml' in parts:
        sd=parse(parts['xl/sharedStrings.xml'])
        shared=[''.join(t.firstChild.data for t in descendants(si,'t') if t.firstChild) for si in descendants(sd,'si')]
    workbook=parse(parts['xl/workbook.xml']);rels=parse(parts['xl/_rels/workbook.xml.rels']);ctype=parse(parts['[Content_Types].xml'])
    sheetnodes=descendants(workbook,'sheet')
    relationship={n.getAttribute('Id'):n for n in descendants(rels,'Relationship')}
    lookup={s.getAttribute('name').casefold():s for s in sheetnodes}
    if 'predictions' not in lookup: raise ValueError('Existing predictions sheet is required; no sheets have been removed.')
    def sheetpath(node):return resolve('xl/workbook.xml',relationship[node.getAttribute('r:id')].getAttribute('Target'))
    predpath=sheetpath(lookup['predictions'])
    preddoc=parse(parts[predpath])
    original_headers={''.join(c for c in cell.getAttribute('r') if c.isalpha()):string_value(cell,shared)
                      for row in descendants(preddoc,'row') if row.getAttribute('r')=='1' for cell in children(row,'c')}
    formula_archive=[]
    for cell in descendants(preddoc,'c'):
        ref=cell.getAttribute('r'); letter=''.join(c for c in ref if c.isalpha())
        if original_headers.get(letter) in OUTPUT_COLUMNS[6:]:
            for formula in children(cell,'f'):
                formula_archive.append({'cell':ref,'header':original_headers[letter],
                    'formula_xml':formula.toxml()})
    if formula_archive:
        audit['replaced_prediction_formulas']=formula_archive
        audit['formula_replacement_reason']='Old prediction-model formulas must be replaced by externally trained numeric outputs. Original formulas are archived here in the workbook audit. Source-sheet formulas and custom columns are unchanged.'
    newxml,positions,lastrow=patch_sheet(parts[predpath],predictions.to_dict('records'),OUTPUT_COLUMNS,shared)
    parts[predpath]=newxml
    predrels=posixpath.join(posixpath.dirname(predpath),'_rels',posixpath.basename(predpath)+'.rels')
    if predrels in parts:
        for rel in descendants(parse(parts[predrels]),'Relationship'):
            if rel.getAttribute('Type').endswith('/table'):
                target=resolve(predpath,rel.getAttribute('Target'))
                tabledoc=parse(parts[target])
                table_formulas=[]
                for col in descendants(tabledoc,'tableColumn'):
                    if col.getAttribute('name') in OUTPUT_COLUMNS[6:]:
                        for formula in children(col,'calculatedColumnFormula'):
                            table_formulas.append({'header':col.getAttribute('name'),'formula_xml':formula.toxml()})
                if table_formulas: audit['replaced_prediction_table_formulas']=table_formulas
                parts[target]=patch_table(parts[target],positions,lastrow)
    # Remove only obsolete calculation-chain entries for replaced output formulas.
    if formula_archive and 'xl/calcChain.xml' in parts:
        chain=parse(parts['xl/calcChain.xml']); current_sheet=None
        pred_sheet_id=lookup['predictions'].getAttribute('sheetId')
        replaced={item['cell'] for item in formula_archive}
        for node in list(children(chain.documentElement,'c')):
            if node.hasAttribute('i'): current_sheet=node.getAttribute('i')
            if current_sheet==pred_sheet_id and node.getAttribute('r') in replaced:
                chain.documentElement.removeChild(node)
            elif current_sheet is not None: node.setAttribute('i',current_sheet)
        if children(chain.documentElement,'c'):
            parts['xl/calcChain.xml']=serialized(chain)
        else:
            del parts['xl/calcChain.xml']
            for node in list(descendants(rels,'Relationship')):
                if node.getAttribute('Type').endswith('/calcChain'): node.parentNode.removeChild(node)
            for node in list(descendants(ctype,'Override')):
                if node.getAttribute('PartName')=='/xl/calcChain.xml': node.parentNode.removeChild(node)
            parts['xl/_rels/workbook.xml.rels']=serialized(rels)
            parts['[Content_Types].xml']=serialized(ctype)
    if 'model_audit' in lookup:
        apath=sheetpath(lookup['model_audit'])
        parts[apath],_,_=patch_sheet(parts[apath],audit_values(audit),['KEY','VALUE'],shared)
    else:
        ids=[int(s.getAttribute('sheetId')) for s in sheetnodes]
        number=1
        while f'xl/worksheets/ucl_audit_{number}.xml' in parts: number+=1
        apath=f'xl/worksheets/ucl_audit_{number}.xml'
        relationid='rIdUclAudit'
        while relationid in relationship: relationid+='X'
        node=element(workbook,'sheet');node.setAttribute('name','model_audit');node.setAttribute('sheetId',str(max(ids)+1));node.setAttributeNS(R,'r:id',relationid)
        descendants(workbook,'sheets')[0].appendChild(node)
        node=element(rels,'Relationship',P);node.setAttribute('Id',relationid);node.setAttribute('Type',R+'/worksheet');node.setAttribute('Target',apath[3:]);rels.documentElement.appendChild(node)
        node=element(ctype,'Override',C);node.setAttribute('PartName','/'+apath);node.setAttribute('ContentType','application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml');ctype.documentElement.appendChild(node)
        template=f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{S}"><dimension ref="A1:B1"/><sheetData/></worksheet>'.encode()
        parts[apath],_,_=patch_sheet(template,audit_values(audit),['KEY','VALUE'],[],False)
        parts['xl/workbook.xml']=serialized(workbook);parts['xl/_rels/workbook.xml.rels']=serialized(rels);parts['[Content_Types].xml']=serialized(ctype)
    managed={k for k,v in parts.items() if originals.get(k)!=v} | (originals.keys()-parts.keys())
    staged=BytesIO()
    with ZipFile(staged,'w',ZIP_DEFLATED) as target:
        target.comment=archive_comment
        for info in infos:
            if info.filename in parts: target.writestr(info,parts[info.filename])
        for name in parts.keys()-originals.keys(): target.writestr(name,parts[name])
    with ZipFile(staged) as target:
        if target.testzip(): raise ValueError('Staged workbook ZIP CRC failed')
        for name,content in originals.items():
            if name not in managed and target.read(name)!=content: raise AssertionError('Unmanaged workbook part changed: '+name)
    verify=load_workbook(staged,read_only=True,data_only=True)
    try:
        names=verify.sheetnames
        if 'model_audit' not in names: raise AssertionError('Audit missing')
        ws=next(s for s in verify if s.title.casefold()=='predictions')
        values=list(ws.iter_rows(values_only=True)); heads=list(values[0])
        actual=[r[heads.index('MATCH_ID')] for r in values[1:] if r[heads.index('MATCH_ID')] is not None]
        if actual!=predictions.MATCH_ID.tolist(): raise AssertionError('Saved fixture IDs differ')
        for i,row in predictions.iterrows():
            for col in ['HOME_WIN_PROB','DRAW_PROB','AWAY_WIN_PROB']:
                expected=row[col]; stored=values[i+1][heads.index(col)]
                if pd.notna(expected) and (not isinstance(stored,(int,float)) or abs(stored-expected)>1e-12): raise AssertionError('Excel numeric verification failed')
    finally: verify.close()
    receipt={'status':'UPDATED','workbook':str(path),'source_sha256':expected_hash,
        'modified_parts':sorted(managed),'preserved_parts':len(originals)-len(managed & originals.keys()),
        'replaced_prediction_formula_count':len(formula_archive)}
    content=staged.getvalue()
    try:
        # r+b requires an existing file and never truncates it on open.
        with path.open('r+b') as destination:
            original=destination.read()
            if hashlib.sha256(original).hexdigest()!=expected_hash:
                raise RuntimeError('Workbook changed while staging. Rerun.')
            try:
                destination.seek(0)
                destination.write(content)
                destination.truncate()
                destination.flush()
                os.fsync(destination.fileno())
            except Exception:
                # Restore from memory if writing fails; no disk copy is created.
                destination.seek(0)
                destination.write(original)
                destination.truncate()
                destination.flush()
                os.fsync(destination.fileno())
                raise
    except PermissionError as exc:
        receipt['status']='PENDING_WORKBOOK_LOCK'
        raise WorkbookLockedError('Excel is locking the workbook or write access is denied. Close it, then rerun python main.py. No separate workbook was created.',receipt) from exc
    receipt['workbook_sha256']=hashlib.sha256(content).hexdigest()
    return receipt
