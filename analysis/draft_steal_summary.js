// Each steal variant vs no steal (replay_current.json), per league, and how often the waited-on player lasted.
//   node analysis/draft_steal_summary.js <dir with replay_*.json>
const fs=require('fs');const DIR=process.argv[2]||'.';const R=v=>JSON.parse(fs.readFileSync(`${DIR}/replay_${v}.json`));
const base=R('current');const D=['538977698','1854297225','1503540199'];
for(const v of ['steal','commit','logit','logitcommit','page'].filter(v=>fs.existsSync(`${DIR}/replay_${v}.json`))){const r=R(v);
 const d=r.map((x,i)=>x.v-base[i].v);const per={};r.forEach((x,i)=>(per[x.lg]=per[x.lg]||[]).push(d[i]));
 const m=a=>a.reduce((s,x)=>s+x,0)/a.length;
 const ev=r.flatMap(x=>x.events);const withL=ev.filter(e=>e.lasted!=null);
 const bins=[[0,.5],[.5,.7],[.7,.9],[.9,1.01]].map(([a,b])=>{const g=withL.filter(e=>e.p>=a&&e.p<b);return g.length?`${a}-${b}: n=${g.length} pred ${m(g.map(e=>e.p)).toFixed(2)} lasted ${m(g.map(e=>+e.lasted)).toFixed(2)}`:''}).filter(Boolean);
 console.log(v,'mean',m(d).toFixed(3),'design',m(d.filter((_,i)=>D.includes(r[i].lg))).toFixed(3),'test',m(d.filter((_,i)=>!D.includes(r[i].lg))).toFixed(3),
  'better',d.filter(x=>x>1e-9).length,'worse',d.filter(x=>x<-1e-9).length,'| per lg',Object.values(per).map(a=>m(a).toFixed(2)).join(' '));
 console.log('   steals',ev.length,'lasted',withL.filter(e=>e.lasted).length,'took',ev.filter(e=>e.took).length,'| mean p',m(ev.map(e=>e.p)).toFixed(2),'|',bins.join(' | '));}
