import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const require=createRequire(import.meta.url);
const {JSDOM}=require('jsdom');
const helper=readFileSync(new URL('../scripts/stay_helper.js',import.meta.url),'utf8');
const boot=readFileSync(new URL('../scripts/stay_boot.js',import.meta.url),'utf8');

function screen(body,steps=[]){
  const d=new JSDOM(`<ul class="tab-container"><li><a href="#pane" class="active">요금제</a></li></ul><div id="pane">${body}</div>`,{url:'https://example.test/stay/123/#pane',runScripts:'outside-only',pretendToBeVisual:true});
  const w=d.window;
  w.localStorage.setItem('staySteps',JSON.stringify({guide:{},steps}));w.eval(helper);w.eval(boot);
  return {w,close:async()=>{w.stayRun.progressHide();await new Promise(r=>w.setTimeout(r,0));w.close();}};
}

test('room creation replay finds the existing room in the native room-types panel',async()=>{
  const s=screen('<div data-stay-panel="room_types"><table><tbody><tr data-stay-entity="room_type" data-stay-name="Deluxe"><td>Deluxe</td></tr></tbody></table></div>');
  try{
    assert.equal(await s.w.existsInListWait('Deluxe','객실 (룸 타입)'),true);
    assert.equal(await s.w.existsInListWait('Missing','객실 (룸 타입)'),false);
    assert.equal(await s.w.existsInListWait('Deluxe','다른 오퍼'),false);
  }finally{await s.close();}
});

test('an explicit longer room name cannot satisfy a different room name',async()=>{
  const s=screen('<div data-stay-panel="room_types"><table><tbody><tr data-stay-entity="room_type" data-stay-name="Deluxe Suite"><td>Deluxe Suite</td></tr></tbody></table></div>');
  try{
    Object.defineProperty(s.w.HTMLElement.prototype,'innerText',{get(){return this.textContent;}});
    assert.equal(await s.w.existsInListWait('Deluxe','객실 (룸 타입)'),false);
  }finally{await s.close();}
});

function applyStep(){return {no:1,title:'요금제 전체 적용',kind:'요금제 전체 적용',head:{tab:'요금제',card:'공통 요금제',buttons_parsed:[{text:'전체 적용',row:'Breakfast'}]},fields:[],longtexts:[],photos:[],submit:'전체 적용'};}

test('apply-all is a verified no-op when the exact plan already covers every room',async()=>{
  const s=screen('<div class="stay-card"><h4 class="stay-card__head">공통 요금제</h4><table><tbody><tr data-stay-entity="rate_plan_catalog" data-stay-name="Breakfast"><td>Breakfast</td><td class="stay-numeric">3 / 3개 룸</td></tr></tbody></table></div>',[applyStep()]);
  try{
    const r=await s.w.runStep(1);
    assert.equal(r.skipped,true);
    assert.equal(r.submitted,false);
    assert.equal(s.w.stepFailed(r),false);
  }finally{await s.close();}
});

test('missing or partial deployment is not reported as an apply-all success',async()=>{
  for(const count of ['2 / 3개 룸','0 / 0개 룸','']){
    const s=screen(`<div class="stay-card"><h4 class="stay-card__head">공통 요금제</h4><table><tbody><tr data-stay-entity="rate_plan_catalog" data-stay-name="Breakfast"><td>Breakfast</td><td class="stay-numeric">${count}</td></tr></tbody></table></div>`,[applyStep()]);
    try{
      const r=await s.w.runStep(1);
      assert.notEqual(r.skipped,true);
      assert.equal(s.w.stepFailed(r),true);
    }finally{await s.close();}
  }
});
