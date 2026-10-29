import { test } from 'node:test';
import assert from 'node:assert/strict';
import {calendarDays, calendarEvents, eventLanes} from '../src/calendarModel.ts';
import type {Work} from '../src/taskModels.ts';
const work=(schedule:Work['schedule'],state='active'):Work=>({id:'one',title:'Plan',objective:'Compare',success_criteria:'Done',state,source:'manual',updated_at:1,schedule,runs:[]});
test('month has six Monday-first weeks across year boundary',()=>{
 const days=calendarDays(new Date(2026,0,1),'month');assert.equal(days.length,42);assert.equal(days[0].getDay(),1);assert.equal(days[0].getFullYear(),2025);
});
test('unscheduled work never invents an appointment',()=>{
 assert.deepEqual(calendarEvents([work({mode:'now',timezone:'UTC'})],calendarDays(new Date(2026,0,1),'month')),[]);
});
test('recurrence uses schedule timezone and actual occurrence replaces projection',()=>{
 const days=calendarDays(new Date(2026,9,29),'week');const t=work({mode:'daily',timezone:'Asia/Shanghai',time:'09:00'});
 const now=new Date('2026-10-25T00:00:00Z');let events=calendarEvents([t],days,now);assert.ok(events.length>0);assert.ok(events.every(e=>e.date.getUTCHours()===1));
 t.runs=[{id:'run',due_at:events[0].date.getTime()/1000,status:'succeeded'} as Work['runs'][number]];
 events=calendarEvents([t],days,now);assert.equal(events.filter(e=>e.date.getTime()===t.runs[0].due_at*1000).length,1);assert.equal(events[0].projected,false);
});
test('paused recurrence has no speculative future work and invalid zone stays safe',()=>{
 const days=calendarDays(new Date(2026,9,29),'week');assert.equal(calendarEvents([work({mode:'daily',timezone:'UTC',time:'09:00'},'paused')],days,new Date(0)).length,0);
 assert.equal(calendarEvents([work({mode:'daily',timezone:'invalid-zone',time:'09:00'})],days,new Date(0)).length,0);
});
test('DST gap is skipped rather than displaying a fabricated time',()=>{
 const days=calendarDays(new Date(2026,2,8),'week');const events=calendarEvents([work({mode:'daily',timezone:'America/New_York',time:'02:30'})],days,new Date('2026-03-01'));
 assert.ok(events.every(e=>e.date.toISOString()!=='2026-03-08T07:30:00.000Z'));
});
test('chained collisions share one stable lane group',()=>{
 const task=work({mode:'once',timezone:'UTC'});const values=[0,20,40].map((m)=>({id:String(m),task,date:new Date(2026,0,1,9,m),status:'scheduled',projected:false}));
 assert.deepEqual(eventLanes(values,72).map(v=>[v.lane,v.lanes]),[[0,3],[1,3],[2,3]]);
});
