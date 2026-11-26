// Compare the browser and server daily generator across dates and categories.
const fs = require('node:fs');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const assert = require('node:assert/strict');
const ctx = vm.createContext({document:{addEventListener(){}}});
let src = fs.readFileSync('app.js','utf8').replace(/init\(\);\s*$/, '');
vm.runInContext(src,ctx);
const data = fs.readFileSync('data/pokedex.json','utf8');
vm.runInContext(`DATA=${data};POKE=DATA.pokemon;WORDS=Math.ceil(POKE.length/32);
const megaSpecies=new Set(POKE.filter(p=>p.mega).map(p=>p.dex));
for(const p of POKE){p.moveSet=new Set(p.moves);p.hasMega=megaSpecies.has(p.dex);p.homeRegion=homeRegion(p);}
CATS=buildCategories();POOL=CATS.filter(c=>c.n>=8);`,ctx);
const days = Array.from({length:30},(_,i)=>'2026-09-'+String(i+1).padStart(2,'0'));
const expected = JSON.parse(execFileSync(process.env.PYTHON || 'python', ['-c',
  `import json,daily;print(json.dumps([daily.puzzle(d) for d in ${JSON.stringify(days)}]))`],{encoding:'utf8'}));
for (let i=0;i<days.length;i++) {
  const result = vm.runInContext(`JSON.stringify((()=>{const g=generateGrid(hashStr('pokegrid-${days[i]}'));return {rows:g.rows.map(c=>CATS.indexOf(c)),cols:g.cols.map(c=>CATS.indexOf(c))};})())`,ctx);
  assert.deepEqual(JSON.parse(result),expected[i],days[i]);
}
console.log('Browser/server puzzle parity passed for 30 daily grids.');
