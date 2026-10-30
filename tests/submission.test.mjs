import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../platform.js',import.meta.url),'utf8').split("window.addEventListener('hashchange'")[0];
const context=vm.createContext({document:{getElementById:()=>({})},location:{href:'https://example.test/gotc/platform.html#team'},URL,TextEncoder,Intl,Date,setTimeout,clearTimeout});
vm.runInContext(source+'\nglobalThis.helpers={submissionState,safeMaterialUrl,materialMarkup,judgeSubmissionMarkup,teamFormMarkup,windowMarkup,beijingInput,parseBeijingInput,beijingTime};',context);
const h=context.helpers;

test('submission states distinguish empty, draft and changes after formal submission',()=>{
  assert.equal(h.submissionState({}),'未保存');
  assert.equal(h.submissionState({draft:{}}),'草稿');
  assert.equal(h.submissionState({draft:{},submitted:{}}),'已正式提交');
  assert.equal(h.submissionState({draft:{},submitted:{},hasUnsubmittedChanges:true}),'已提交且有草稿修改');
});

test('material links allow complete HTTPS and independently reject executable or malformed URLs',()=>{
  assert.equal(h.safeMaterialUrl(' https://example.test/readme?q=one#run '),'https://example.test/readme?q=one#run');
  for(const url of ['javascript:alert(1)','data:text/html,x','http://example.test','//example.test','/relative','https://u:p@example.test','https://@example.test','https://exa<mple.test','https://exa|mple.test','https://%40example.test','https://under_score.test','https://[bad','https://example.test:bad','https://example.test/a b','https://example.test/a\\b','https://example.test/%0aheader','https://example.test/'+('中'.repeat(400))])assert.equal(h.safeMaterialUrl(url),'',url);
  const html=h.materialMarkup({projectName:'<img src=x onerror=alert(1)>',summary:'<script>unsafe</script>',codeUrl:'javascript:alert(1)',readmeUrl:'https://example.test/readme?x="&y=1',confirmed:true});
  assert.ok(!html.includes('<img'));
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('href="javascript:'));
  assert.match(html,/&lt;img/);
  assert.match(html,/target="_blank" rel="noopener noreferrer"/);
  assert.match(html,/x=&quot;&amp;y=1/);
});

test('judge material block only renders its formal projection and preserves the unsubmitted scoring state',()=>{
  const html=h.judgeSubmissionMarkup({version:2,submittedAt:0,materials:{projectName:'FORMAL_VISIBLE'},draft:{projectName:'PRIVATE_DRAFT'}});
  assert.match(html,/FORMAL_VISIBLE/);
  assert.ok(!html.includes('PRIVATE_DRAFT'));
  assert.match(html,/正式版本 2/);
  assert.match(html,/1970/);
  assert.match(h.judgeSubmissionMarkup(null),/仍可根据现场演示评分/);
});

test('team form prefills draft and fixed server identity without allowing a team selector',()=>{
  const data={team:{id:'T1',project:'PUBLIC_TITLE'},submission:{version:1,draft:{projectName:'DRAFT_TITLE',summary:'</textarea><script>bad</script>'}},window:{canEdit:true}};
  const html=h.teamFormMarkup(data);
  assert.match(html,/DRAFT_TITLE/);
  assert.ok(!html.includes('PUBLIC_TITLE'));
  assert.ok(!html.includes('name="teamId"'));
  assert.match(html,/&lt;\/textarea&gt;/);
  assert.match(html,/type="button" id="save-submission-draft"/);
  assert.match(html,/novalidate/);
  assert.match(h.teamFormMarkup({...data,window:{canEdit:false}}),/<fieldset disabled>/);
});

test('Beijing datetime conversion is independent of browser timezone and handles epoch zero',()=>{
  assert.equal(h.beijingInput(0),'1970-01-01T08:00');
  assert.equal(h.parseBeijingInput('1970-01-01T08:00'),0);
  assert.equal(h.beijingInput(null),'');
  assert.equal(h.parseBeijingInput(''),null);
  const deadline=Date.parse('2026-11-08T14:30:00+08:00');
  assert.equal(h.beijingInput(deadline),'2026-11-08T14:30');
  assert.equal(h.parseBeijingInput('2026-11-08T14:30'),deadline);
  assert.throws(()=>h.parseBeijingInput('2026-02-30T14:30'));
  assert.throws(()=>h.parseBeijingInput('invalid'));
});


test('submission notice explains save-time checks and mutable external content',()=>{
  const html=h.windowMarkup({canEdit:true,submissionDeadline:null});
  assert.match(html,/实际保存前检查提交窗口和材料版本/);
  assert.match(html,/点击提交不代表已保存/);
  assert.match(html,/只保存填写的内容和链接/);
  assert.match(html,/不会抓取或检查外链内容/);
  assert.match(html,/文件之后仍可能变化/);
  assert.ok(!html.includes('服务器接收时'));
  assert.match(h.windowMarkup({canEdit:false,submissionDeadline:0}),/当前作品提交只读/);
});
