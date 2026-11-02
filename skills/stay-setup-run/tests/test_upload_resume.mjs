import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const require=createRequire(import.meta.url);
const {JSDOM}=require('jsdom');
const helper=readFileSync(new URL('../scripts/stay_helper.js',import.meta.url),'utf8');
const boot=readFileSync(new URL('../scripts/stay_boot.js',import.meta.url),'utf8');

function screen(){
  const dom=new JSDOM(`<ul class="tab-container"><li><a class="active" href="#offers">오퍼</a></li></ul>
    <div id="offers"><button id="add">오퍼 추가</button><button id="other">다른 오퍼</button></div>
    <aside class="stay-drawer"><div id="stay_drawer_body"></div></aside>`,
    {url:'https://example.test/stay/123/',runScripts:'outside-only',pretendToBeVisual:true});
  const w=dom.window,doc=w.document;let opens=0,savedFiles=null;
  for(const id of ['add','other']) doc.getElementById(id).onclick=()=>{
    opens++;
    doc.querySelector('.stay-drawer').classList.add('is-open');
    doc.getElementById('stay_drawer_body').innerHTML=`<div data-stay-screen="offer"><input type="file" name="image_file" data-stay-field="image_file"><p>${'x'.repeat(opens)}</p><button type="button" data-stay-action="save">추가</button></div>`;
    doc.querySelector('[data-stay-action=save]').onclick=()=>{
      savedFiles=[...doc.querySelector('input[type=file]').files].map(f=>f.name);
      doc.querySelector('.stay-drawer').classList.remove('is-open');
    };
  };
  w.eval(helper);w.stayRun.config({waitMs:1200});
  return {w,doc,opens:()=>opens,savedFiles:()=>savedFiles,close:async()=>{w.stayRun.progressHide();await new Promise(resolve=>w.setTimeout(resolve,0));w.close();}};
}

function loadOfferStep(s){
  s.w.localStorage.setItem('staySteps',JSON.stringify({guide:{},steps:[{no:1,title:'오퍼 만들기',kind:'오퍼 만들기',
    head:{tab:'오퍼',buttons_parsed:[{text:'오퍼 추가'}]},
    fields:[{label:'오퍼 이미지',kind:'file',file:'hero.jpg',field:'image_file'}],
    longtexts:[],photos:[{file:'hero.jpg'}],submit:'추가',submit_action:'save'}]}));
  s.w.eval(boot);
}

test('resuming the same drawer preserves the selected upload file',async()=>{
  const s=screen();try{
    assert.equal((await s.w.stayRun.open({button:'오퍼 추가'})).status,'ok');
    const file=s.doc.querySelector('input[type=file]');
    Object.defineProperty(file,'files',{value:[new s.w.File(['photo'],'hero.jpg',{type:'image/jpeg'})]});
    assert.equal((await s.w.stayRun.open({button:'오퍼 추가'})).status,'already');
    assert.equal(s.opens(),1);
    assert.equal(s.doc.querySelector('input[type=file]'),file);
    assert.equal(file.files[0].name,'hero.jpg');
  }finally{await s.close();}
});

test('a different opener is not treated as the existing upload drawer',async()=>{
  const s=screen();try{
    await s.w.stayRun.open({button:'오퍼 추가'});
    assert.equal((await s.w.stayRun.open({button:'다른 오퍼'})).status,'ok');
    assert.equal(s.opens(),2);
  }finally{await s.close();}
});

test('a replaced drawer body is not reused as the old upload target',async()=>{
  const s=screen();try{
    await s.w.stayRun.open({button:'오퍼 추가'});
    s.doc.getElementById('stay_drawer_body').innerHTML='<div data-stay-screen="room">another target</div>';
    assert.equal((await s.w.stayRun.open({button:'오퍼 추가'})).status,'ok');
    assert.equal(s.opens(),2);
  }finally{await s.close();}
});

test('stepFields keeps the planned filename so fill requests the upload',async()=>{
  const s=screen();try{
    s.w.localStorage.setItem('staySteps',JSON.stringify({guide:{},steps:[{no:1,title:'오퍼 만들기',kind:'오퍼 만들기',fields:[{label:'오퍼 이미지',kind:'file',file:'hero.jpg',field:'image_file'}],longtexts:[]}]}));
    s.w.eval(boot);
    await s.w.stayRun.open({button:'오퍼 추가'});
    const fields=s.w.stepFields(1);
    assert.equal(fields[0].file,'hero.jpg');
    const result=await s.w.stayRun.fill(fields);
    assert.equal(result[0].status,'needs-upload');
  }finally{await s.close();}
});

test('the ordinary runStep upload resume submits the selected file',async()=>{
  const s=screen();try{
    loadOfferStep(s);
    assert.equal((await s.w.runStep(1)).waitingFiles,true);
    const input=s.doc.querySelector('input[type=file]');
    Object.defineProperty(input,'files',{value:[new s.w.File(['photo'],'hero.jpg',{type:'image/jpeg'})]});
    const result=await s.w.runStep(1,{uploaded:true});
    assert.equal(result.submit,'closed');
    assert.deepEqual(s.savedFiles(),['hero.jpg']);
    assert.equal(s.opens(),1);
  }finally{await s.close();}
});

test('uploaded=true cannot silently save an empty or different file input',async()=>{
  for(const name of [null,'different.jpg']){
    const s=screen();try{
      loadOfferStep(s);
      await s.w.runStep(1);
      if(name)Object.defineProperty(s.doc.querySelector('input[type=file]'),'files',{value:[new s.w.File(['photo'],name,{type:'image/jpeg'})]});
      const result=await s.w.runStep(1,{uploaded:true});
      assert.equal(result.submitted,false);
      assert.equal(s.savedFiles(),null);
      assert.ok((result.bad||[]).length>0);
    }finally{await s.close();}
  }
});
