import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const require=createRequire(import.meta.url);
const {JSDOM}=require('jsdom');
const helper=readFileSync(new URL('../scripts/stay_helper.js',import.meta.url),'utf8');
const boot=readFileSync(new URL('../scripts/stay_boot.js',import.meta.url),'utf8');

function row(key,los,price=''){
  return `<tbody data-stay-occupancy-key="${key}" data-stay-los-nights="${los}"><tr><th>翻訳された見出し</th><td><input type="number" data-stay-col="price" value="${price}"></td><td><input type="number" data-stay-col="original_price"></td><td><input type="number" data-stay-col="net_amount"></td></tr></tbody>`;
}
function fixture(rows){
  const dom=new JSDOM(`<table data-stay-rows="prices" data-stay-field="prices">${rows}</table>`,{url:'https://example.test/stay/123/',runScripts:'outside-only',pretendToBeVisual:true});
  dom.window.eval(helper);
  return dom;
}
const field=(key='A2',los=1,col='price',value='123456')=>({label:'판매가',kind:'typed',field:'prices',field_col:col,occupancy_key:key,los_nights:los,value});

test('price input and readback identify occupancy, LOS and column even after rows move',async()=>{
  const dom=fixture(row('A2',2,'202')+row('A1',1,'101')+row('A2',1,'201'));
  const w=dom.window,d=w.document;
  try{
    const r=await w.stayRun.fill([field()]);
    assert.equal(r[0].status,'ok');
    assert.equal(r[0].matchedBy,'hook');
    assert.deepEqual([...d.querySelectorAll('[data-stay-col="price"]')].map(e=>e.value),['202','101','123456']);
    assert.equal(w.stayRun.readback([field()]).ok,1);
    d.querySelector('table').prepend(d.querySelector('[data-stay-occupancy-key="A2"][data-stay-los-nights="1"]'));
    assert.equal((await w.stayRun.fill([field('A2',1,'net_amount','0')]))[0].status,'ok');
    assert.equal(w.stayRun.readback([field('A2',1,'net_amount','0')]).ok,1);
    assert.deepEqual([...d.querySelectorAll('[data-stay-col="net_amount"]')].map(e=>e.value),['0','','']);
    assert.equal(d.querySelector('[data-stay-col="original_price"]').value,'');
  }finally{w.close();}
});

test('a missing, ambiguous or incomplete price identity stops without label or order fallback',async()=>{
  for(const [rows,f] of [
    [row('A1',1,'111'),field()],
    [row('A2',2,'222'),field()],
    [row('A2',1,'111')+row('A2',1,'222'),field()],
    [row('A2',1,'111'),{label:'판매가',kind:'typed',field:'prices',value:'9'}],
    [row('A2',1,'111'),field('A2',0)],
    [row('A2',1,'111'),field('A2',1,'invalid')],
    [row('A2',1,'111'),{...field(),field:undefined}],
    [row('A1',1,''),{...field(),kind:'empty'}],
  ]){
    const dom=fixture(rows),w=dom.window;
    try{
      const before=[...w.document.querySelectorAll('input')].map(e=>e.value);
      const r=await w.stayRun.fill([f]);
      assert.equal(r[0].status,'error');
      assert.notEqual(r[0].byOrder,true);
      assert.deepEqual([...w.document.querySelectorAll('input')].map(e=>e.value),before);
      assert.equal(w.stayRun.readback([f]).fields[0].same,false);
      assert.notEqual(w.stayRun.readback([f]).fields[0].byOrder,true);
    }finally{w.close();}
  }
});

test('empty occupancy key is a valid single-price identity and survives the boot field adapter',async()=>{
  const dom=fixture(row('',1,'12')+row('A1',1,'99')),w=dom.window;
  try{
    w.localStorage.setItem('staySteps',JSON.stringify({steps:[{no:1,fields:[field('',1,'price','0')],longtexts:[]}]}));
    w.eval(boot);
    const fields=w.stepFields(1);
    assert.equal((await w.stayRun.fill(fields))[0].status,'ok');
    assert.equal(w.stayRun.readback(fields).ok,1);
    assert.deepEqual([...w.document.querySelectorAll('[data-stay-col="price"]')].map(e=>e.value),['0','99']);
  }finally{w.stayRun.progressHide();await new Promise(r=>w.setTimeout(r,0));w.close();}
});
