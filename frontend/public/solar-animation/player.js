"use strict";
// Deterministic, local-only animatic. No model API, network fetch, or TTS is used.
const scenes = [
  {name:"一个问题",duration:9,sub:["太阳活跃，地球会立刻受影响吗？","有的几分钟，有的要几天"],voice:"太阳离我们那么远，突然变得活跃，地球会立刻受影响吗？有的影响几分钟就到，有的要等几天。",note:"这里是传播过程的演示，不是针对某次事件的风险预报。",sources:["S-SW-003"]},
  {name:"三位信使",duration:12,sub:["光、粒子、物质云团","不同速度，也有不同影响","一次事件不一定三者都有"],voice:"把它们想成三位信使：光、高速粒子，还有太阳抛出的物质云团。它们不同速，也不一定一起出发。",note:"信使和跑道是比喻，不代表真实形状或准确的速度比例。",sources:["S-SW-003","S-SW-005"]},
  {name:"光先到",duration:14,sub:["约8分钟：从太阳出发算起","向阳一侧的高层大气受到扰动","部分短波通信可能听不清"],voice:"第一位是耀斑发出的辐射，像光一样快。约八分钟后到达地球，可能让向阳一侧的部分短波通信听不清。",note:"不是看到耀斑后还有8分钟准备时间；也不代表所有手机和网络中断。",sources:["S-SW-001","S-SW-003"]},
  {name:"粒子随后",duration:12,sub:["粒子通常几十分钟到数小时抵达","卫星、航天员需要留意","地面与太空的风险不能混为一谈"],voice:"接着是高速粒子，通常几十分钟到数小时。它们主要让卫星、航天员和部分高纬度航班多加留意。",note:"时间随粒子与事件条件变化；图中的提示牌不是实体保护盾。",sources:["S-SW-003","S-SW-008","S-SW-002"]},
  {name:"云团更慢",duration:17,sub:["太阳物质云团：约18小时到数天","要先看是否朝向地球","速度和磁场方向也很重要","强耀斑，不一定有强地磁暴"],voice:"物质云团更慢，大约十八小时到数天。是否朝向地球、速度和磁场方向，都影响它的作用。强耀斑不一定造成强地磁暴。",note:"云团是携带磁场的等离子体，不是水汽云；到达不代表一定导致故障。",sources:["S-SW-003","S-SW-004","S-SW-005"]},
  {name:"持续监测",duration:10,sub:["持续观察，评估风险","预警帮助相关系统准备"],voice:"科学家持续观察太阳和近地环境。监测与预警，帮助相关系统评估风险、做准备。",note:"预警有不确定性；并非所有影响都能提前准确预测。",sources:["S-SW-003"]},
  {name:"记住三问",duration:10,sub:["是谁？多久到？影响什么？","分清三种信使，不必过度恐慌"],voice:"记住三个问题：是谁，多久到，影响什么？分清三种信使，才能理解太阳带来的不同影响。",note:"本片为无旁白的代码动画分镜；字幕时间仅用于节奏预演。",sources:["S-SW-001","S-SW-003","S-SW-005"]},
];
let cumulative=0;
scenes.forEach(s=>{s.start=cumulative;cumulative+=s.duration;});
const total=cumulative, canvas=document.querySelector("#canvas"), ctx=canvas.getContext("2d");
const seek=document.querySelector("#seek"), play=document.querySelector("#play");
const colors={yellow:"#ffdc78",orange:"#ff9d69",cyan:"#61d7d0",white:"#eff5fc",dim:"#a4bbcc"};
const clamp=(n,a=0,b=1)=>Math.max(a,Math.min(b,n));
const smooth=n=>{const x=clamp(n);return x*x*(3-2*x);};
function circle(x,y,r,color){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();}
function line(x,y,a,b,color,width=3){ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(a,b);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.lineCap="round";ctx.stroke();}
function box(x,y,w,h,color,r=16){ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fillStyle=color;ctx.fill();}
function text(t,x,y,size=24,color=colors.white,align="center"){ctx.font=`600 ${size}px 'Microsoft YaHei', sans-serif`;ctx.fillStyle=color;ctx.textAlign=align;ctx.fillText(t,x,y);}
function face(x,y,r){circle(x-r*.23,y-r*.06,r*.06,"#173b48");circle(x+r*.23,y-r*.06,r*.06,"#173b48");ctx.beginPath();ctx.arc(x,y+r*.10,r*.23,0,Math.PI);ctx.strokeStyle="#173b48";ctx.lineWidth=3;ctx.stroke();}
function sun(x,y,r,t){for(let i=0;i<12;i++){const a=i*Math.PI/6+t*.06;line(x+Math.cos(a)*r*1.2,y+Math.sin(a)*r*1.2,x+Math.cos(a)*r*1.40,y+Math.sin(a)*r*1.40,"#df994d",6);}circle(x,y,r+10,"#ffba5514");circle(x,y,r,colors.yellow);face(x,y,r);}
function earth(x,y,r,t,lit=false){circle(x,y,r+12,lit?"#ffe6a14a":"#60dbdf16");circle(x,y,r,"#4b9ee1");ctx.save();ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.clip();ctx.fillStyle="#68c8a3";ctx.beginPath();ctx.moveTo(x-r,y-r*.6);ctx.lineTo(x-r*.2,y-r*.8);ctx.lineTo(x+r*.1,y-r*.3);ctx.lineTo(x-r*.4,y+r*.2);ctx.lineTo(x-r*.55,y+r*.7);ctx.lineTo(x-r,y+r*.5);ctx.fill();ctx.beginPath();ctx.ellipse(x+r*.6,y+r*.5,r*.3,r*.5,-.6,0,Math.PI*2);ctx.fill();ctx.fillStyle="#071e3c44";ctx.fillRect(x+4,y-r,r,r*2);ctx.restore();face(x,y,r);if(lit){ctx.beginPath();ctx.arc(x,y,r+13,Math.PI*.6,Math.PI*1.4);ctx.strokeStyle=colors.yellow;ctx.lineWidth=6;ctx.stroke();}}
function light(x,y,scale=1){for(let i=0;i<3;i++)line(x-90*scale-i*12,y+(i-1)*12*scale,x-20*scale,y+(i-1)*12*scale,colors.yellow,4);ctx.fillStyle=colors.yellow;ctx.beginPath();ctx.moveTo(x,y-22*scale);ctx.lineTo(x-12*scale,y+2*scale);ctx.lineTo(x,y+2*scale);ctx.lineTo(x-7*scale,y+23*scale);ctx.lineTo(x+20*scale,y-8*scale);ctx.lineTo(x+5*scale,y-8*scale);ctx.closePath();ctx.fill();}
function particles(x,y,t,scale=1){for(let i=0;i<9;i++){circle(x-(i%3)*22*scale,y+(Math.floor(i/3)-1)*18*scale+Math.sin(t*2+i)*3,5*scale,colors.orange);}}
function cloud(x,y,t,scale=1){for(let i=0;i<5;i++){circle(x+(i-2)*19*scale,y+Math.sin(i*2+t*.3)*10*scale,(23+(i%2)*7)*scale,colors.cyan);}face(x,y,24*scale);}
function satellite(x,y,t,scale=1){ctx.save();ctx.translate(x,y);ctx.rotate(Math.sin(t)*.07);ctx.scale(scale,scale);box(-105,-24,64,48,"#488aa9",4);box(41,-24,64,48,"#488aa9",4);for(let i=0;i<3;i++){line(-100+i*20,-22,-100+i*20,22,"#8ed5dc",1);line(45+i*20,-22,45+i*20,22,"#8ed5dc",1);}line(-100,0,100,0,"#bbd7e2",3);box(-26,-32,52,64,"#d3e2ea",10);circle(0,-2,11,"#f5c362");line(15,-30,34,-58,"#d3e2ea",4);circle(34,-60,5,"#f5c362");ctx.restore();}
function radio(x,y,t,active=false){box(x-65,y-45,130,90,"#e8ded0");box(x-49,y-26,58,46,"#31485e",8);for(let i=0;i<4;i++)line(x-42,y-18+i*10,x+1,y-18+i*10,"#739bab",2);circle(x+37,y-5,10,"#a76746");line(x+34,y-45,x+55,y-80,"#e8ded0",4);if(active)for(let i=0;i<3;i++)line(x+73+i*8,y-30+(Math.sin(t*6+i)*12),x+79+i*8,y-15+(Math.cos(t*6+i)*12),colors.orange,3);}
function lane(y,color){line(245,y,754,y,color+"44",3);for(let x=260;x<750;x+=38)line(x,y+26,x+16,y+26,"#26465b",2);}
function background(index,t){ctx.fillStyle="#0d2238";ctx.fillRect(0,0,960,540);for(let i=0;i<65;i++){const x=(i*127+73)%960,y=(i*89+21)%540;circle(x,y,i%5===0?1.7:.8,"#ffffff"+(i%3===0?"42":"1d"));}text("SOLAR MESSENGERS  /  卡通动态分镜",38,38,13,"#84aebc","left");text(`${String(index+1).padStart(2,"0")} / 07`,922,38,13,colors.dim,"right");text(scenes[index].name,480,88,31);text("示意不按比例 · 无旁白样片",922,516,12,colors.dim,"right");}
function draw(time){const index=sceneAt(time),s=scenes[index],p=clamp((time-s.start)/s.duration);background(index,time);
  if(index===0){sun(230,280,77,time);earth(727,280,80,time);text("太阳那边发生的事……",230,422,24,colors.yellow);text("地球何时会有感觉？",720,422,24,colors.cyan);for(let i=0;i<3;i++){const x=370+((p*150+i*65)%230);circle(x,280,4+i,"#f8d981"+(i===0?"dd":"66"));}text("?",480,229,70,colors.white);}
  if(index===1||index===6){const ys=[193,311,430];for(let i=0;i<3;i++){const color=[colors.yellow,colors.orange,colors.cyan][i];lane(ys[i],color);text(["光（辐射）","高速粒子","物质云团"][i],142,ys[i]+8,24,color);const move=clamp((p*(i===0?2.4:i===1?1.5:1)))*340;const x=350+move;if(i===0)light(x,ys[i],.7);if(i===1)particles(x,ys[i],time,.8);if(i===2)cloud(x,ys[i],time,.8);text(["约8分钟","几十分钟到数小时","约18小时到数天"][i],830,ys[i]+8,i===0?24:18,color);} }
  if(index===2){sun(155,264,60,time);earth(732,264,85,time,p>.56);const x=260+smooth(p/.65)*390;light(x,262);text("从太阳出发 → 到达地球",459,155,24,colors.yellow);text("约8分钟",463,204,38,colors.yellow);radio(747,431,time,p>.57);text("向阳一侧",731,381,18,colors.yellow);text("短波通信可能受影响",382,428,23);text("不是全球网络一起断开",382,463,17,colors.dim);}
  if(index===3){sun(137,248,53,time);particles(240+smooth(p/.75)*345,244,time,1.35);satellite(715,244,time,1.15);text("几十分钟到数小时",470,149,33,colors.orange);earth(215,423,43,time);text("地面与太空的风险不同",478,438,24);if(p>.52){box(632,341,180,46,"#624339",12);text("关注粒子风险",722,371,20,colors.orange);} }
  if(index===4){sun(116,239,48,time);cloud(238+smooth(p/.75)*315,242,time,1.4);earth(786,239,69,time);text("约18小时到数天",475,147,32,colors.cyan);const titles=["朝向地球？","速度如何？","磁场方向？"];titles.forEach((a,i)=>{const show=p>.15+i*.18;box(165+i*220,363,200,67,show?"#205358":"#142f43");text(a,265+i*220,405,22,show?colors.cyan:colors.dim);});text("共同决定影响，不是实体闸门",480,470,18,colors.dim);}
  if(index===5){sun(124,254,51,time);satellite(388,251,time,.7);box(635,198,203,125,"#286072");box(649,212,175,94,"#102e47",8);line(736,325,736,355,"#bfdce4",9);line(697,355,775,355,"#bfdce4",7);for(let i=0;i<3;i++){const v=(p*3+i*.3)%1;circle(461+v*171,251,4,colors.cyan);}line(670,260,695,239,colors.cyan,3);line(695,239,720,270,colors.cyan,3);line(720,270,751,231,colors.cyan,3);line(751,231,799,253,colors.cyan,3);text("观测太阳",128,400,23);text("传回数据",392,400,23);text("评估与预警",738,400,23);}
}
function sceneAt(time){const index=scenes.findIndex(s=>time<s.start+s.duration);return index<0?scenes.length-1:index;}
let position=0,playing=false,lastTick=0,currentScene=-1;
function stamp(n){return `${Math.floor(n/60)}:${String(Math.floor(n%60)).padStart(2,"0")}`;}
function sync(){const i=sceneAt(position),s=scenes[i],p=clamp((position-s.start)/s.duration);draw(position);document.querySelector("#caption").textContent=s.sub[Math.min(s.sub.length-1,Math.floor(p*s.sub.length))];seek.value=position.toFixed(2);document.querySelector("#clock").textContent=`${stamp(position)} / ${stamp(total)}`;document.querySelector("#prev").disabled=i===0;document.querySelector("#next").disabled=i===scenes.length-1;
  if(i!==currentScene){currentScene=i;document.querySelector("#scene-number").textContent=`SCENE ${i+1} · ${s.duration}秒 · ${s.sources.join(" / ")}`;document.querySelector("#scene-title").textContent=s.name;document.querySelector("#narration").textContent="旁白待配音稿："+s.voice;document.querySelector("#boundary").textContent=s.note;document.querySelectorAll("#chapters button").forEach((b,j)=>{if(j===i)b.setAttribute("aria-current","step");else b.removeAttribute("aria-current");});}}
