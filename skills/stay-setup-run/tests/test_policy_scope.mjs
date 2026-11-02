import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const require=createRequire(import.meta.url);
const {JSDOM}=require('jsdom');
const helper=readFileSync(new URL('../scripts/stay_helper.js',import.meta.url),'utf8');
const boot=readFileSync(new URL('../scripts/stay_boot.js',import.meta.url),'utf8');

async function result(owners,scope='이 호텔 전용'){
  const rows=owners.map(owner=>`<tr data-stay-entity="policy" data-stay-name="NRF" ${owner===null?'':`data-stay-owner-master-id="${owner}"`}><td>NRF</td></tr>`).join('');
  const dom=new JSDOM(`<input type="hidden" id="master_id" value="123"><ul class="tab-container"><li><a class="active" href="#policies">취소정책</a></li></ul><div id="policies"><table><tbody>${rows}</tbody></table></div>`,{url:'https://example.test/stay/123/#policies',runScripts:'outside-only',pretendToBeVisual:true});
  const w=dom.window;
  w.localStorage.setItem('staySteps',JSON.stringify({guide:{},steps:[{no:1,title:'취소정책 만들기',kind:'취소정책 만들기',head:{tab:'취소정책',buttons_parsed:[]},fields:[{label:'정책명',kind:'typed',value:'NRF',field:'name'},{label:'사용 범위',kind:'select',value:scope,field:'scope'}],longtexts:[],photos:[],submit:'추가'}]}));
  w.eval(helper);w.eval(boot);
  try{return await w.runStep(1,{dry:true});}
  finally{w.stayRun.progressHide();await new Promise(r=>w.setTimeout(r,0));w.close();}
}

test('a policy belonging to another hotel does not skip creating this hotel policy',async()=>{
  assert.notEqual((await result(['456'])).skipped,true);
  assert.notEqual((await result([''])).skipped,true);
});
test('replay only skips the exact requested shared or current-hotel policy',async()=>{
  assert.equal((await result(['123','456',''])).skipped,true);
  assert.equal((await result(['123','456',''],'공용')).skipped,true);
});
test('unknown ownership or duplicate matching policies stop before any action',async()=>{
  for(const owners of [[null],['123','123']]){
    const r=await result(owners);
    assert.notEqual(r.skipped,true);
    assert.equal(r.submitted,false);
    assert.ok(r.error);
  }
});
