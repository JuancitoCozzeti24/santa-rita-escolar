import os
os.environ['CLASSROOM_BRIDGE_SECRET'] = 'synthetic-test-secret-at-least-24-chars'
import asyncio
import json
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from private_routing import PrivatePathGate
from bridge_diagnostics import compatibility, CAPABILITIES, BUILD

SECRET = os.environ['CLASSROOM_BRIDGE_SECRET']
PREFIX = '/private-test-only'

async def echo(request):
    return JSONResponse({'ok': True, 'path': request.url.path})

app = PrivatePathGate(Starlette(routes=[Route('/mcp', echo), Route('/bridge/v1/status', echo)]), PREFIX, SECRET)

def test_bridge_secret_is_required_and_mcp_remains_private():
    with TestClient(app) as c:
        for headers in [{}, {'X-SieRoom-Bridge-Secret':'wrong'}]:
            r=c.get('/bridge/v1/status',headers=headers)
            assert r.status_code==401 and r.json()['error']=='bridge_unauthorized'
        h={'X-SieRoom-Bridge-Secret':SECRET}
        assert c.get('/bridge/v1/status',headers=h).json()['path']=='/bridge/v1/status'
        for path in ['/mcp','/bridge/v1evil/mcp','/bridge/v1/../mcp','/profe-johnny/v1/status']:
            assert c.get(path,headers=h).status_code==404
        assert c.get(PREFIX+'/mcp').json()['path']=='/mcp'
        assert c.get(PREFIX+'-wrong/mcp').status_code==404

def test_extension_cors_does_not_authorize_requests_or_websites():
    with TestClient(app) as c:
        origin='chrome-extension://'+'a'*32
        preflight={'Origin':origin,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'x-sieroom-bridge-secret,x-sieroom-bridge-build'}
        r=c.options('/bridge/v1/status',headers=preflight)
        assert r.status_code==200 and r.headers['access-control-allow-origin']==origin
        r=c.get('/bridge/v1/status',headers={'Origin':origin})
        assert r.status_code==401 and r.headers['access-control-allow-origin']==origin
        r=c.options('/bridge/v1/status',headers={**preflight,'Origin':'https://untrusted.example'})
        assert r.status_code==400 and 'access-control-allow-origin' not in r.headers
        assert c.options('/mcp',headers=preflight).status_code==404

def test_compatibility_fails_closed_on_missing_capabilities_and_versions():
    headers={'x-sieroom-bridge-version':'0.8.7','x-sieroom-bridge-build':BUILD,'x-sieroom-bridge-capabilities':','.join(CAPABILITIES)}
    assert compatibility(headers)['compatible']
    for key,value in [('x-sieroom-bridge-version','0.0.0'),('x-sieroom-bridge-build','unknown'),('x-sieroom-bridge-capabilities','read_private_comments')]:
        assert not compatibility({**headers,key:value})['compatible']


def test_real_application_routes_and_read_negotiation(monkeypatch):
    # Application imports install guards; all jobs below live only in this test process.
    import bridge_policy_hotfix
    import private_entry
    import server_core
    from bridge import ClassroomBridgeQueue
    monkeypatch.setattr(server_core, 'bridge_queue', ClassroomBridgeQueue())
    q=server_core.bridge_queue
    assert getattr(ClassroomBridgeQueue,'_sieroom_triple_contract_r62',False)
    monkeypatch.setattr(private_entry.mcp, "_session_manager", None)
    with TestClient(private_entry._private_app_factory()) as c:
        h={'X-SieRoom-Bridge-Secret':SECRET,'X-SieRoom-Bridge-Version':'0.8.7','X-SieRoom-Bridge-Build':BUILD,'X-SieRoom-Bridge-Capabilities':','.join(CAPABILITIES)}
        assert c.get('/bridge/v1/status',headers=h).json()['queue']['work_remaining']==0
        assert c.get('/bridge/v1/compatibility',headers=h).json()['triple_contract']
        assert c.get('/bridge/v1/compatibility',headers={**h,'X-SieRoom-Bridge-Version':'0'}).status_code==409
        before=q.stats()
        c.get('/bridge/v1/compatibility',headers=h)
        assert q.stats()==before
        job=q.enqueue(course_id='c',course_work_id='w',submission_id='s',submission_url='https://classroom.google.com/c/c/a/w/submissions/by-status/and-sort-last-name/all/student/s',operation='read_private_comments')
        assert c.get('/bridge/v1/next',headers={**h,'X-SieRoom-Bridge-Version':'0'}).json()['job'] is None
        assert job.status=='queued'
        assert c.get('/bridge/v1/next',headers=h).json()['job']['id']==job.id
        # Routes exist and authenticate before looking up a job; no real job is completed.
        for path in ['/bridge/v1/jobs/nonexistent/complete','/bridge/v1/jobs/nonexistent/fail','/bridge/v1/delete/jobs/nonexistent/complete']:
            assert c.post(path,json={}).status_code==401
        assert c.post('/bridge/v1/jobs/nonexistent/complete',headers=h,json={}).status_code==404
        assert c.get('/mcp',headers=h).status_code==404
        # Invalid read payload cannot confirm an unverified account/target.
        r=c.post(f'/bridge/v1/jobs/{job.id}/complete',headers=h,json={'ok':True,'comments':[],'count':0,'teacher_account_verified':False})
        assert r.status_code==409
        with __import__('pytest').raises(ValueError,match='comentario privado'):
            q.enqueue(course_id='c',course_work_id='w',submission_id='s',submission_url='https://classroom.google.com/c/c',grade=15,comment='')


