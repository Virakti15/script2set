"""Script2Set Flask API, local UI and durable private workspace."""
import hmac
import logging
import os
import secrets
import time
from threading import Lock
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, jsonify, render_template, request, send_file, session
from itsdangerous import URLSafeSerializer, URLSafeTimedSerializer, BadSignature
from werkzeug.exceptions import HTTPException
from dotenv import load_dotenv
from services.schema import UserError, validate_plan, fingerprint, PRODUCTION, INTERNAL, METADATA, normalize, IDENTITY_FIELDS, TRACE_FIELDS, ordered, production_view, shot_interval
from services.screenplay import analyze
from services.planning import generate_plan, generate_breakdown
from services.importing import import_excel
from services.exporting import csv_export, excel_export, ppt_export
from services.providers import provider_name
from services.accuracy import audit
from services.storage import Store
from services.storyboard import image_config, continuity_bible, context, digest, generate_image, decode_image, image_response, approved_images, clean_continuity

load_dotenv(Path(__file__).with_name('.env'))

def create_app(test_config=None):
    app=Flask(__name__)
    app.json.sort_keys=False
    production=bool(os.getenv('VERCEL')) or os.getenv('APP_ENV')=='production'
    app.config.update(SECRET_KEY=os.getenv('SECRET_KEY') or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=32_000_000,SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=production,
        PRODUCTION=production,DATA_DIR=os.getenv('DATA_DIR',str(Path(__file__).parent/'data')))
    if test_config: app.config.update(test_config)
    signer=URLSafeSerializer(app.config['SECRET_KEY'],salt='shot-plan-approval-v1')
    login_signer=URLSafeTimedSerializer(app.config['SECRET_KEY'],salt='workspace-login-v1')
    store=Store(app.config['DATA_DIR'])
    app.extensions['store']=store
    login_attempts=[]
    login_lock=Lock()
    origins={v.strip().rstrip('/') for v in os.getenv('FRONTEND_ORIGINS','').split(',') if v.strip()}
    invalid_origins=any(urlparse(v).scheme not in ('https',) if production else urlparse(v).scheme not in ('http','https') for v in origins)
    invalid_origins=invalid_origins or any(not urlparse(v).netloc or urlparse(v).path or urlparse(v).query or urlparse(v).fragment or urlparse(v).username for v in origins)

    def authenticated():
        token=request.headers.get('Authorization','').removeprefix('Bearer ')
        if token:
            try: return login_signer.loads(token,max_age=43200)=='workspace'
            except BadSignature: return False
        return bool(session.get('authenticated'))

    def origin_allowed():
        origin=request.headers.get('Origin')
        return not origin or origin==request.host_url.rstrip('/') or origin in origins

    def body():
        value=request.get_json(silent=True)
        if not isinstance(value,dict): raise UserError('Send a valid JSON object.')
        return value

    def approved(data):
        plan=validate_plan(data.get('plan'))
        try: claim=signer.loads(data.get('approval',''))
        except (BadSignature,TypeError):
            raise UserError('Review and approve the shot plan before continuing.',409) from None
        digest=fingerprint(plan)
        if claim!=digest:
            raise UserError('Shot plan changed. Regenerate the production breakdown to apply updates.',409)
        return plan,digest

    def current_rows(data):
        plan,digest=approved(data)
        if data.get('breakdown_hash')!=digest:
            raise UserError('Shot plan changed. Regenerate the production breakdown to apply updates.',409)
        rows=data.get('breakdown')
        if not isinstance(rows,list) or not rows or len(rows)!=len(plan):
            raise UserError('Generate a complete production breakdown before exporting.',409)
        rows=[normalize(r) for r in rows]
        if len({r['id'] for r in rows})!=len(rows) or set(r['id'] for r in rows)!=set(r['id'] for r in plan):
            raise UserError('The breakdown does not match the approved plan. Regenerate it.',409)
        by_id={r['id']:r for r in plan}
        for row in rows:
            original=by_id[row['id']]
            for key in IDENTITY_FIELDS+TRACE_FIELDS:
                if key in original:row[key]=original[key]
            first,last,label=shot_interval(row['number'])
            row['representative_shot']=first
            if last:row['coverage_count']=int(last)-int(first)+1;row['coverage_label']=label or 'Coverage'
        validate_plan(rows)
        return ordered(rows)

    @app.before_request
    def protect():
        if request.path.startswith('/static/') or request.path=='/health': return
        if production and (not os.getenv('SECRET_KEY') or not os.getenv('APP_ACCESS_PASSWORD') or not os.getenv('DATA_DIR')):
            raise UserError('Production setup is incomplete. Configure SECRET_KEY, APP_ACCESS_PASSWORD and persistent DATA_DIR on the server.',503)
        if invalid_origins: raise UserError('FRONTEND_ORIGINS must contain exact allowed origins (HTTPS in production), never wildcards.',503)
        if request.path.startswith('/api/') and not origin_allowed():
            raise UserError('This frontend origin is not allowed by the backend configuration.',403)
        if request.method=='OPTIONS': return '',204
        if request.method=='POST':
            if not origin_allowed():
                raise UserError('This request came from a different site. Refresh Script2Set and try again.',403)
            if request.headers.get('X-Script2Set')!='1':
                raise UserError('Open Script2Set to perform this action.',403)
        if request.path.startswith('/api/') and request.path not in ('/api/login','/api/config'):
            if os.getenv('APP_ACCESS_PASSWORD') and not authenticated():
                raise UserError('Sign in with the workspace password to continue.',401)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['X-Frame-Options']='DENY'
        origin=request.headers.get('Origin')
        if origin in origins and not invalid_origins:
            response.headers['Access-Control-Allow-Origin']=origin
            response.headers['Vary']='Origin'
            response.headers['Access-Control-Allow-Methods']='GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers']='Content-Type, X-Script2Set, Authorization'
            response.headers['Access-Control-Expose-Headers']='Content-Disposition'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.path.startswith('/api/') or request.path=='/print': response.headers['Cache-Control']='no-store'
        return response

    @app.errorhandler(UserError)
    def user_error(error): return jsonify(error=str(error)),error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        message='This project exceeds the 32 MB request limit. Save images on the server or split the project.' if error.code==413 else 'The requested page or operation is not available.'
        return jsonify(error=message),error.code

    @app.errorhandler(Exception)
    def unexpected(error):
        # Do not log request bodies, provider response text, keys, or exception messages.
        app.logger.error('Unhandled %s in %s',type(error).__name__,request.path)
        return jsonify(error='Something went wrong. Your saved project is safe. Retry the action.'),500

    @app.get('/')
    def index(): return render_template('index.html')

    @app.get('/print')
    def print_view(): return render_template('print.html')

    @app.get('/health')
    def health():
        return jsonify(status='ok',ai_provider=provider_name(),environment='production' if production else 'local')

    @app.get('/api/config')
    def config():
        return jsonify(provider=provider_name(),production=production,
            image_enabled=image_config()['enabled'],image_provider=image_config()['provider'],
            generation_mode='offline_rules' if provider_name()=='demo' else 'live_ai',
            login_required=bool(os.getenv('APP_ACCESS_PASSWORD')) and not authenticated(),
            columns=PRODUCTION,metadata_fields=METADATA)

    @app.post('/api/login')
    def login():
        # Global bounded throttle for a small shared workspace; no untrusted proxy headers.
        with login_lock:
            now=time.monotonic()
            login_attempts[:]=[t for t in login_attempts if now-t<60]
            if len(login_attempts)>=20: raise UserError('Too many sign-in attempts. Wait one minute and try again.',429)
            login_attempts.append(now)
        supplied=str(body().get('password',''))
        expected=os.getenv('APP_ACCESS_PASSWORD','')
        if not expected or not hmac.compare_digest(supplied.encode(),expected.encode()):
            raise UserError('Incorrect workspace password.',401)
        session.clear(); session['authenticated']=True
        return jsonify(ok=True,token=login_signer.dumps('workspace'))

    @app.post('/api/analyze')
    def analyze_script(): return jsonify(analyze(body().get('script')))

    @app.post('/api/migrate')
    def migrate():
        data=body();project=data.get('project')
        if not isinstance(project,dict) or project.get('version') not in (1,2,3):raise UserError('This is not a supported Script2Set project.')
        for key in ('plan','breakdown'):
            if not isinstance(project.get(key),list) or len(project[key])>300:raise UserError('Project shot rows are invalid.')
            project[key]=[normalize({**r,**production_view(r)}) if key=='breakdown' else normalize(r) for r in project[key]]
        if project['version']<3:
            old_rows={r['id']:r for r in project['breakdown']}
            for row in project['plan']:
                if row['id'] in old_rows:
                    row['existing']={**row.get('existing',{}),**{k:v for k,v in old_rows[row['id']].items() if k in (set(PRODUCTION)|set(INTERNAL)) and k not in IDENTITY_FIELDS and v}}
            project.update(version=3,approval='',planHash='',breakdownHash='',stale=bool(project['breakdown']))
        project.setdefault('metadata',{})
        project['breakdown']=[{**r,**production_view(r)} for r in project['breakdown']]
        return jsonify(project=project)

    @app.post('/api/plan')
    def plan():
        data=body()
        offset=data.get('offset',0)
        if type(offset)!=int or offset<0 or offset>300: raise UserError('Invalid shot offset.')
        return jsonify(shots=generate_plan(data.get('scene'),data.get('characters'),offset,data.get('previous')),generation_mode='offline_rules' if provider_name()=='demo' else 'live_ai',provider=provider_name())

    @app.post('/api/import')
    def import_sheet():
        upload=request.files.get('file')
        if not upload or not upload.filename.lower().endswith('.xlsx'):
            raise UserError('Upload a modern Excel workbook (.xlsx). Save older .xls files as .xlsx first.')
        return jsonify(import_excel(upload.read()))

    @app.post('/api/approve')
    def approve():
        data=body()
        if data.get('reviewed') is not True: raise UserError('Review the shot plan and explicitly approve it first.',409)
        plan=validate_plan(data.get('plan')); digest=fingerprint(plan)
        return jsonify(approval=signer.dumps(digest),plan_hash=digest)

    @app.post('/api/breakdown')
    def breakdown():
        data=body(); plan,digest=approved(data)
        return jsonify(shots=generate_breakdown(plan,data.get('scene'),data.get('prior')),plan_hash=digest,generation_mode='offline_rules' if provider_name()=='demo' else 'live_ai',provider=provider_name())

    def image_inputs(data):
        rows=current_rows(data)
        row=next((r for r in rows if r['id']==data.get('shot_id')),None)
        if not row: raise UserError('Choose a shot in the current production breakdown.')
        ctx=context(rows,row,data.get('visual_context',''),data.get('continuity'))
        return rows,row,ctx

    @app.post('/api/storyboard/context')
    def storyboard_context():
        data=body(); rows=current_rows(data)
        return jsonify(continuity=continuity_bible(rows,data.get('continuity')))

    @app.post('/api/storyboard/generate')
    def storyboard_generate():
        data=body(); rows,row,ctx=image_inputs(data)
        candidates=approved_images(store,rows,data.get('images',{}),data.get('visual_context',''),data.get('continuity'))
        related=[r for r in rows if r['id']!=row['id'] and (r['scene']==row['scene'] or r.get('shot_location')==row.get('shot_location') or set(context(rows,r)['characters']) & set(ctx['characters']))]
        refs=[candidates[r['id']] for r in related if r['id'] in candidates][:3]
        raw=generate_image(ctx,refs)
        info=store.put_image(raw,{'shot_id':row['id'],'digest':digest(ctx),'source':'generated','provider':image_config()['provider'],'reference_count':len(refs),'representative_shot':row.get('representative_shot'),'number':row['number']})
        return jsonify(image=image_response(info,raw))

    @app.post('/api/storyboard/upload')
    def storyboard_upload():
        data=body(); rows,row,ctx=image_inputs(data)
        raw=decode_image(data.get('image'))
        info=store.put_image(raw,{'shot_id':row['id'],'digest':digest(ctx),'source':'uploaded','reference_count':0,'representative_shot':row.get('representative_shot'),'number':row['number']})
        return jsonify(image=image_response(info,raw))

    @app.post('/api/storyboard/approve')
    def storyboard_approve():
        data=body(); rows,row,ctx=image_inputs(data)
        info,raw=store.image(data.get('asset_id'))
        if info['shot_id']!=row['id'] or info['digest']!=digest(ctx):
            raise UserError('This frame is outdated. Regenerate or replace it using the current shot and continuity details.',409)
        if type(data.get('approved')) is not bool: raise UserError('Explicitly approve or unapprove this frame.')
        info,raw=store.approve(info['asset_id'],data['approved'])
        return jsonify(image=image_response(info,raw))

    @app.route('/api/projects',methods=['GET','POST'])
    def projects():
        if request.method=='GET': return jsonify(projects=store.projects())
        project=body().get('project')
        if not isinstance(project,dict) or project.get('version')!=3: raise UserError('Save a current Script2Set project.')
        for key in ('plan','breakdown'):
            if not isinstance(project.get(key),list) or len(project[key])>300: raise UserError('Invalid project rows.')
        clean_continuity(project.get('continuity'))
        images=project.get('images',{})
        if not isinstance(images,dict) or len(images)>300: raise UserError('Invalid project storyboard images.')
        for shot_id,image in images.items():
            if not isinstance(image,dict): raise UserError('Invalid project storyboard image.')
            if image.get('asset_id'):
                info,_=store.image(image['asset_id'])
                if info['shot_id']!=shot_id: raise UserError('Storyboard image belongs to a different shot.')
                image.pop('data',None)
        return jsonify(id=store.save_project(project))

    @app.get('/api/projects/<project_id>')
    def restore_project(project_id):
        project=store.project(project_id)
        for shot_id,image in project.get('images',{}).items():
            if image.get('asset_id'):
                try:
                    info,raw=store.image(image['asset_id'])
                    image['data']=image_response(info,raw)['data']
                    image['approved']=bool(image.get('approved') and info['approved'])
                except UserError:
                    image.update(approved=False,stale=True,status='error',error='Stored image is missing. Upload or generate it again.')
        return jsonify(project=project)

    @app.post('/api/export/<kind>')
    def export(kind):
        data=body(); rows=current_rows(data)
        validation=audit(rows,data.get('plan'),data.get('source_script'))
        if kind=='xlsx' and not validation['ok']:
            return jsonify(error='Resolve the production accuracy errors before final Excel export.',validation=validation),422
        formats={'xlsx':(excel_export,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                 'csv':(csv_export,'text/csv; charset=utf-8')}
        if kind=='pptx':
            images=approved_images(store,rows,data.get('images',{}),data.get('visual_context',''),data.get('continuity'),strict=True)
            stream=ppt_export(rows,data.get('per_slide',1),str(data.get('title','Script2Set')),images=images,metadata=data.get('metadata'))
            mime='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        elif kind in formats:
            func,mime=formats[kind]
            metadata={**(data.get('metadata') or {}),'client':(data.get('metadata') or {}).get('client') or data.get('title','')}
            if kind=='xlsx':
                images=approved_images(store,rows,data.get('images',{}),data.get('visual_context',''),data.get('continuity'),strict=True)
                stream=func(rows,metadata,images=images,validation=validation)
            else:stream=func(rows,metadata)
        else: raise UserError('Choose Excel, CSV, or Storyboard PPT.')
        if stream.getbuffer().nbytes>64_000_000:
            raise UserError('This export exceeds 64 MB. Split the project into smaller sequences.',413)
        return send_file(stream,mimetype=mime,as_attachment=True,download_name='script2set-breakdown.'+kind)

    @app.post('/api/validate')
    def validate_production():
        data=body();rows=current_rows(data)
        return jsonify(audit(rows,data.get('plan'),data.get('source_script')))

    @app.post('/api/print')
    def print_data():
        data=body()
        return jsonify(shots=[{**r,**production_view(r)} for r in current_rows(data)],columns=PRODUCTION,metadata=data.get('metadata') or {},metadata_fields=METADATA)

    return app

app=create_app()
if __name__=='__main__':
    from waitress import serve
    host=os.getenv('HOST','127.0.0.1');port=int(os.getenv('PORT','5000'))
    print(f'Script2Set available at http://{host}:{port}',flush=True)
    serve(app,host=host,port=port,threads=6)
