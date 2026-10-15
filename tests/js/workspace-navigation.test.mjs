import test from 'node:test';
import assert from 'node:assert/strict';
import {workspaceSelection,activateWorkspace} from '../../public/workspace-navigation.mjs';
test('workspace modes retain validated source and agency evidence sections',()=>{
 assert.ok(workspaceSelection('geography').includes('spatial-heading'));
 assert.ok(workspaceSelection('validation').includes('frap-heading'));
 assert.ok(workspaceSelection('overview').includes('historical-timeline-heading'));
});
test('focus mode hides only unrelated sections, all mode restores them',()=>{
 const sections=['spatial-heading','annual-heading','frap-heading'].map(name=>({
  hidden:false,getAttribute:()=>name
 }));
 activateWorkspace('geography',sections);
 assert.deepEqual(sections.map(x=>x.hidden),[false,true,true]);
 activateWorkspace('all',sections);
 assert.deepEqual(sections.map(x=>x.hidden),[false,false,false]);
 assert.throws(()=>workspaceSelection('untrusted'),/Unknown/);
});
