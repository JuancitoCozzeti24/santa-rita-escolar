from __future__ import annotations
import base64, io, os, secrets
from datetime import datetime
from typing import Any
import qrcode
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

SESSIONS: dict[str, dict[str, Any]] = {}

def install(mcp, sieweb, settings):
    def admin_ok(request: Request) -> bool:
        expected = str(os.getenv('ATTENDANCE_ADMIN_SECRET') or settings.classroom_bridge_secret or '')
        provided = str(request.query_params.get('key') or request.headers.get('x-attendance-admin-secret') or '')
        return bool(expected and provided and secrets.compare_digest(expected, provided))

    def students(section):
        data=sieweb.resolve_student_recipients_by_sections([section])
        return [{'code':str(r.get('USUCOD') or ''),'name':str(r.get('USUNOM') or '')} for r in data.get('resolved',[])]

    def family(section, code):
        data=sieweb.resolve_family_recipients_by_sections([section])
        for r in data.get('resolved',[]):
            if str(r.get('student_code') or '') == code:
                return {'code':str(r.get('family_code') or ''),'name':str(r.get('family_name') or '')}
        return None

    @mcp.custom_route('/asesoria', methods=['GET'])
    async def admin(request: Request):
        if not admin_ok(request): return HTMLResponse('<h2>Acceso no autorizado</h2>',401)
        key=request.query_params.get('key','')
        page="""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>SieRoom Asesoría</title><style>body{font-family:system-ui;max-width:850px;margin:30px auto;padding:16px}input,select,button{font-size:18px;padding:10px;margin:6px}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}</style><h1>Asistencia a asesoría</h1><p>Crea una sesión y proyecta el QR.</p><select id=s><option>2A</option><option>2B</option><option>5A</option><option>5B</option></select><input id=e value='4:25 p. m.'><button onclick='createSession()'>Nueva asesoría</button><div id=out></div><script>const key=KEY;async function createSession(){let r=await fetch('/asesoria/api/session?key='+encodeURIComponent(key),{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({section:s.value,end_time:e.value})});let j=await r.json();if(!j.ok){out.innerText=JSON.stringify(j);return}out.innerHTML='<h2>'+j.section+' · '+j.date+'</h2><img style="width:min(70vw,430px)" src="'+j.qr_data_url+'"><p><b>Enlace:</b> '+j.checkin_url+'</p><h3>Registrados</h3><div id=list></div>';poll(j.token)}async function poll(t){let r=await fetch('/asesoria/api/session/'+t+'/status?key='+encodeURIComponent(key));let j=await r.json();list.innerHTML='<table><tr><th>Alumno</th><th>Hora</th><th>Aviso</th></tr>'+j.attendees.map(x=>'<tr><td>'+x.name+'</td><td>'+x.time+'</td><td>'+(x.notified?'✓ Enviado':'⚠ '+(x.error||'Pendiente'))+'</td></tr>').join('')+'</table>';setTimeout(()=>poll(t),3000)}</script>""".replace('KEY',repr(key))
        return HTMLResponse(page)

    @mcp.custom_route('/asesoria/api/session', methods=['POST'])
    async def create(request: Request):
        if not admin_ok(request): return JSONResponse({'ok':False,'error':'unauthorized'},401)
        try: body=await request.json()
        except Exception: body={}
        section=str(body.get('section') or '').upper().replace(' ','')
        if section not in {'2A','2B','5A','5B'}: return JSONResponse({'ok':False,'error':'section_invalid'},400)
        token=secrets.token_urlsafe(18); now=datetime.now()
        SESSIONS[token]={'section':section,'date':now.strftime('%d/%m/%Y'),'end_time':str(body.get('end_time') or '4:25 p. m.'),'attendees':{}}
        url=f'{settings.public_base_url}/asesoria/r/{token}'; qr=qrcode.make(url); buf=io.BytesIO(); qr.save(buf,format='PNG')
        return JSONResponse({'ok':True,'token':token,'section':section,'date':SESSIONS[token]['date'],'checkin_url':url,'qr_data_url':'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()})

    @mcp.custom_route('/asesoria/r/{token}', methods=['GET'])
    async def form(request: Request):
        token=str(request.path_params.get('token') or ''); ses=SESSIONS.get(token)
        if not ses:return HTMLResponse('<h2>Esta sesión ya no está disponible.</h2>',404)
        try: roster=students(ses['section'])
        except Exception as ex:return HTMLResponse('<h2>No se pudo cargar la lista.</h2><p>'+str(ex)+'</p>',500)
        opts=''.join('<option value="'+x['code']+'">'+x['name']+'</option>' for x in roster)
        page="""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{font-family:system-ui;max-width:600px;margin:40px auto;padding:20px;text-align:center}select,button{width:100%;font-size:18px;padding:14px;margin:10px 0}</style><h1>Asesoría de Matemática</h1><p>SECTION · DATE</p><select id=student><option value=''>— Selecciona tu nombre —</option>OPTIONS</select><button onclick='go()'>REGISTRAR MI ASISTENCIA</button><div id=msg></div><script>async function go(){if(!student.value)return;let r=await fetch('/asesoria/api/checkin/TOKEN',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({student_code:student.value})});let j=await r.json();msg.innerHTML=j.ok?'<h2>✓ Asistencia registrada</h2><p>Tu familia ha sido notificada.</p>':'<h2>'+((j.attendance_saved)?'✓ Asistencia registrada':'No se pudo registrar')+'</h2><p>'+(j.error||'')+'</p>'}</script>"""
        return HTMLResponse(page.replace('SECTION',ses['section']).replace('DATE',ses['date']).replace('OPTIONS',opts).replace('TOKEN',token))

    @mcp.custom_route('/asesoria/api/checkin/{token}', methods=['POST'])
    async def checkin(request: Request):
        token=str(request.path_params.get('token') or ''); ses=SESSIONS.get(token)
        if not ses:return JSONResponse({'ok':False,'error':'Sesión no disponible.'},404)
        try: body=await request.json()
        except Exception: body={}
        code=str(body.get('student_code') or '').strip()
        if code in ses['attendees']:return JSONResponse({'ok':True,'duplicate':True})
        student=next((x for x in students(ses['section']) if x['code']==code),None)
        if not student:return JSONResponse({'ok':False,'error':'Alumno no válido.'},400)
        now=datetime.now(); rec={'name':student['name'],'time':now.strftime('%H:%M:%S'),'notified':False,'error':''}; ses['attendees'][code]=rec
        fam=family(ses['section'],code)
        if not fam or not fam['code']:
            rec['error']='No se encontró la familia en SIEweb.';return JSONResponse({'ok':False,'attendance_saved':True,'error':rec['error']},422)
        subject='Asistencia registrada – Taller de asesoría'
        text=f"Estimados padres de familia:\n\nLes informo que {student['name']} acaba de registrar correctamente su asistencia al taller de asesoría de Matemática.\n\nSu asistencia ha quedado registrada satisfactoriamente. El taller culminará hoy a las {ses['end_time']}.\n\nSi tienen alguna duda o consulta, estaré disponible para atenderlos.\n\nSaludos cordiales."
        try:
            sieweb.send_message(recipient_codes=[fam['code']],subject=subject,plain_text=text);rec['notified']=True
            return JSONResponse({'ok':True,'student':student['name'],'notified':True})
        except Exception as ex:
            rec['error']=str(ex);return JSONResponse({'ok':False,'attendance_saved':True,'error':'Asistencia registrada, pero falló el aviso a la familia.'},502)

    @mcp.custom_route('/asesoria/api/session/{token}/status', methods=['GET'])
    async def status(request: Request):
        if not admin_ok(request):return JSONResponse({'ok':False,'error':'unauthorized'},401)
        ses=SESSIONS.get(str(request.path_params.get('token') or ''))
        if not ses:return JSONResponse({'ok':False,'error':'not_found'},404)
        return JSONResponse({'ok':True,'attendees':list(ses['attendees'].values())})
