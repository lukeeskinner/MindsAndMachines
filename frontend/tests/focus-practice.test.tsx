// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../src/App';
import type { ConceptEstimate, CoachContext } from '../../contracts/api';
vi.mock('../src/components/course/CourseContext', async () => {
  const actual = await vi.importActual('../src/components/course/CourseContext');
  return {...actual, useCourseLabels: () => ({ course: {
    course_id:'course',title:'Source course',concepts:[{concept_id:'chain',display_name:'Composition'}],source_filenames:['notes.pdf'],question_count:4,
  },title:'Source course',names:{chain:'Composition'},conceptName:()=> 'Composition'})};
});
const before: ConceptEstimate = {concept_id:'chain',alpha:1,beta:5,mean:1/6,interval90:{lower:.01,upper:.45},evidence_count:4};
const after: ConceptEstimate = {...before,alpha:2,mean:2/7,evidence_count:5,interval90:{lower:.06,upper:.58}};
const analytics = (c:ConceptEstimate, complete=false):CoachContext => ({session_complete:complete,session_kind:'focus',focus_ranking:[{concept_id:'chain',concept_name:'Composition',focus_priority:.5,mastery_mean:c.mean,interval90:c.interval90,evidence_count:c.evidence_count,unseen_questions:1,reasons:['low_mastery']}]});
const q={question_id:'q1',concept_id:'chain',prompt:'Original source question',choices:[{id:'a',text:'Source response'},{id:'unsure',text:'Unsure'}]};
const response=(body:unknown)=>({ok:true,json:async()=>body});
let mock=vi.fn();
beforeEach(()=>{window.sessionStorage.clear(); Element.prototype.scrollIntoView=vi.fn();vi.spyOn(window,'scrollTo').mockImplementation(()=>{});mock=vi.fn();vi.stubGlobal('fetch',mock)});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()});
it('starts trusted focus from chat, continues plotted Beta state, and preserves it through flashcards and retake',async()=>{
  const session={session_id:'s1',course_id:'course',question:q,concepts:[before],session_start:[before],question_count:4,flashcards:[{card_id:'card',concept_id:'chain',front:'Composition',back:'Source notes',source:'notes.pdf'}],analytics:analytics(before)};
  mock.mockResolvedValueOnce(response(session));
  render(<App/>);const user=userEvent.setup();await screen.findByRole('radio',{name:'Source response'});
  await user.click(screen.getByRole('tab',{name:'Chatbot',exact:true}));
  mock.mockResolvedValueOnce(response({session_id:'s1',message:'Give me more practice on my weakest concept.',text:'Composition needs more practice.',teaching_source:'bedrock',practice_concept_id:'chain',analytics:analytics(before)}));
  await user.click(screen.getByRole('button',{name:'Give me more practice on my weakest concept.',exact:true}));
  expect((screen.getByRole('textbox',{name:'Your message'}) as HTMLTextAreaElement).value).toBe('Give me more practice on my weakest concept.');
  // Older browser engines provide AbortController but no AbortSignal.timeout.
  vi.stubGlobal('AbortSignal', {});
  await user.click(screen.getByRole('button',{name:'Send',exact:true}));
  const action=await screen.findByRole('button',{name:'Practice this concept',exact:true});
  expect(mock.mock.calls[1][0]).toBe('/api/v1/chat');
  expect(screen.queryByRole('alert')).toBeNull();
  mock.mockResolvedValueOnce(response({...session,session_id:'f1',question:{...q,question_id:'fresh',prompt:'Fresh focus question'},question_count:1,session_kind:'focus',focus_concept_id:'chain',practice_notice:'1 fresh question. Your existing learner model continues.'}));
  await user.click(action);await screen.findByText('Fresh focus question');
  expect(JSON.parse(mock.mock.calls[2][1].body)).toEqual({session_id:'s1',concept_id:'chain'});
  expect(mock.mock.calls[2][0]).toBe('/api/v1/focus-practice');
  expect(within(screen.getByRole('region',{name:'Focus practice progress'})).getByRole('img').getAttribute('aria-label')).toContain('Beta(1, 5)');
  mock.mockResolvedValueOnce(response({session_id:'f1',assessment:{outcome:'correct',misconception_id:null,feedback:'Correct'},concepts:[after],decision:null,tutor:{text:'Set complete',fallback:false,teaching_source:'authored'},next_question:null,mode:'dummy',provider:'fake',trace:['assess','update','select','teach'],session_start:[before],analytics:analytics(after,true),counts:{submitted_answers:1,unique_questions_seen:1,accepted_observations:1,focus_observations:1,lifetime_evidence:5}}));
  await user.click(screen.getByRole('radio',{name:'Source response'}));await user.click(screen.getByRole('button',{name:'Check answer'}));
  await screen.findByRole('region',{name:'What changed?'});
  const plot=within(screen.getByRole('region',{name:'What changed?'})).getByRole('img');
  expect(plot.getAttribute('aria-label')).toContain('Beta(2, 5)');expect(plot.innerHTML).not.toMatch(/NaN|Infinity/);
  expect(screen.getByText(/16.7% → 28.6%/)).toBeTruthy();
  await user.click(screen.getByRole('button',{name:'Flashcards',exact:true}));
  expect(screen.getByRole('region',{name:'Flashcard study'})).toBeTruthy();expect(mock).toHaveBeenCalledTimes(4);
  await user.click(screen.getByRole('button',{name:'Practice quiz',exact:true}));
  await user.click(screen.getByRole('tab',{name:'Chatbot',exact:true}));
  expect(within(screen.getByRole('region',{name:'Practice priorities'})).getByText(/28.6% estimate/)).toBeTruthy();
  await user.click(screen.getByRole('tab',{name:'Study desk',exact:true}));
  await user.click(screen.getByRole('button',{name:'Session recap',exact:true}));
  mock.mockResolvedValueOnce(response({...session,session_id:'again',concepts:[after],session_start:[after],analytics:analytics(after)}));
  await user.click(screen.getByRole('button',{name:'Practice again',exact:true}));
  await screen.findByRole('radio',{name:'Source response'});
  expect(JSON.parse(mock.mock.calls[4][1].body).previous_session_id).toBe('f1');
  expect(screen.queryByRole('region',{name:'Focus practice progress'})).toBeNull();
  expect(screen.getAllByRole('img',{name:/Beta\(2, 5\)/}).length).toBeGreaterThan(0);
  const prior={...before,alpha:1,beta:1,mean:.5,evidence_count:0,interval90:{lower:.05,upper:.95}};
  mock.mockResolvedValueOnce(response({...session,session_id:'reset',concepts:[prior],session_start:[prior],analytics:analytics(prior)}));
  await user.click(screen.getByRole('button',{name:'Reset learner profile',exact:true}));
  await user.click(screen.getByRole('button',{name:'Erase evidence and restart',exact:true}));
  await screen.findByRole('radio',{name:'Source response'});
  expect(JSON.parse(mock.mock.calls[5][1].body).reset_learner).toBe(true);
  expect(screen.getAllByRole('img',{name:/Beta\(1, 1\)/}).length).toBeGreaterThan(0);
}, 15000);