function setPlaying(value){playing=value;play.textContent=value?"暂停":"播放";play.setAttribute("aria-pressed",String(value));lastTick=0;}
function jump(i){position=scenes[clamp(i,0,scenes.length-1)].start;sync();}
play.addEventListener("click",()=>{if(position>=total)position=0;setPlaying(!playing);sync();});seek.addEventListener("input",()=>{position=Number(seek.value);sync();});document.querySelector("#prev").addEventListener("click",()=>jump(sceneAt(position)-1));document.querySelector("#next").addEventListener("click",()=>jump(sceneAt(position)+1));
scenes.forEach((s,i)=>{const b=document.createElement("button");b.textContent=`${i+1}. ${s.name}`;b.type="button";b.addEventListener("click",()=>jump(i));document.querySelector("#chapters").appendChild(b);});
document.addEventListener("visibilitychange",()=>{if(document.hidden)setPlaying(false);});
function tick(now){if(playing){if(lastTick)position=Math.min(total,position+(now-lastTick)/1000);if(position>=total)setPlaying(false);sync();}lastTick=now;requestAnimationFrame(tick);}
// Time query supports deterministic QA screenshots without auto-playing.
const requested=Number(new URLSearchParams(location.search).get("t")||0);position=Number.isFinite(requested)?clamp(requested,0,total):0;sync();setPlaying(false);requestAnimationFrame(tick);
