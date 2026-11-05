'use strict';
const $=id=>document.getElementById(id), esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let backend=false, alertsAvailable=true, devices=[], chosen='pi-lab',tick=0, events=[],faults={},previous={},lastFrame=null;
const names=[['pi-lab','Raspberry Pi · Lab','Raspberry Pi demo','RP'],['jetson-lab','Jetson · Vision','Jetson demo','JX'],['linux-lab','Linux · Gateway','Linux demo','LX']];
const log=(message)=>{events.unshift({at:new Date().toLocaleTimeString('en-GB'),message});events=events.slice(0,50)};
function status(d,now){if(now-d.last_seen>12)return'offline';if(d.temperature!==null&&d.temperature>=80)return'hot';if(d.cpu>=90||d.memory>=90)return'busy';return'healthy'}
function stepDemo(){const now=Date.now()/1000;devices=names.map(([id,name,platform,icon],i)=>{let d=devices.find(d=>d.device_id===id)||{device_id:id,name,platform,mode:'simulated',history:[],last_seen:now,icon};if(faults[id]!=='pause'){d.cpu=+(32+i*13+12*Math.sin(tick/4+i)).toFixed(1);d.memory=42+i*12;d.temperature=faults[id]==='heat'?88:+(46+i*7+4*Math.sin(tick/8)).toFixed(1);d.last_seen=now;d.uptime=tick*3;d.sequence=tick;d.history.push({cpu:d.cpu,received:now});d.history=d.history.slice(-120)}d.age=Math.max(0,now-d.last_seen);d.state=status(d,now);return d});tick++;render()}