it('starts the recommended focus directly from the server ID without a chat request, and permits retry after a real failure',async()=>{
  const session={session_id:'s1',course_id:'course',question:q,concepts:[before],analytics:analytics(before)};
  mock.mockResolvedValueOnce(response(session));
  render(<App/>); const user=userEvent.setup(); await screen.findByRole('radio',{name:'Source response'});
  await user.click(screen.getByRole('tab',{name:'Chatbot',exact:true}));
  const action=screen.getByRole('button',{name:'Start Composition focus set',exact:true});
  mock.mockResolvedValueOnce({ok:false,status:503});
  await user.click(action); await screen.findByRole('alert');
  expect(JSON.parse(mock.mock.calls[1][1].body)).toEqual({session_id:'s1',concept_id:'chain'});
  mock.mockResolvedValueOnce(response({...session,session_id:'focus',session_kind:'focus',focus_concept_id:'chain',question:{...q,prompt:'Fresh retry'}}));
  await user.click(action); await screen.findByText('Fresh retry');
  expect(mock.mock.calls.map(c=>c[0])).toEqual(['/api/v1/sessions','/api/v1/focus-practice','/api/v1/focus-practice']);
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getAllByRole('img',{name:/Beta\(1, 5\)/}).length).toBeGreaterThan(0);
});
