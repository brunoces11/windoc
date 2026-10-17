"""Regression tests: private temporary state, no desktop mutations."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import WORKSPACE1 as ws
import AGENT_SESSION_HOOK as hook

SID = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'

def pane(agent=None, sid=None, state='program'):
    return {'cwd': '/tmp', 'command': [agent or '/bin/bash'], 'agent': agent,
            'session_id': sid, 'state': state}

def window(identity='a'*24, agent=None, sid=None, state='program'):
    return {'restore_id': identity, 'class': 'kitty', 'kind': 'kitty',
            'tabs': [{'panes': [pane(agent, sid, state)]}], 'agent_sessions': [], 'warnings': []}

class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in [('STATE_DIR', self.root), ('STATE_FILE', self.root/'WORKSPACE1.json'),
                            ('CAPTURE_FILE', self.root/'LATEST_CAPTURE.json'),
                            ('RESTORE_STATUS_FILE', self.root/'RESTORE_STATUS.json')]:
            p = patch.object(ws, name, value);p.start();self.addCleanup(p.stop)

    def transcript(self, rows):
        p=self.root/'history.jsonl';p.write_text(''.join(json.dumps(r)+'\n' for r in rows));return str(p)

    def test_antigravity_real_schema(self):
        self.assertIs(hook.transcript_has_user_message(self.transcript([{'type':'USER_INPUT','content':'hello'}])), True)

    def test_codex_nested_schema(self):
        self.assertIs(hook.transcript_has_user_message(self.transcript([{'type':'response_item','payload':{'type':'message','role':'user'}}])), True)

    def test_claude_nested_schema(self):
        self.assertIs(hook.transcript_has_user_message(self.transcript([{'message':{'role':'user'}}])), True)

    def test_unknown_is_not_empty(self):
        self.assertIsNone(hook.transcript_has_user_message(self.transcript([{'new_schema':'anything'}])))

    def test_empty_transcript(self):
        self.assertIs(hook.transcript_has_user_message(self.transcript([])), False)

    def test_revalidate_old_empty(self):
        record={'agent':'antigravity','session_id':SID,'state':'empty','has_user_turn':False,
                'transcript_path':self.transcript([{'type':'USER_INPUT'}])}
        with patch.object(ws,'pane_registry_record',return_value=record), patch.object(ws,'process_start_ticks',return_value='1'):
            sid,method,state=ws.session_id_for('antigravity',{'pid':2,'cmdline':['agy']},kitty_pid=1,kitty_window_id=1)
        self.assertEqual((sid,state),(SID,'active'))

    def test_hook_overrides_old_resume_arguments(self):
        record={'agent':'codex','session_id':OTHER,'state':'active','has_user_turn':True}
        with patch.object(ws,'pane_registry_record',return_value=record), patch.object(ws,'process_start_ticks',return_value='1'):
            sid,_,_=ws.session_id_for('codex',{'pid':2,'cmdline':['codex','resume',SID]},kitty_pid=1,kitty_window_id=1)
        self.assertEqual(sid,OTHER)

    def record(self,state='unresolved',sid=None):
        return {'agent':'codex','session_id':sid,'state':state,'id_method':'test',
                'kitty_tab_index':0,'kitty_pane_index':0,'kitty_tab_title':'x','kitty_window_id':1,'cwd':'/tmp'}

    def test_unknown_direct_agent_becomes_shell(self):
        raw='new_tab\nlaunch \'kitty-unserialize-data={"id":1}\' --cwd=/tmp codex resume '+SID+'\n'
        result,records=ws.patch_native_session(raw,{1:self.record()})
        self.assertNotIn('codex',result);self.assertNotIn(SID,result);self.assertEqual(len(records),1)

    def test_known_agent_exact_resume(self):
        raw='new_tab\nlaunch \'kitty-unserialize-data={"id":1}\' --cwd=/tmp codex\n'
        result,_=ws.patch_native_session(raw,{1:self.record('active',SID)})
        self.assertIn('codex resume '+SID,result)
        self.assertNotIn('--cwd=/tmp codex',result)

    def test_partial_loads_and_generates_command(self):
        w=window();w['session_file']=ws.stored_session('new_tab\nlaunch\n')
        state={'schema':2,'workspace':ws.WORKSPACE_ID,'boot_id':'old','valid':True,'complete':False,
               'updated_at':1,'windows':[w],'warnings':['missing ID']}
        ws.promote_state(state)
        self.assertFalse(ws.load_state()['complete']);self.assertIsNotNone(ws.restore_plan(ws.load_state())[0]['command'])

    def test_corruption_is_local_to_window(self):
        a,b=window(),window('b'*24)
        a['session_file']=ws.stored_session('new_tab\nlaunch\n')
        b['session_file']=ws.stored_session('new_tab\nlaunch --cwd=/tmp\n')
        (self.root/a['session_file']).write_text('corrupt')
        plan=ws.restore_plan({'windows':[a,b]})
        self.assertIsNone(plan[0]['command']);self.assertIsNotNone(plan[1]['command'])

    def test_unreadable_session_does_not_block_app(self):
        a=window();a['session_file']=ws.stored_session('new_tab\nlaunch\n')
        b={'restore_id':'b'*24,'kind':'application','restore_command':['amberol']}
        with patch.object(Path,'read_bytes',side_effect=PermissionError('unreadable')):
            plan=ws.restore_plan({'windows':[a,b]})
        self.assertIsNone(plan[0]['command'])
        self.assertEqual(plan[1]['command'],['amberol'])

    def test_amberol_command(self):
        with patch.object(ws.shutil,'which',return_value='/usr/bin/amberol'):
            self.assertEqual(ws.application_command('io.bassi.Amberol'),['amberol'])

    def test_path_traversal_rejected(self):
        w=window();w['session_file']='../elsewhere.session'
        self.assertIsNone(ws.restore_plan({'windows':[w]})[0]['command'])

    def test_missing_empty_tab_detected(self):
        a=window();b=copy.deepcopy(a);a['tabs'].append({'panes':[pane()]})
        self.assertFalse(ws.window_matches(a,b))

    def test_swapped_sessions_between_windows_detected(self):
        a,b=window('a'*24,'codex',SID,'active'),window('b'*24,'codex',OTHER,'active')
        x,y=copy.deepcopy(a),copy.deepcopy(b)
        x['tabs'][0]['panes'][0]['session_id']=OTHER;y['tabs'][0]['panes'][0]['session_id']=SID
        self.assertFalse(ws.restore_matches({'windows':[a,b]},{'windows':[x,y]}))

    def test_unknown_expected_shell_accepted(self):
        self.assertTrue(ws.window_matches(window(agent='codex',state='unresolved'),window()))

    def test_missing_pane_detected(self):
        a=window();b=copy.deepcopy(a);a['tabs'][0]['panes'].append(pane())
        self.assertFalse(ws.window_matches(a,b))

    def test_resume_arguments_are_not_loaded_chat_confirmation(self):
        a=window(agent='codex',sid=SID,state='active');b=copy.deepcopy(a)
        b['tabs'][0]['panes'][0]['id_method']='explicit-resume-arguments'
        self.assertFalse(ws.window_matches(a,b))

    def test_corrupt_primary_uses_previous_snapshot(self):
        state={'schema':2,'workspace':ws.WORKSPACE_ID,'updated_at':1,'windows':[window()],'complete':False}
        (self.root/'PREVIOUS_WORKSPACE1.json').write_text(json.dumps(state))
        ws.STATE_FILE.write_text('{invalid')
        self.assertEqual(ws.load_state()['windows'][0]['restore_id'],'a'*24)

    def test_fallback_keeps_known_agent_resume(self):
        text=ws.shell_session([{'panes':[pane('codex',SID,'active'),pane('codex',None,'unresolved')]}])
        self.assertIn('codex resume '+SID,text)
        self.assertEqual(text.count('cmd_at_shell_startup'),1)

    def test_launch_failure_does_not_stop_next(self):
        a={'restore_id':'a'*24,'class':'first','kind':'application','restore_command':['first']}
        b={'restore_id':'b'*24,'class':'second','kind':'application','restore_command':['second']}
        calls=[]
        def dispatch(value):
            calls.append(value)
            if 'first' in value:raise RuntimeError('simulated failure')
        client={'address':'0x2','class':'second','pid':2,'workspace':{'id':ws.WORKSPACE_ID}}
        def associate(item,live,source):
            return client if item['class']=='second' and any('exec_cmd' in c and 'second' in c for c in calls) else None
        with patch.object(ws,'wait_for_hyprland'),patch.object(ws,'clients',return_value=[client]), \
             patch.object(ws,'associated_client',side_effect=associate),patch.object(ws,'dispatch',side_effect=dispatch), \
             patch.object(ws,'snapshot',return_value={'windows':[b]}):
            results=ws.restore({'windows':[a,b],'complete':True},verify_seconds=0)
        self.assertEqual(results[0]['status'],'falhou');self.assertEqual(results[1]['status'],'verificado')
        self.assertTrue(any('exec_cmd' in c and 'second' in c for c in calls))

    def test_existing_window_is_not_launched_again(self):
        a=window();a['session_file']=ws.stored_session('new_tab\nlaunch\n')
        with patch.object(ws,'wait_for_hyprland'),patch.object(ws,'clients',return_value=[]), \
             patch.object(ws,'associated_client',return_value={'address':'0x1'}),patch.object(ws,'dispatch') as dispatch, \
             patch.object(ws,'snapshot',return_value={'windows':[a]}):
            results=ws.restore({'windows':[a],'complete':True},verify_seconds=0)
        dispatch.assert_not_called();self.assertEqual(results[0]['status'],'verificado')

    def test_group_membership_compares_stable_ids(self):
        a,b=window(),window('b'*24)
        a.update(address='0x1',grouped=['0x1','0x2']);b.update(address='0x2',grouped=['0x1','0x2'])
        x,y=copy.deepcopy(a),copy.deepcopy(b)
        x.update(address='0x3',grouped=['0x3','0x4']);y.update(address='0x4',grouped=['0x3','0x4'])
        self.assertTrue(ws.restore_matches({'windows':[a,b]},{'windows':[x,y]}))
        x['grouped']=['0x3'];y['grouped']=['0x4']
        self.assertFalse(ws.restore_matches({'windows':[a,b]},{'windows':[x,y]}))

    def test_previous_snapshot_kept(self):
        a={'schema':2,'workspace':ws.WORKSPACE_ID,'windows':[window()],'complete':False,'updated_at':1}
        ws.promote_state(a)
        b=copy.deepcopy(a);b['windows'].append(window('b'*24));ws.promote_state(b)
        self.assertEqual(len(ws.load_state(self.root/'PREVIOUS_WORKSPACE1.json')['windows']),1)

if __name__=='__main__':unittest.main(verbosity=2)
