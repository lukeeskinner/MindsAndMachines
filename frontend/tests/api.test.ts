import { afterEach, expect, it, vi } from 'vitest';
import { post } from '../src/lib/api';
import { createCourseUploadAdapter } from '../src/lib/courses';

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('sends chat and focus requests without AbortSignal.timeout', async () => {
  vi.stubGlobal('AbortSignal', {});
  const fetch = vi.fn().mockResolvedValue({ok:true,json:async()=>({accepted:true})});
  vi.stubGlobal('fetch', fetch);
  for (const path of ['chat', 'focus-practice']) {
    await expect(post(path, {session_id:'existing',concept_id:'opaque-id'})).resolves.toEqual({accepted:true});
  }
  expect(fetch.mock.calls.map(c=>c[0])).toEqual(['/api/v1/chat','/api/v1/focus-practice']);
  expect(fetch.mock.calls.every(c=>c[1].signal.aborted === false)).toBe(true);
});

it('keeps the upload timeout compatible too', async () => {
  vi.stubGlobal('AbortSignal', {});
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,status:201,json:async()=>({
    course_id:'course',title:'Course',concepts:[{concept_id:'id',display_name:'Concept'}],
    source_filenames:['notes.pdf'],question_count:3,
  })}));
  await expect(createCourseUploadAdapter().upload([])).resolves.toMatchObject({status:'ready'});
});

it('aborts at the deadline, reports timeout, and clears the timer', async () => {
  vi.useFakeTimers();
  vi.spyOn(console,'warn').mockImplementation(()=>{});
  vi.stubGlobal('fetch', vi.fn((_url, {signal})=>new Promise((_resolve,reject)=>{
    signal.addEventListener('abort',()=>reject(new Error('private transport detail')));
  })));
  const result = expect(post('chat', {})).rejects.toThrow('The request timed out');
  await vi.advanceTimersByTimeAsync(20000);
  await result;
  expect(vi.getTimerCount()).toBe(0);
});

it('keeps the deadline through body parsing and clears it after success', async () => {
  vi.useFakeTimers();
  let finish!: (data:object)=>void;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:()=>new Promise(resolve=>{finish=resolve;})}));
  const result=post('chat',{});
  await vi.advanceTimersByTimeAsync(0);
  expect(vi.getTimerCount()).toBe(1);
  finish({text:'ready'});
  await expect(result).resolves.toEqual({text:'ready'});
  expect(vi.getTimerCount()).toBe(0);
});

it('distinguishes preparation, network, HTTP, and malformed-response failures without logging private data', async () => {
  const warn=vi.spyOn(console,'warn').mockImplementation(()=>{});
  const fetch=vi.fn(); vi.stubGlobal('fetch',fetch);
  const circular: {self?:unknown}={}; circular.self=circular;
  await expect(post('chat',circular)).rejects.toThrow('could not be prepared');
  expect(fetch).not.toHaveBeenCalled();
  fetch.mockRejectedValueOnce(new Error('secret network data'));
  await expect(post('chat',{})).rejects.toThrow('Could not reach');
  fetch.mockResolvedValueOnce({ok:false,status:503});
  await expect(post('chat',{})).rejects.toThrow('tutor is temporarily unavailable');
  fetch.mockResolvedValueOnce({ok:true,json:async()=>{throw new Error('private response');}});
  await expect(post('chat',{})).rejects.toThrow('invalid response');
  expect(warn.mock.calls).toEqual(['prepare','request','http','response'].map(reason=>[
    'learning_request_failed',{path:'chat',reason},
  ]));
});
