import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';import {execFileSync} from 'node:child_process';
const path='hackathon/트민두AI_프로토타입.html',html=fs.readFileSync(path,'utf8'),original=execFileSync('git',['show','HEAD:'+path],{encoding:'utf8',maxBuffer:8*1024*1024});
assert.equal(html,fs.readFileSync('index.html','utf8'));
const avatar=h=>h.match(/const AVATAR_IMAGES=([\s\S]*?);\s*function picture/)[0];assert.equal(avatar(html),avatar(original));
const scripts=h=>[...h.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);for(const s of scripts(html))new vm.Script(s);
for(let i=0;i<4;i++)assert.equal(scripts(html)[i],scripts(original)[i],'Learning library/core scripts remain unchanged');
const app=scripts(html).at(-1),old=scripts(original).at(-1);assert.equal(app.match(/const empty=\(\)=>\([^\n]+/)[0],old.match(/const empty=\(\)=>\([^\n]+/)[0]);
const feature=app.slice(app.indexOf('// Remote headlines'),app.indexOf('function home()')),esc=app.match(/const esc=[^\n]+/)[0];
assert.ok(feature.includes("$('[data-collected-filter]').forEach"),'Bind all filter buttons');
let renders=0,calls=0;const ctx=vm.createContext({URL,Intl,Date,AbortController,setTimeout,clearTimeout,render:()=>renders++});vm.runInContext(esc+'\n'+feature,ctx);
assert.equal(vm.runInContext("collectedNewsSection().includes('불러오는 중')",ctx),true);
for(const url of ['javascript:alert(1)','http://example.com','data:text/html,test','https://user:pass@example.com','https://example.com/\nx']){ctx.url=url;assert.equal(vm.runInContext('collectedHttps(url)',ctx),null)}
assert.equal(vm.runInContext("collectedHttps('https://example.com/a?x=1&b=2')",ctx),'https://example.com/a?x=1&b=2');
assert.equal(vm.runInContext("collectedDate('2026-11-21T17:34:22+09:00',true)",ctx),'2026.11.21 17:34');assert.equal(vm.runInContext('collectedDate(null)',ctx),'발행일 미상');
ctx.fixture={updatedAt:'2026-11-21T17:34:22+09:00',items:Array.from({length:12},(_,i)=>({id:String(i),source:i%3===0?'GitHub':i%3===1?'TLDR AI':'OpenAI',sourceKey:i%3===0?'github':i%3===1?'tldr':'openai',sourceType:i%3===0?'GitHub 인기 저장소':i%3===1?'뉴스레터':'AI 기업 블로그',title:'항목 '+i,published:'2026-11-'+String(i+1).padStart(2,'0'),url:'https://example.com/'+i,status:'검수 대기',tag:'AI 모델',stars:1000,language:'Python',description:'설명'}))};
ctx.fixture.items.push({title:'숨겨야 함',status:'제외',url:'https://example.com/hidden'});ctx.fixture.items.push({title:'<img src=x onerror=alert(1)>',source:'<script>alert(1)</script>',sourceType:'뉴스레터',tag:'"<svg onload=alert(1)>',published:null,url:'javascript:alert(1)',status:'검수 대기'});
ctx.fetch=async url=>{calls++;assert.equal(url,'https://raw.githubusercontent.com/leeyoun90-oss/nobrand-b/main/data/trends.json');return {ok:true,json:async()=>ctx.fixture}};
await vm.runInContext('loadCollectedNews()',ctx);assert.equal(calls,1);assert.equal(renders,1);let view=vm.runInContext('collectedNewsSection()',ctx);assert.equal((view.match(/<article class="compact-article collected-card">/g)||[]).length,6);assert.ok(!view.includes('숨겨야 함'));assert.ok(view.includes('항목 11'));
vm.runInContext('collectedLimit=100',ctx);view=vm.runInContext('collectedNewsSection()',ctx);assert.ok(view.includes('&lt;img'));assert.ok(!view.includes('<img src=x'));assert.ok(!view.includes('href="javascript:'));assert.ok(view.includes('target="_blank" rel="noopener noreferrer"'));assert.ok(view.includes('⭐ 1,000'));assert.ok(view.includes('검수 대기'));
for(const [filter,count]of [['github',4],['newsletter',5],['blog',4]]){vm.runInContext('collectedFilter='+JSON.stringify(filter),ctx);assert.equal(vm.runInContext('collectedItems().filter(collectedMatches).length',ctx),count)}
ctx.fetch=async()=>{throw Error('offline')};await vm.runInContext('loadCollectedNews()',ctx);assert.ok(vm.runInContext('collectedNewsSection()',ctx).includes('불러오지 못했어요'));
ctx.fetch=async()=>({ok:true,json:async()=>({items:[]})});await vm.runInContext('loadCollectedNews()',ctx);assert.ok(vm.runInContext('collectedNewsSection()',ctx).includes('표시할 수집 소식이 없어요'));
ctx.fetch=async()=>({ok:true,json:async()=>({items:null})});await vm.runInContext('loadCollectedNews()',ctx);assert.equal(vm.runInContext('collectedState',ctx),'error');
assert.equal((app.match(/\nloadCollectedNews\(\);/g)||[]).length,1);
console.log('PASS: identical index, unchanged avatar/library/storage shape, 6 latest cards, filters, excluded/pending, HTTPS/XSS, KST dates, empty/offline/malformed data.');