def test_scoped_read_and_grade_return_contract_with_synthetic_jobs(monkeypatch):
    import private_entry
    import server_core
    from bridge import ClassroomBridgeQueue
    q=ClassroomBridgeQueue()
    monkeypatch.setattr(server_core,'bridge_queue',q)
    class NoAcademicWrites:
        def __getattr__(self,name):
            raise AssertionError('No Classroom API calls allowed in this test: '+name)
    monkeypatch.setattr(server_core,'classroom',NoAcademicWrites())
    url='https://classroom.google.com/c/c/a/w/submissions/by-status/and-sort-last-name/all/student/s'
    read_result={'ok':True,'operation':'read_private_comments','count':1,
        'comments':[{'text':'Comentario sintético existente','markers':[], 'structuredFeedback':False,'timestamp':None,'domOrder':0}],
        'private_section_verified':True,'bounded_private_region_verified':True,
        'student_scope_verified':True,'teacher_account_verified':True,
        'scope_evidence':'private_label_and_composer','comment_order':'document_order',
        'method':'dom-v0.8.7-read-hf4','content_build':'0.8.7-HF5-COMMENT-ACK','current_student_id':'s','url':url}
    h={'X-SieRoom-Bridge-Secret':SECRET,'X-SieRoom-Bridge-Version':'0.8.7','X-SieRoom-Bridge-Build':BUILD,'X-SieRoom-Bridge-Capabilities':','.join(CAPABILITIES)}
    monkeypatch.setattr(private_entry.mcp, "_session_manager", None)
    with TestClient(private_entry._private_app_factory()) as c:
        read=q.enqueue(course_id='c',course_work_id='w',submission_id='s',submission_url=url,operation='read_private_comments')
        c.get('/bridge/v1/next',headers=h)
        assert c.post(f'/bridge/v1/jobs/{read.id}/complete',headers=h,json=read_result).json()['job']['status']=='completed'
        post=q.enqueue(course_id='c',course_work_id='w',submission_id='s',submission_url=url,comment='Comentario sintético',grade=15)
        assert post.return_after_comment is True
        guard=c.get('/bridge/v1/next',headers=h).json()['job']
        c.post(f'/bridge/v1/jobs/{guard["id"]}/complete',headers=h,json={**read_result,'comments':[],'count':0})
        assert c.get('/bridge/v1/next',headers=h).json()['job']['id']==post.id
        # Synthetic local confirmation only: no browser or external academic operation.
        result={'ok':True,'method':'dom-v0.8.7','teacher_account_verified':True,'url':url,
                'browser_followup_done':True,'comment':{'ok':True},'content_build':'0.8.7-HF5-COMMENT-ACK',
                'target_student_id':'s','current_student_id':'s','browser_grade_applied':True,'browser_grade':15,'browser_returned':True}
        assert c.post(f'/bridge/v1/jobs/{post.id}/complete',headers=h,json=result).json()['job']['status']=='completed'


def test_diagnostics_never_blocks_the_mcp_event_loop():
    import private_entry
    tool = private_entry.mcp._tool_manager.get_tool("bridge_connection_diagnostics")
    assert tool.is_async is True
