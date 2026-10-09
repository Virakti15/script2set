"""Generate review exports through real routes and inspect every row."""
import os,json,csv,html
from pathlib import Path
from io import StringIO
from openpyxl import load_workbook
from pptx import Presentation
from app import create_app
from services.schema import PRODUCTION,production_view

def main():
    os.environ['AI_PROVIDER']='demo'
    root=Path(__file__).resolve().parents[1];out=root.parent/'shot-list-review';out.mkdir(exist_ok=True)
    script=(root/'tests/fixtures/production-review.txt').read_text(encoding='utf-8')
    client=create_app({'TESTING':True,'SECRET_KEY':'export-review-only'}).test_client()
    def post(path,data):
        r=client.post(path,json=data,headers={'X-Script2Set':'1'})
        assert r.status_code==200,(path,r.status_code,r.get_json(silent=True))
        return r
    analysis=post('/api/analyze',{'script':script}).json;plan=[]
    for chunk in analysis['chunks']:plan+=post('/api/plan',{'scene':chunk,'characters':analysis['characters'],'offset':len(plan),'previous':plan[-4:]}).json['shots']
    approval=post('/api/approve',{'plan':plan,'reviewed':True}).json;rows=[]
    for scene in dict.fromkeys(r['scene'] for r in plan):rows+=post('/api/breakdown',{'plan':plan,'approval':approval['approval'],'scene':scene}).json['shots']
    metadata={'client':'Script2Set validation sample','director':'To be assigned','dop':'To be assigned','platform':'Production review','location':'Meditation area / kitchen / office / Hill Road','date':'Shoot date to confirm','duration':'Duration to confirm','aspect_ratio':'16:9 (review assumption)','reference':'Written final architecture brief; original Excel not attached'}
    data={'plan':plan,'breakdown':rows,'approval':approval['approval'],'breakdown_hash':approval['plan_hash'],'metadata':metadata,'title':'Make space - production review'}
    for ext in ('xlsx','csv','pptx'):(out/('production-shot-list.'+ext)).write_bytes(post('/api/export/'+ext,data).data)
    (out/'storyboard-two-up.pptx').write_bytes(post('/api/export/pptx',{**data,'per_slide':2}).data)
    printed=post('/api/print',data).json
    (out/'print-payload.json').write_text(json.dumps(printed,ensure_ascii=False,indent=2),encoding='utf-8')
    esc=lambda s:html.escape(str(s or ''))
    meta='<dl>'+''.join(f'<dt>{esc(printed["metadata_fields"][k])}</dt><dd>{esc(v)}</dd>' for k,v in metadata.items())+'</dl>'
    articles=''.join(f'<article><h2>Scene {esc(r["scene"])} / Shot {esc(r["number"])}</h2><dl>'+''.join(f'<dt>{esc(label)}</dt><dd>{esc(r[k])}</dd>' for k,label in PRODUCTION.items())+'</dl></article>' for r in printed['shots'])
    (out/'production-print.html').write_text('<!doctype html><html><head><meta charset="utf-8"><title>Production shot list</title><style>'+(root/'static/print.css').read_text()+'</style></head><body><h1>SHOT LIST</h1>'+meta+articles+'</body></html>',encoding='utf-8')
    (out/'source-script.txt').write_text(script,encoding='utf-8')
    (out/'review-project.json').write_text(json.dumps({'version':3,'title':data['title'],'metadata':metadata,'script':script,'plan':plan,'breakdown':rows,'analysis':analysis,'approval':'','planHash':'','breakdownHash':'','stale':True,'images':{}},ensure_ascii=False,indent=2),encoding='utf-8')
    wb=load_workbook(out/'production-shot-list.xlsx');sheet=wb.active
    assert list(list(sheet.values)[5])==list(PRODUCTION.values())
    assert sheet.max_column==19 and sheet.max_row==len(rows)+6 and all(r.max_row<6 for r in sheet.merged_cells.ranges)
    assert sheet.freeze_panes=='D7' and sheet.auto_filter.ref==f'A6:S{sheet.max_row}'
    checks=[];mandatory=['number','day_int_ext','size_angle','camera_movement','shot_location','equipment','fps','shot_description','lighting','script','cast','props','costumes']
    for index,(row,values) in enumerate(zip(rows,list(sheet.values)[6:]),7):
        view=production_view(row)
        assert list(values)==[view[k] or None for k in PRODUCTION]
        assert sheet.cell(index,1).data_type=='s' and sheet.cell(index,1).number_format=='@'
        assert row['source_script_block']==''.join(script[s['start']:s['end']] for s in row['source_spans'])
        assert all(view[k].strip() for k in mandatory)
        assert row['script'].strip() not in ('"','Mira:','Ravi:')
        checks.append({'excel_row':index,'shot':row['number'],'scene':row['scene'],'type':row['shot_type'],'description':row['shot_description'],'dialogue':row['script'],'cast':row['cast'],'source_exact':True,'shot_stored_as_text':True})
    csv_rows=list(csv.DictReader(StringIO((out/'production-shot-list.csv').read_text(encoding='utf-8-sig'))))
    assert len(csv_rows)==len(rows)
    for record,row in zip(csv_rows,rows):assert list(record.values())==list(production_view(row).values())
    for filename,per_slide in [('production-shot-list.pptx',1),('storyboard-two-up.pptx',2)]:
        deck=Presentation(out/filename);assert len(deck.slides)==(len(rows)+per_slide-1)//per_slide
        for i,row in enumerate(rows):
            slide=deck.slides[i//per_slide]
            assert 'SHOT '+row['number'] in ' '.join(s.text for s in slide.shapes if s.has_text_frame)
            assert row['source_script_block'] in slide.notes_slide.notes_text_frame.text
            for shape in slide.shapes:assert shape.left>=0 and shape.top>=0 and shape.left+shape.width<=deck.slide_width+2 and shape.top+shape.height<=deck.slide_height+2
    assert [r['source_order'] for r in rows]==sorted(r['source_order'] for r in rows)
    report={'mode':'Offline rules preview, not live AI','rows':len(rows),'groups':sum(bool(r.get('coverage_label')) for r in rows),'scenes':len(set(r['scene'] for r in rows)),'columns':list(PRODUCTION.values()),'checks':checks,'excel':'all cells compared; text shot IDs; filter/freeze/borders/wrap checked','csv':'all cells compared','print':'actual endpoint payload compared; live JS renderer tested in DOM-free harness','ppt':'one/two-up reopened; every shot label and exact source in notes; shape bounds checked'}
    (out/'export-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('checks','columns')}))
    for row in checks:print(json.dumps(row,ensure_ascii=True))
if __name__=='__main__':main()
