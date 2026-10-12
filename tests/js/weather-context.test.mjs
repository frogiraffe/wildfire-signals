import test from 'node:test';
import assert from 'node:assert/strict';
import {parseNwsGrid, fetchNwsWeather} from '../../public/weather-context.mjs';

const START = '2026-10-12T00:00:00Z';
const value = (unit, values) => ({uom:unit,values});
const span = (validTime, amount) => ({validTime,value:amount});
const GRID = {properties:{updateTime:START,validTimes:`${START}/P7D`,
  windSpeed:value('wmoUnit:km_h-1',[span(`${START}/PT6H`,20),span('2026-10-12T06:00:00Z/PT6H',40)]),
  windDirection:value('wmoUnit:degree_(angle)',[span(`${START}/P1D`,270)]),
  windGust:value('wmoUnit:km_h-1',[span(`${START}/P1D`,60)]),
  temperature:value('wmoUnit:degC',[span(`${START}/P1D`,30)]),
  relativeHumidity:value('wmoUnit:percent',[span(`${START}/P1D`,25)]),
  quantitativePrecipitation:value('wmoUnit:mm',[
    span(`${START}/PT6H`,0),span('2026-10-12T06:00:00Z/PT6H',3)])}};

test('NWS grid forecast keeps each valid interval, unit and source update time', () => {
  const parsed = parseNwsGrid(GRID,new Date('2026-10-12T00:30:00Z'));
  assert.equal(parsed.updatedAt,START);
  assert.equal(parsed.rows[0].windKmh,20);
  assert.equal(parsed.rows[0].gustKmh,60);
  assert.equal(parsed.rows[0].directionDeg,270);
  assert.equal(parsed.rows[0].temperatureC,30);
  assert.equal(parsed.rows[0].humidityPercent,25);
  assert.deepEqual(parsed.rows[0].validity.windKmh,
    {start:START,end:'2026-10-12T06:00:00.000Z'});
  assert.deepEqual(parsed.rows[0].validity.gustKmh,
    {start:START,end:'2026-10-13T00:00:00.000Z'});
  assert.deepEqual(parsed.rows[0].rain,{mm:0,start:START,end:'2026-10-12T06:00:00.000Z'});
  assert.equal(parsed.rows[1].windKmh,40);
  assert.deepEqual(parsed.rows[1].rain,
    {mm:3,start:'2026-10-12T06:00:00Z',end:'2026-10-12T12:00:00.000Z'});
  assert.equal(parsed.rows[3].rain,null);
});

test('unknown units and missing values remain unknown, not zero', () => {
  const grid = structuredClone(GRID);
  grid.properties.windSpeed.uom = 'wmoUnit:kn';
  grid.properties.relativeHumidity.values[0].value = null;
  const parsed = parseNwsGrid(grid,new Date('2026-10-12T00:30:00Z'));
  assert.equal(parsed.rows[0].windKmh,null);
  assert.equal(parsed.rows[0].humidityPercent,null);
  assert.equal(parsed.rows[0].rain.mm,0);
});

test('physically invalid weather values are omitted', () => {
  const grid = structuredClone(GRID);
  grid.properties.windSpeed.values[0].value = -30;
  grid.properties.windDirection.values[0].value = 400;
  grid.properties.windGust.values[0].value = -1;
  grid.properties.relativeHumidity.values[0].value = 150;
  grid.properties.quantitativePrecipitation.values[0].value = -4;
  const row = parseNwsGrid(grid,new Date('2026-10-12T00:30:00Z')).rows[0];
  assert.equal(row.windKmh,null);
  assert.equal(row.directionDeg,null);
  assert.equal(row.gustKmh,null);
  assert.equal(row.humidityPercent,null);
  assert.equal(row.rain,null);
});

test('weather retrieval accepts only NWS grid URLs and records receipt time', async () => {
  const calls = [];
  const fakeFetch = async url => {
    calls.push(url);
    return {ok:true,status:200,text:async () => JSON.stringify(calls.length === 1
      ? {properties:{forecastGridData:'https://api.weather.gov/gridpoints/TOP/32,81'}} : GRID)};
  };
  const result = await fetchNwsWeather(39.7,-97.1,{fetchImpl:fakeFetch,
    now:() => new Date('2026-10-12T00:30:00Z')});
  assert.equal(calls.length,2);
  assert.equal(result.sourceUrl,calls[1]);
  assert.equal(result.receivedAt,'2026-10-12T00:30:00.000Z');
  const hostile = async () => ({ok:true,status:200,text:async () => JSON.stringify(
    {properties:{forecastGridData:'https://attacker.example/grid'}})});
  await assert.rejects(fetchNwsWeather(39.7,-97.1,{fetchImpl:hostile}),/NWS grid URL/);
});

test('unsupported location fails without inventing weather and older source is marked stale', async () => {
  let calls = 0;
  const unavailable = async () => {calls++;return {ok:false,status:404};};
  await assert.rejects(fetchNwsWeather(52,-115,{fetchImpl:unavailable}),/NWS HTTP 404/);
  assert.equal(calls,1);
  const old = parseNwsGrid(GRID,new Date('2026-10-12T13:00:00Z'));
  assert.equal(old.stale,true);
  assert.equal(old.rows[3].rain,null);
});
