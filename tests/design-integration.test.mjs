import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const html=fs.readFileSync('index.html','utf8');
const app=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
const feature=app.slice(app.indexOf('// Reference design assets'),app.indexOf('const AVATAR_IMAGES='));
let clock='2026-11-30T14:59:59Z';
class TestDate extends Date{constructor(...args){super(...(args.length?args:[clock]));}}
const ctx=vm.createContext({Date:TestDate,Intl,setInterval:()=>0,state:{profile:{level:2},attempts:[]},levels:['트렌드 자연인','트렌드 눈팅족','트렌드 탑승족','트렌드 민감족','트렌드 선도족','트렌드 창조자'],C:{monthly:()=>3},esc:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))});
vm.runInContext(feature,ctx);
assert.equal(vm.runInContext('DESIGN_LEVELS.length',ctx),6);
for(let level=1;level<=6;level++){
 const image=vm.runInContext('designCharacter('+level+')',ctx);
 assert.ok(image.includes('data:image/webp;base64,'));
 assert.ok(image.includes('alt="Lv'+level+' '));
}
assert.equal(vm.runInContext('designCountdown()',ctx),'D-0 00:00:01');
clock='2026-11-30T15:00:00Z';
assert.equal(vm.runInContext('designCountdown()',ctx),'D-31 00:00:00');
vm.runInContext('designPicked=6',ctx);
const hero=vm.runInContext('designHomeHero()',ctx);
assert.ok(hero.includes('Lv6 트렌드 창조자 트민두 캐릭터'));
assert.ok(hero.includes('Lv.2 트렌드 눈팅족'));
assert.equal(ctx.state.profile.level,2,'Preview must not change actual level');
assert.ok(!hero.includes('{{'),'All design bindings resolve');
assert.ok(!hero.includes('<sc-'),'No reference-only custom components remain');
assert.ok(hero.includes('href="#study"'),'Article quiz opens the existing study flow');
assert.ok(hero.includes('href="#level-test"'),'Assessment remains accessible');
assert.equal((hero.match(/data-tmd-slide=/g)||[]).length,3);
assert.equal((vm.runInContext('designLevelCatalog()',ctx).match(/data-design-level=/g)||[]).length,6);
assert.ok(app.includes("'level-test':levelTestPage"),'Remote assessment route retained');
assert.ok(app.includes('state.profile.level=Math.max(state.profile.level,assigned)'),'Assessment cannot demote existing users');
assert.ok(app.includes("if(look==='auto')return designCharacter(state.profile.level,cls)"),'Automatic character follows real level');
assert.ok(app.includes("const allowed=['base','jacket','spark']"),'Existing custom looks retained');
console.log('PASS: six reference characters, independent preview, KST month boundary, resolved hero, assessment route and existing custom looks.');
