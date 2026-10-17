"""Regression tests: private temporary state, no desktop mutations."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import WORKSPACE1 as ws
import AGENT_SESSION_HOOK as hook
from INTERFACE_MONITOR import QuietPeriod, relevant_event, EventFilter
import WORKSPACE_LAYOUT as layout

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

    def test_process_cache_cannot_override_current_native_id(self):
        registry=self.root/'AGENT_IDS.json'
        registry.write_text(json.dumps({'42':{'agent':'antigravity','session_id':SID,'start_ticks':'100'}}))
        with patch.object(ws,'AGENT_IDS_FILE',registry),patch.object(ws,'pane_registry_record',return_value=None), \
             patch.object(ws,'process_start_ticks',return_value='100'), \
             patch.object(ws,'process_fd_targets',return_value=['/presence/'+OTHER+'.lock']), \
             patch.object(ws,'process_mapped_files',return_value=[]),patch.object(ws,'register_session_id'):
            sid,_,_=ws.session_id_for('antigravity',{'pid':42,'cmdline':['agy']},kitty_pid=3,kitty_window_id=1)
        self.assertEqual(sid,OTHER)

    def test_process_cache_alone_does_not_prove_active_session(self):
        registry=self.root/'AGENT_IDS.json'
        registry.write_text(json.dumps({'42':{'agent':'antigravity','session_id':SID,'start_ticks':'100'}}))
        with patch.object(ws,'AGENT_IDS_FILE',registry),patch.object(ws,'pane_registry_record',return_value=None), \
             patch.object(ws,'process_start_ticks',return_value='100'),patch.object(ws,'process_fd_targets',return_value=[]), \
             patch.object(ws,'process_mapped_files',return_value=[]):
            sid,_,state=ws.session_id_for('antigravity',{'pid':42,'cmdline':['agy']},kitty_pid=3,kitty_window_id=1)
        self.assertIsNone(sid);self.assertEqual(state,'unresolved')

    def preserved_scene(self):
        good=window(agent='codex',sid=SID,state='active')
        good.update(pid=42,pid_start_ticks='100',native_layout=True,structure_available=True,session_file='known.session')
        old={'schema':2,'workspace':1,'boot_id':'boot','updated_at':10,'complete':True,'warnings':[],'windows':[good]}
        bad=copy.deepcopy(old);bad.update(updated_at=20,complete=False,warnings=['read failure'])
        bad['windows'][0].update(structure_available=False,native_layout=False,session_file='fallback.session',
                                 tabs=[{'panes':[pane(state='unresolved')]}],warnings=['read failure'])
        return old,bad

    def test_unreadable_kitty_preserves_known_data_with_warning(self):
        old,bad=self.preserved_scene()
        ws.promote_state(old);ws.promote_state(bad)
        saved=ws.load_state();item=saved['windows'][0]
        self.assertEqual(item['tabs'][0]['panes'][0]['session_id'],SID)
        self.assertEqual(item['session_file'],'known.session')
        self.assertTrue(item['capture_stale']);self.assertFalse(saved['complete'])
        self.assertEqual(item['last_successful_capture_at'],10)
        self.assertIsNone(bad['windows'][0]['tabs'][0]['panes'][0].get('session_id'))

    def test_unreadable_different_process_or_boot_does_not_inherit_chat(self):
        old,bad=self.preserved_scene()
        for ticks,boot in [('200','boot'),('100','new-boot')]:
            candidate=copy.deepcopy(bad);candidate['boot_id']=boot
            candidate['windows'][0]['pid_start_ticks']=ticks
            result=ws.preserve_unreadable_windows(candidate,old)
            self.assertEqual(result['windows'][0]['session_file'],'fallback.session')
            self.assertNotIn('capture_stale',result['windows'][0])

    def test_successful_capture_replaces_stale_data(self):
        old,bad=self.preserved_scene()
        stale=ws.preserve_unreadable_windows(bad,old)
        fresh=copy.deepcopy(old);fresh['windows'][0]['tabs'][0]['panes'][0]['session_id']=OTHER
        result=ws.preserve_unreadable_windows(fresh,stale)
        self.assertEqual(result['windows'][0]['tabs'][0]['panes'][0]['session_id'],OTHER)
        self.assertNotIn('capture_stale',result['windows'][0])

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

    def test_quiet_period_waits_30_seconds_after_last_change(self):
        gate=QuietPeriod(30);gate.change(10)
        self.assertFalse(gate.ready(39.999));gate.change(35)
        self.assertFalse(gate.ready(64.999));self.assertTrue(gate.ready(65))

    def test_spinner_titles_do_not_restart_quiet_period(self):
        self.assertFalse(relevant_event('windowtitlev2','abc,spinner',{'0xabc'},1))
        self.assertTrue(relevant_event('closewindow','abc',{'0xabc'},1))
        self.assertFalse(relevant_event('openwindow','def,2,kitty,title',{'0xabc'},1))

    def test_repeated_active_events_from_spinner_do_not_reset_timer(self):
        events=EventFilter();events.active='0xabc'
        gate=QuietPeriod(30);gate.change(0)
        for second in range(1,31):
            if events.accept('activewindowv2','abc',{'0xabc','0xdef'},1):gate.change(second)
        self.assertTrue(gate.ready(30))
        self.assertTrue(events.accept('activewindowv2','def',{'0xabc','0xdef'},1))
        self.assertFalse(events.accept('activewindowv2','def',{'0xabc','0xdef'},1))

    def test_no_write_for_unchanged_snapshot(self):
        state={'schema':2,'workspace':ws.WORKSPACE_ID,'boot_id':'boot','updated_at':1,
               'windows':[window()],'complete':True,'warnings':[]}
        ws.promote_state(state);stamp=ws.STATE_FILE.stat().st_mtime_ns
        ws.promote_state(dict(state,updated_at=2))
        self.assertEqual(stamp,ws.STATE_FILE.stat().st_mtime_ns)
        self.assertEqual(ws.load_state()['updated_at'],1)

    def test_geometry_only_capture_reuses_native_file(self):
        w=window();w.update(pid=42,address='0x1',pid_start_ticks='100',kind='kitty',
                           native_fingerprint='known',native_layout=True,structure_available=True)
        w['session_file']=ws.stored_session('new_tab\nlaunch\n')
        state={'schema':2,'workspace':ws.WORKSPACE_ID,'updated_at':1,'windows':[w],'complete':True,'warnings':[]}
        ws.CAPTURE_FILE.write_text(json.dumps(state))
        probe={'clients':[dict(w,at=[10,40],size=[800,700],floating=False,fullscreen=0,grouped=[])],
               'monitors':[],'native':{},'terminals':{}}
        with patch.object(ws,'process_start_ticks',return_value='100'),patch.object(ws,'window_identity',return_value=w['restore_id']), \
             patch.object(ws,'save_kitty_session') as export:
            captured=ws.snapshot(probe=probe,promote=False)
        export.assert_not_called();self.assertEqual(captured['windows'][0]['session_file'],w['session_file'])
        self.assertEqual(captured['windows'][0]['at'],[10,40])

    def test_native_fingerprint_ignores_dynamic_title_and_terminal_cells(self):
        tree=[{'tabs':[{'layout':'tall','is_active':True,'title':'spinner1','layout_state':{'ratio':.5},
                       'windows':[{'id':1,'cwd':'/tmp','columns':80,'lines':24}]}]}]
        other=copy.deepcopy(tree);other[0]['tabs'][0]['title']='spinner2'
        other[0]['tabs'][0]['windows'][0]['columns']=120
        self.assertEqual(ws.terminal_fingerprint(tree,{}),ws.terminal_fingerprint(other,{}))
        other[0]['tabs'][0]['layout_state']['ratio']=.7
        self.assertNotEqual(ws.terminal_fingerprint(tree,{}),ws.terminal_fingerprint(other,{}))

    def test_layout_tree_has_nested_axes_and_proportions(self):
        a={'id':'a','at':[10,10],'size':[600,700]}
        b={'id':'b','at':[620,10],'size':[400,340]}
        c={'id':'c','at':[620,370],'size':[400,340]}
        tree=layout.infer_tree([c,a,b])
        self.assertEqual(tree['axis'],0);self.assertEqual(tree['right']['axis'],1)
        self.assertAlmostEqual(tree['ratio'],.59900990099)

    def test_native_grid_maps_exact_tree_boxes_groups_and_order(self):
        windows = [
            dict(window('a'*24), address='0x1', at=[10, 10], size=[500, 700], floating=False),
            dict(window('b'*24), address='0x2', at=[10, 10], size=[500, 700], floating=False),
            dict(window('c'*24), address='0x3', at=[520, 10], size=[500, 700], floating=False),
        ]
        state = {'windows': windows, 'monitors': [], 'warnings': [], 'complete': True}
        grid = {'layout': 'dwindle', 'build_id': 'build', 'work_area': [0, 0, 1024, 768],
                'tree': {'kind': 'split', 'axis': 0, 'split_top': False, 'split_ratio': 1.2,
                         'box': [0, 0, 1024, 768],
                         'first': {'kind': 'tile', 'box': [0, 0, 614, 768], 'windows': ['0x1', '0x2'],
                                   'active': '0x2', 'locked': True, 'is_group': True},
                         'second': {'kind': 'tile', 'box': [614, 0, 410, 768], 'windows': ['0x3'],
                                    'active': '0x3', 'locked': False, 'is_group': True}}}
        layout.apply_native_grid(state, grid)
        self.assertEqual(state['grid']['source'], 'hyprland-native')
        self.assertAlmostEqual(state['tile_tree']['native_split_ratio'], 1.2)
        self.assertEqual(state['tile_tree']['box'], [0, 0, 1024, 768])
        self.assertEqual(state['groups'][0]['members'], ['a'*24, 'b'*24])
        self.assertEqual(state['groups'][0]['active'], 'b'*24)
        self.assertTrue(state['groups'][0]['locked'])
        self.assertTrue(state['groups'][1]['is_group'])  # singleton CGroup keeps its groupbar semantics
        self.assertEqual(state['windows'][0]['group_members'], ['a'*24, 'b'*24])

    def test_native_grid_rejects_missing_or_repeated_tiles(self):
        state = {'windows': [dict(window('a'*24), address='0x1', floating=False)], 'monitors': []}
        duplicate = {'kind': 'split', 'axis': 0, 'split_ratio': 1, 'first':
                     {'kind': 'tile', 'windows': ['0x1'], 'box': [0, 0, 1, 1]}, 'second':
                     {'kind': 'tile', 'windows': ['0x1'], 'box': [1, 0, 1, 1]}}
        with self.assertRaises(ValueError):
            layout.apply_native_grid(state, {'layout': 'dwindle', 'tree': duplicate})

    def test_native_grid_accepts_workspace_with_only_floating_windows(self):
        item = dict(window(), address='0x1', at=[20, 30], size=[600, 400], floating=True)
        state = {'windows': [item], 'monitors': [], 'warnings': []}
        layout.apply_native_grid(state, {'layout': 'dwindle', 'build_id': 'build',
                                         'work_area': [0, 0, 1024, 768], 'tree': None})
        self.assertIsNone(state['tile_tree'])
        self.assertEqual(state['grid']['source'], 'hyprland-native')
        self.assertEqual(state['grid']['tiled_leaves'], 0)

    def test_pruning_saved_tree_keeps_original_ratios_and_collapses_missing_leaf(self):
        tree = {'axis': 0, 'ratio': .6, 'native_split_ratio': 1.2, 'left': {'group': 'kept'},
                'right': {'axis': 1, 'ratio': .5, 'left': {'group': 'missing'}, 'right': {'group': 'other'}}}
        pruned = layout.prune_tree(tree, {'kept', 'other'})
        self.assertEqual(pruned['axis'], 0)
        self.assertEqual(pruned['ratio'], .6)
        self.assertEqual(pruned['right'], {'group': 'other'})

    def test_restore_uses_saved_native_tree_without_reinferring_geometry(self):
        import hashlib
        from types import SimpleNamespace
        first, second = 'a'*24, 'b'*24
        gid_first = hashlib.sha256(first.encode()).hexdigest()[:24]
        gid_second = hashlib.sha256(second.encode()).hexdigest()[:24]
        rows = [
            {'restore_id': first, 'address': '0x1', 'at': [0, 0], 'size': [600, 700], 'floating': False,
             'fullscreen': 0, 'focus_order': 0, 'monitor_name': 'DP-1'},
            {'restore_id': second, 'address': '0x2', 'at': [610, 0], 'size': [390, 700], 'floating': False,
             'fullscreen': 0, 'focus_order': 1, 'monitor_name': 'DP-1'},
        ]
        groups = [{'id': gid_first, 'members': [first], 'is_group': False, 'active': first, 'locked': False,
                   'at': [0, 0], 'size': [600, 700], 'tile_at': [0, 0],
                   'tile_size': [600, 700], 'floating': False, 'fullscreen': 0, 'layout': 'dwindle'},
                  {'id': gid_second, 'members': [second], 'is_group': False, 'active': second, 'locked': False,
                   'at': [610, 0], 'size': [390, 700], 'tile_at': [610, 0],
                   'tile_size': [390, 700], 'floating': False, 'fullscreen': 0, 'layout': 'dwindle'}]
        tree = {'axis': 0, 'ratio': .6, 'native_split_ratio': 1.2, 'left': {'group': gid_first},
                'right': {'group': gid_second}}
        live = [{'address': '0x1', 'workspace': {'id': 1}, 'focusHistoryID': 0, 'floating': False},
                {'address': '0x2', 'workspace': {'id': 1}, 'focusHistoryID': 1, 'floating': False}]
        calls = []
        api = SimpleNamespace(WORKSPACE_ID=1, clients=lambda: live,
                              associated_client=lambda item, _live, _boot: next((c for c in live if c['address'] == item['address']), None),
                              hypr_json=lambda _name: [], dispatch=lambda command: calls.append(command),
                              run=lambda _args: SimpleNamespace(stdout='ok'))
        state = {'boot_id': 'boot', 'windows': rows, 'groups': groups, 'tile_tree': tree,
                 'grid': {'source': 'hyprland-native'}, 'monitors': []}
        with patch.object(layout, 'infer_tree', side_effect=AssertionError('should use saved tree')):
            result = layout.restore(api, state)
        self.assertEqual(result.get('groups'), 2, result)
        self.assertTrue(any('splitratio 1.20000000 exact' in call for call in calls))
        calls.clear()
        def fail_after_staging(command):
            calls.append(command)
            if 'splitratio' in command:
                raise RuntimeError('simulated dispatcher failure')
        api.dispatch = fail_after_staging
        failed = layout.restore(api, state)
        self.assertIn('error', failed)
        self.assertTrue(any('action="disable"' in call for call in calls[calls.index(next(c for c in calls if 'splitratio' in c))+1:]))

    def test_monitor_adaptation_uses_name_and_scale(self):
        group={'at':[100,50],'size':[500,350],'monitor_name':'DP-1','monitor_area':[0,0,1000,700]}
        monitors=[{'id':9,'name':'DP-1','width':2000,'height':1400,'scale':1,'x':0,'y':0}]
        self.assertEqual(layout.target_rect(group,monitors),[200,100,1000,700])

    def test_failed_restore_geometry_is_kept_until_real_change(self):
        desired=window();desired.update(at=[10,40],size=[600,700],floating=False,grouped=[],group_members=[])
        initial=copy.deepcopy(desired);initial['size']=[1000,700]
        target={'schema':3,'workspace':ws.WORKSPACE_ID,'windows':[desired],'updated_at':1}
        observed={'schema':3,'workspace':ws.WORKSPACE_ID,'windows':[initial],'updated_at':2}
        ws.save_restore_guard(target,observed,[{'restore_id':desired['restore_id'],'status':'grupo_pendente',
                                             'verified':{'terminal':True,'group':True,'geometry':False}}])
        kept=ws.preserve_restore_target(observed)
        self.assertEqual(kept['windows'][0]['size'],[600,700]);self.assertFalse(kept['complete'])
        changed=copy.deepcopy(observed);changed['windows'][0]['size']=[800,700]
        accepted=ws.preserve_restore_target(changed)
        self.assertEqual(accepted['windows'][0]['size'],[800,700])

    def test_invalid_old_guard_does_not_replace_current_native_tree(self):
        item = window()
        item.update(address='0x1', at=[10, 10], size=[900, 700], floating=False,
                    group_members=[item['restore_id']], group_active=item['restore_id'], group_locked=False)
        group_id = 'c'*24
        current_tree = {'group': group_id, 'box': [0, 0, 1024, 768]}
        current_group = {'id': group_id, 'members': [item['restore_id']], 'is_group': False,
                         'at': [10, 10], 'size': [900, 700], 'floating': False}
        actual = {'schema': 4, 'workspace': ws.WORKSPACE_ID, 'boot_id': 'boot', 'updated_at': 2,
                  'windows': [item], 'groups': [current_group], 'tile_tree': current_tree,
                  'grid': {'source': 'hyprland-native', 'layout': 'dwindle', 'build_id': 'current-build', 'tiled_leaves': 1},
                  'complete': True, 'warnings': []}
        target = copy.deepcopy(actual)
        target['tile_tree'] = None
        target['groups'] = []
        target['grid'] = None
        observed = copy.deepcopy(actual)
        guard = {'boot_id': 'boot', 'pending': {item['restore_id']: {}},
                 'desired': target, 'observed': observed}
        (ws.STATE_DIR/'RESTORE_GUARD.json').write_text(json.dumps(guard))
        with patch.object(ws, 'boot_id', return_value='boot'):
            kept = ws.preserve_restore_target(actual)
        self.assertEqual(kept['tile_tree'], current_tree)
        self.assertEqual(kept['groups'], [current_group])
        self.assertEqual(kept['grid']['source'], 'hyprland-native')
        old_graph = copy.deepcopy(actual)
        old_graph['grid']['build_id'] = 'different-compositor-build'
        old_group_id = 'd'*24
        old_graph['groups'][0]['id'] = old_group_id
        old_graph['tile_tree'] = {'group': old_group_id}
        guard['desired'] = old_graph
        (ws.STATE_DIR/'RESTORE_GUARD.json').write_text(json.dumps(guard))
        with patch.object(ws, 'boot_id', return_value='boot'):
            kept = ws.preserve_restore_target(actual)
        self.assertEqual(kept['tile_tree'], current_tree)
        self.assertEqual(kept['grid']['build_id'], actual['grid']['build_id'])

if __name__=='__main__':unittest.main(verbosity=2)
