import test from 'node:test';
import assert from 'node:assert/strict';
import {intervalText, matchesRecord, otherNames} from '../web/app.mjs';

const operator = {
  repeat: true,
  licences: [{regulator:'licensing'}],
  actions: [
    {regulator:'agency', id:'event-a', case_id:'case-A', eligible:true},
    {regulator:'agency', id:'event-b', case_id:'case-A', eligible:true},
    {regulator:'agency', id:'proposal', case_id:'case-B', eligible:false},
    {regulator:'other', id:'event-z', eligible:true},
  ],
  foreign:[{action:{regulator:'agency'}, licence:{regulator:'licensing'}}],
};

test('record filters distinguish issuing regulator from action issuer', () => {
  assert.equal(matchesRecord(operator,'licences','agency'), false);
  assert.equal(matchesRecord(operator,'actions','agency'), true);
  assert.equal(matchesRecord(operator,'foreign','licensing'), true);
  assert.equal(matchesRecord(operator,'foreign','other'), false);
});

test('a repeat requires distinct eligible cases when scoped to one regulator', () => {
  assert.equal(matchesRecord(operator,'repeat'), true);
  assert.equal(matchesRecord(operator,'repeat','agency'), false);
  const added = {...operator, actions:[...operator.actions,{regulator:'agency',id:'event-c',eligible:true}]};
  assert.equal(matchesRecord(added,'repeat','agency'), true);
});

test('documented intervals retain a zero-day case and distinguish missing data', () => {
  assert.match(intervalText([]), /No documented interval/);
  assert.equal(intervalText([{days:0}]), '0 days (one documented case interval)');
  assert.equal(intervalText([{days:15},{days:4},{days:3},{days:8}]), '6 days median across 4 documented intervals');
  assert.match(intervalText([{days:null},{days:-1}]), /No documented interval/);
});

test('record names and domains remain searchable aliases of the labelled legal entity', () => {
  const entity = {name:'Parent Ltd.', identity:{names:['Parent Ltd.', 'Parent Limited']},
    licences:[{entity:'Parent Ltd.', name:'Example Brand', domains:['example.test']}],
    actions:[{entity:'Parent Limited', title:'Case about a different company'}]};
  assert.deepEqual(otherNames(entity), ['Parent Limited', 'Example Brand', 'example.test']);
});
