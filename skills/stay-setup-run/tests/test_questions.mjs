import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const {JSDOM} = createRequire(import.meta.url)('jsdom');
const boot = readFileSync(new URL('../scripts/stay_boot.js', import.meta.url), 'utf8');
const labels = ['구분','질문','필수 여부','선택지 표시 방식','안내문','선택지 (한 줄에 하나)'];
const fields = [
  {label:labels[0],kind:'select',value:'객관식'}, {label:labels[1],kind:'typed',value:'이용 시간'},
  {label:labels[2],kind:'check'}, {label:labels[3],kind:'select',value:'셀렉트 박스형'},
  {label:labels[4],kind:'empty'}];
const step = {no:1, title:'정보 수집 질문 만들기',kind:'정보 수집 질문 만들기',head:{tab:'혜택',card:'샘플 오퍼 · 혜택 · 픽업',buttons_parsed:[]},fields,
  longtexts:[{label:labels[5],text:'10:15\n서울, 인천'}],submit:'질문 추가'};

function fixture(type='혜택', options={}) {
  const w = new JSDOM('<main></main><div id="stay_drawer_body"></div>', {url:'https://example.invalid/stay/',runScripts:'outside-only'}).window;
  let state = options.existing ? ['객관식','이용 시간',true,'셀렉트 박스형','','10:15\n서울, 인천'] : null;
  if (state && options.title) state[1] = options.title;
  let writes=0;
  const doc=w.document;
  const offer = doc.querySelector('main');
  offer.innerHTML=type==='부가옵션' ? '<div data-stay-entity="addon" data-stay-name="픽업"><table><tr><th>오퍼</th><td>샘플 오퍼</td></tr></table><button>정보 수집 폼</button></div>' :
    `<div data-stay-entity="offer" data-stay-name="샘플 오퍼"><div data-stay-entity="${type==='혜택'?'benefit':'charge'}" data-stay-name="픽업"><button>${type==='혜택'?'편집':'정보 수집 폼'}</button></div></div>`;
  function panel(edit=false) {
    const id=type==='혜택'?'stay_benefit_questions':'stay_item_questions';
    const root=doc.createElement('div');root.id=id;
    root.innerHTML=Array.from({length:options.extraRows||0},(_,i)=>`<p>기존 질문 ${i} (단답형) <button>편집</button><button>삭제</button></p>`).join('')+(state?'<p>'+state[1]+' (객관식) · 필수 <button>편집</button><button>삭제</button></p>':'<p>등록된 질문이 없습니다.</p>')+
      labels.map((l,i)=>`<p><label for="q${i}">${l}</label>${i===0?'<select id="q0"><option>단답형</option><option>객관식</option><option>서술형</option></select>':i===3?'<select id="q3"><option>칩 선택형</option><option>셀렉트 박스형</option></select>':i===2?'<input id="q2" type="checkbox">':i>3?`<textarea id="q${i}"></textarea>`:`<input id="q${i}">`}</p>`).join('')+
      `<button class="save">${edit?'질문 저장':'질문 추가'}</button>`;
    if(edit) labels.forEach((_,i)=>{const el=root.querySelector('#q'+i);if(i===2)el.checked=state[i];else el.value=state[i];});
    Array.from(root.querySelectorAll('p')).find(p=>p.firstChild?.textContent.startsWith(state?.[1]+' ('))?.querySelector('button')?.addEventListener('click',()=>replace(true));
    root.querySelector('.save').addEventListener('click',()=>{
      writes++;
      if(options.failSave)return;
      state=labels.map((_,i)=>{const el=root.querySelector('#q'+i);return i===2?el.checked:el.value;});
      if(options.corrupt)state[3]='칩 선택형';
      replace(false);
    });
    return root;
  }
  function replace(edit){doc.querySelector('#stay_drawer_body').replaceChildren(panel(edit));}
  offer.querySelector('button').addEventListener('click',()=>replace(false));
  if(options.duplicate)offer.appendChild(offer.firstElementChild.cloneNode(true));
  w.stayRun={tab:async()=>({status:'ok'}),waitFor:async fn=>!!fn()};
  w.localStorage.setItem('staySteps',JSON.stringify({steps:[step]}));w.eval(boot);
  return {w,writes:()=>writes,state:()=>state};
}

