import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const require=createRequire(import.meta.url);
const {JSDOM}=require('jsdom');
const helper=readFileSync(new URL('../scripts/stay_helper.js',import.meta.url),'utf8');

function screen(names,multiple=true){
  const d=new JSDOM(`<input type="file" id="target" ${multiple?'multiple':''}>`,{url:'https://example.test/stay/123/',runScripts:'outside-only',pretendToBeVisual:true});
  const w=d.window;let changes=0;
  w.DataTransfer=class{constructor(){this.files=[];this.items={add:file=>this.files.push(file)};}};
  w.eval(helper);w.stayRun.bridge();
  Object.defineProperty(w.document.getElementById('stay_file_bridge'),'files',{value:names.map(name=>new w.File(['photo'],name))});
  const target=w.document.getElementById('target');Object.defineProperty(target,'files',{value:[],writable:true});
  target.addEventListener('change',()=>changes++);
  return {w,target,changes:()=>changes,close:()=>w.close()};
}

test('missing requested files stop before any native change event',async()=>{
  const s=screen(['a.jpg']);try{
    const r=await s.w.stayRun.takeFiles({names:['a.jpg','b.jpg'],wait:0});
    assert.notEqual(r.status,'ok');assert.equal(s.changes(),0);assert.equal(s.target.files.length,0);
  }finally{s.close();}
});
test('multiple requested photos cannot be silently truncated by a single-file field',async()=>{
  const s=screen(['a.jpg','b.jpg'],false);try{
    const r=await s.w.stayRun.takeFiles({names:['a.jpg','b.jpg'],wait:0});
    assert.notEqual(r.status,'ok');assert.equal(s.changes(),0);assert.equal(s.target.files.length,0);
  }finally{s.close();}
});
test('a multi-photo field receives all requested files from one bridge upload',async()=>{
  const s=screen(['a.jpg','b.jpg']);try{
    const r=await s.w.stayRun.takeFiles({names:['a.jpg','b.jpg'],wait:0});
    assert.equal(r.status,'ok');assert.deepEqual(Array.from(r.moved),['a.jpg','b.jpg']);assert.equal(s.target.files.length,2);
  }finally{s.close();}
});
test('one-photo modal transfers can reuse a batch bridge without clearing the other files',async()=>{
  const s=screen(['a.jpg','b.jpg'],false);try{
    assert.equal((await s.w.stayRun.takeFiles({names:['b.jpg'],wait:0})).status,'ok');
    assert.equal(s.target.files[0].name,'b.jpg');
    assert.equal(s.w.document.getElementById('stay_file_bridge').files.length,2);
    assert.equal((await s.w.stayRun.takeFiles({names:['a.jpg'],wait:0})).status,'ok');
    assert.equal(s.target.files[0].name,'a.jpg');
  }finally{s.close();}
});
