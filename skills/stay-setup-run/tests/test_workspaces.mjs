import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const require=createRequire(import.meta.url);
const {JSDOM}=require('jsdom');
const dom=new JSDOM(`<ul class="tab-container"><li><a class="active" href="#plans">요금제</a></li></ul>
<div id="plans"><div class="is-workspace-ready" data-workspace="rate-plans">
<button data-workspace-view-button="catalog" aria-pressed="true">공통 요금제</button>
<button data-workspace-view-button="rooms" aria-pressed="false">객실별 요금제</button>
<section id="catalog"><h4>공통 요금제</h4><button>빠진 룸에 붙이기</button></section>
<section id="rooms" hidden><h4>2026 계약 · 디럭스</h4><button>요금제 추가</button></section>
</div></div>`,{url:'http://example.test/stay/1/',runScripts:'dangerously',pretendToBeVisual:true});
const win=dom.window,doc=win.document;
for(const button of doc.querySelectorAll('[data-workspace-view-button]')) button.addEventListener('click',()=>{
 for(const b of doc.querySelectorAll('[data-workspace-view-button]')) b.setAttribute('aria-pressed',String(b===button));
 for(const id of ['catalog','rooms']) doc.getElementById(id).hidden=id!==button.dataset.workspaceViewButton;
});
win.eval(readFileSync(new URL('../scripts/stay_helper.js',import.meta.url),'utf8'));
for(const spec of [{kind:'요금제 배포',button:'요금제 추가',card:'2026 계약 · 디럭스'},
 {kind:'객실별 붙이기',button:'요금제 추가'},{button:'이 객실에 배포'},{button:'이 룸에 붙이기'}]){
 const r=await win.stayRun.workspace(spec);assert.equal(r.view,'rooms');assert.equal(doc.getElementById('rooms').hidden,false);
}
for(const spec of [{kind:'요금제 정본'},{button:'빠진 룸에 붙이기'},{button:'전체 적용'},{card:'공통 요금제'}]){
 const r=await win.stayRun.workspace(spec);assert.equal(r.view,'catalog');assert.equal(doc.getElementById('catalog').hidden,false);
}
const deploy=doc.createElement('section');deploy.dataset.stayScreen='rate-plan-deploy';
deploy.innerHTML='<button data-stay-action="deploy">이 객실에 배포</button>';doc.body.append(deploy);
assert.equal(win.stayRun.findButton(deploy,'이 룸에 붙이기'),deploy.firstChild);
deploy.firstChild.removeAttribute('data-stay-action');
assert.equal(win.stayRun.findButton(deploy,'이 룸에 붙이기'),deploy.firstChild);
deploy.firstChild.textContent='이 룸에 붙이기';
assert.equal(win.stayRun.findButton(deploy,'이 객실에 배포'),deploy.firstChild);
console.log('11 workspace/alias assertions passed');win.close();