for(const type of ['혜택','부과금','부가옵션']) {
  const f=fixture(type), s={...step,head:{...step.head,tab:type,card:`샘플 오퍼 · ${type} · 픽업`}};
  assert.equal(typeof f.w.runQuestionStep,'function');
  const r=await f.w.runQuestionStep(s,{});
  assert.equal(r.submitted,true,JSON.stringify(r));assert.equal(r.verified,true);
  assert.equal(f.writes(),1);assert.equal(f.state()[5],'10:15\n서울, 인천');f.w.close();
}
// 현재 화면에 있는 질문까지 합쳐 200개를 넘기는 신규 쓰기를 막는다.
for(const type of ['혜택','부과금','부가옵션']) {
  for(const count of [199,200]) {
    const f=fixture(type,{extraRows:count}), s={...step,head:{...step.head,tab:type,card:`샘플 오퍼 · ${type} · 픽업`}};
    const r=await f.w.runQuestionStep(s,{});
    assert.equal(f.writes(),count===199?1:0,JSON.stringify(r));
    if(count===200){assert.equal(r.submitted,false);assert.equal(r.verified,false);assert.match(r.error,/200/);}
    else assert.equal(r.verified,true,JSON.stringify(r));
    f.w.close();
  }
}
{
  const f=fixture('혜택',{existing:true,extraRows:199});const r=await f.w.runQuestionStep(step,{});
  assert.equal(r.verified,true);assert.equal(r.skipped,true);assert.equal(f.writes(),0);f.w.close();
}
{
  const f=fixture('혜택',{existing:true,extraRows:199});
  const edit={...step,kind:'정보 수집 질문 고치기',submit:'질문 저장',head:{...step.head,buttons_parsed:[{text:'편집',row:'이용 시간'}]},fields:step.fields.map(f=>f.label==='질문'?{...f,value:'새 이용 시간'}:f)};
  const r=await f.w.runQuestionStep(edit,{});
  assert.equal(r.verified,true,JSON.stringify(r));assert.equal(f.writes(),1);f.w.close();
}
for(const opt of [{duplicate:true},{failSave:true},{corrupt:true}]) {
  const f=fixture('혜택',opt);const r=await f.w.runQuestionStep(step,{});
  assert.equal(r.verified,false,JSON.stringify(r));assert.ok(r.error);
  if(opt.duplicate)assert.equal(f.writes(),0);else assert.equal(f.writes(),1);
  f.w.close();
}
{
  const f=fixture('혜택',{existing:true});const r=await f.w.runQuestionStep(step,{});
  assert.equal(r.verified,true);assert.equal(r.skipped,true);assert.equal(f.writes(),0);f.w.close();
}
{
  const f=fixture('혜택',{existing:true});
  const renamed={...step,kind:'정보 수집 질문 고치기',submit:'질문 저장',head:{...step.head,buttons_parsed:[{text:'편집',row:'예전 시간 제목'}]}};
  const r=await f.w.runQuestionStep(renamed,{});
  assert.equal(r.verified,true);assert.equal(r.skipped,true);assert.equal(f.writes(),0);f.w.close();
}
{
  const f=fixture('혜택',{existing:true,title:'이용 시간 (현지)'});
  const edit={...step,kind:'정보 수집 질문 고치기',submit:'질문 저장',head:{...step.head,buttons_parsed:[{text:'편집',row:'이용 시간'}]}};
  const r=await f.w.runQuestionStep(edit,{});
  assert.equal(r.verified,false);assert.ok(r.error);assert.equal(f.writes(),0);f.w.close();
}
{
  const f=fixture();const r=await f.w.runQuestionStep(step,{dry:true});
  assert.equal(r.submitted,false);assert.equal(f.writes(),0);f.w.close();
}
{
  const f=fixture();f.w.localStorage.setItem('staySteps',JSON.stringify({steps:[{...step,kind:'원화 표시 설정 확인'}]}));f.w.eval(boot);
  const r=await f.w.runStepCore(1,{});assert.equal(r.manualAction,true);assert.equal(r.submitted,false);assert.ok(r.error);assert.equal(f.writes(),0);f.w.close();
}
console.log('question browser tests passed (3 owners, save readback, fail closed, replay, dry, CCS boundary)');

// 현장과 온라인 연령 칸의 화면 라벨은 같다. 접두로 소속을 구분하고 다른 칸에 쓰지 않는다.
{
  const helper=readFileSync(new URL('../scripts/stay_helper.js',import.meta.url),'utf8');
  const w=new JSDOM('<div class="stay-drawer is-open"><div id="stay_drawer_body"><section class="stay-card" data-stay-card="onsite"><h4>현장 결제 안내</h4><label for="on">소아</label><input id="on" value="7"></section><section class="stay-card" data-stay-card="age_rates"><h4>연령별 단가</h4><table><tbody><tr><th>소아</th><td>만 5~11세</td><td><input id="online" value="8"></td></tr></tbody></table></section></div></div>',{url:'https://example.invalid/',runScripts:'outside-only'}).window;
  w.eval(helper);
  const fs=[{label:'현장 연령별 단가 · 소아',kind:'typed',value:'0'},{label:'연령별 단가 · 소아',kind:'typed',value:'3'}];
  const result=await w.stayRun.fill(fs);assert.ok(result.every(r=>r.status==='ok'),JSON.stringify(result));
  assert.equal(w.document.querySelector('#on').value,'0');assert.equal(w.document.querySelector('#online').value,'3');
  assert.equal(w.stayRun.readback(fs).ok,2);
  w.document.querySelector('[data-stay-card="onsite"]').remove();
  const missing=await w.stayRun.fill([fs[0]]);assert.equal(missing[0].status,'error');
  assert.equal(w.document.querySelector('#online').value,'3');w.close();
}
console.log('onsite and online age amount isolation tests passed');
{
  const f=fixture();
  const values=f.w.customerOptionFields({kind:'택1 그룹 만들기'},[{label:'그룹 이름',kind:'typed',value:'샘플 그룹'}]);
  assert.equal(values.find(x=>x.label==='선택 상한').value,'1');
  assert.equal(values.find(x=>x.label==='정확히 하나 선택 (끄면 선택 사항)').kind,'check');
  f.w.close();
}