function showAlerts(items,note){
  const list=$('alert-list');
  $('alert-count').textContent=items.length+' active';
  $('alerts-note').textContent=note;
  list.innerHTML=items.length?items.map(a=>`<div class="alert-item"><span class="alert-severity ${esc(a.severity)}">${esc(a.severity.toUpperCase())}</span><div><strong>${esc(a.device_name)}</strong><p>${esc(a.message)}</p><small>${esc(a.kind)} · ${a.mode==='simulated'?'SIMULATED':'MEASURED'}</small></div></div>`).join(''):'<p class="alert-empty">No active alerts.</p>';
}
function localAlerts(){
  return devices.flatMap(d=>{
    const base={device_name:d.name,mode:d.mode};
    if(d.state==='offline')return [{...base,kind:'offline',severity:'critical',message:'Device has stopped reporting telemetry'}];
    const out=[];
    if(d.temperature!==null&&d.temperature>=80)out.push({...base,kind:'temperature',severity:'critical',message:'Temperature is at or above 80 C'});
    for(const k of ['cpu','memory'])if(d[k]>=90)out.push({...base,kind:k,severity:'warning',message:k.toUpperCase()+' utilization is at or above 90%'});
    return out;
  });
}
async function pollAlerts(){
  try{
    const r=await fetch('/api/alerts',{cache:'no-store'});
    if(!r.ok)throw Error(r.status===401?'Authentication required':'Alert service unavailable');
    const data=await r.json();
    showAlerts(data.alerts,'Live backend snapshot · no incident history or notifications.');
  }catch(e){showAlerts([],e.message+' · alerts unavailable (not zero).');}
}
function render(){const ids=devices.map(d=>d.device_id),sel=$('device-select');if(!ids.includes(chosen))chosen=ids[0]||'';sel.innerHTML=devices.map(d=>`<option value="${esc(d.device_id)}" ${d.device_id===chosen?'selected':''}>${esc(d.name)}</option>`).join('');$('online').textContent=devices.filter(d=>d.state!=='offline').length;$('total').textContent=` / ${devices.length}`;let active=devices.filter(d=>d.state!=='offline');$('avg').textContent=active.length?(active.reduce((s,d)=>s+d.cpu,0)/active.length).toFixed(1)+'%':'—';$('hot').textContent=active.filter(d=>d.state==='hot').length;document.querySelector('.count').textContent=devices.length;
$('cards').innerHTML=devices.map(d=>{let demo=d.mode==='simulated';if(previous[d.device_id]&&previous[d.device_id]!==d.state)log(`${d.name}: ${previous[d.device_id]} → ${d.state}${demo?' (simulated)':''}`);previous[d.device_id]=d.state;return `<article class="device ${d.device_id===chosen?'selected':''}"><div class="device-top"><div class="chip">${esc(d.icon||d.platform.slice(0,2).toUpperCase())}</div><span class="badge ${esc(d.state)}">${esc(d.state.toUpperCase())}</span></div><h3>${esc(d.name)}</h3><div class="platform">${esc(d.platform)} · ${demo?'SIMULATED':'MEASURED'}</div><div class="metric"><span>CPU utilization</span><strong>${d.cpu.toFixed(1)}%</strong></div><div class="bar"><span style="width:${d.cpu}%"></span></div><div class="metric"><span>Memory</span><strong>${d.memory.toFixed(1)}%</strong></div><div class="metric"><span>Temperature</span><strong>${d.temperature===null?'unavailable':d.temperature.toFixed(1)+'°C'}</strong></div><div class="device-bottom">${demo?['normal','heat','pause'].map(f=>`<button data-device="${esc(d.device_id)}" data-fault="${f}" class="${(faults[d.device_id]||'normal')===f?'on':''}" aria-label="${f} fault on ${esc(d.name)}">${{normal:'↻ Normal',heat:'♨ Heat',pause:'Ⅱ Link'}[f]}</button>`).join(''):'<span class="mini">READ-ONLY AGENT</span>'}</div><div class="age">Last sample ${Math.floor(d.age)}s ago ${faults[d.device_id]==='pause'?'· link paused':''}</div></article>`}).join('');let d=devices.find(d=>d.device_id===chosen);if(d){$('chart-name').textContent=d.name+' · CPU';let h=d.history.slice(-60),points=h.map((p,i)=>[(i/(Math.max(1,h.length-1))*640).toFixed(1),(185-p.cpu*1.8).toFixed(1)]);let path=points.length?'M'+points.map(p=>p.join(',')).join(' L'):'';$('line').setAttribute('d',path);$('fill').setAttribute('d',path?path+' L640,190 L0,190 Z':'');$('trace-note').textContent=`${h.length} ${d.mode==='simulated'?'SYNTHETIC':'RECEIVED'} SAMPLES`}
$('event-list').innerHTML=events.map(e=>`<div class="event"><time>${esc(e.at)}</time><span>${esc(e.message)}</span></div>`).join('');$('clock').textContent=new Date().toLocaleTimeString('en-GB')+' LOCAL';if(!backend)showAlerts(localAlerts(),'Browser simulation only · no physical devices connected.');lastFrame={mode:backend?'local_backend':'browser_simulation',captured_at:new Date().toISOString(),devices};}
$('cards').addEventListener('click',async event=>{const b=event.target.closest('button[data-fault]');if(!b)return;const id=b.dataset.device,f=b.dataset.fault;try{if(backend){const r=await fetch(`/api/demo/${encodeURIComponent(id)}/${f}`,{method:'POST'});if(!r.ok)throw Error('Control rejected')}faults[id]=f;log(`${names.find(n=>n[0]===id)?.[1]||id}: ${f==='heat'?'thermal fault injected':f==='pause'?'simulated link paused':'normal operation restored'}`);if(!backend)stepDemo();}catch(e){log(e.message);render()}});
$('device-select').onchange=e=>{chosen=e.target.value;render()};
for(const id of ['connect','guide'])$(id).onclick=()=>$('setup').showModal();for(const id of ['close','understood'])$(id).onclick=()=>$('setup').close();
$('export').onclick=()=>{if(!lastFrame)return;const a=document.createElement('a'),u=URL.createObjectURL(new Blob([JSON.stringify(lastFrame,null,2)],{type:'application/json'}));a.href=u;a.download='edgepulse-snapshot.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
async function poll(){try{const r=await fetch('/api/fleet',{cache:'no-store'});if(!r.ok)throw Error('Backend unavailable');const data=await r.json();devices=data.devices;$('mode-note').textContent='Received telemetry · demo cards remain explicitly marked simulated.';render()}catch(e){$('mode-note').textContent='Backend unavailable. Showing stale last-known samples.';log('Backend disconnected. Last samples retained; no new measurements.');devices.forEach(d=>{d.state='offline'});render()}}
(async()=>{try{const r=await fetch('/api/status',{signal:AbortSignal.timeout(2000)});if(r.ok&&(await r.json()).service==='edgepulse')backend=true}catch{}if(backend){$('mode').textContent='LOCAL BACKEND';$('mode-note').textContent='Received telemetry · demo cards remain explicitly marked simulated.';log('Local telemetry service connected.');await poll();await pollAlerts();setInterval(async()=>{await poll();await pollAlerts()},2000)}else{$('mode').textContent='BROWSER SIMULATION';$('mode-note').textContent='Synthetic telemetry. No Raspberry Pi, Jetson or other physical device is connected.';log('Browser simulation started. No physical devices connected.');for(let i=0;i<20;i++)stepDemo();setInterval(stepDemo,3000)}})();
