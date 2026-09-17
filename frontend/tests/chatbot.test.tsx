// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../src/App";
import fixture from "../../contracts/fixtures/turn_response.json";
const question = { question_id: "q1", concept_id: fixture.concepts[0].concept_id,
  prompt: "Practice question", choices: [{id:"a",text:"Option A"}] };
const initial = {session_id:"s1",course_id:null,question,concepts:fixture.concepts};
const response = {session_id:"s1",message:"Explain the concept",text:"A grounded explanation.",teaching_source:"bedrock"};
const ok = (body: unknown) => ({ok:true,json:async()=>body});
afterEach(()=>{cleanup();vi.unstubAllGlobals()});

it("sends session-only context, prevents duplicate requests and preserves conversation across navigation", async()=>{
 let release!: (value:unknown)=>void;
 const fetch = vi.fn().mockResolvedValueOnce(ok(initial)).mockImplementationOnce(()=>new Promise(resolve=>{release=resolve}));
 vi.stubGlobal("fetch",fetch);
 const user=userEvent.setup();render(<App/>);await screen.findByRole("radio");
 await user.click(screen.getByRole("tab",{name:"Chatbot",exact:true}));
 await user.type(screen.getByRole("textbox",{name:"Your message"}),response.message);
 await user.click(screen.getByRole("button",{name:"Send",exact:true}));
 expect((screen.getByRole("button",{name:"Send"}) as HTMLButtonElement).disabled).toBe(true);
 expect((screen.getByRole("button",{name:"New practice session"}) as HTMLButtonElement).disabled).toBe(true);
 await user.click(screen.getByRole("button",{name:"Send"}));
 expect(fetch).toHaveBeenCalledTimes(2);
 expect(fetch.mock.calls[1][0]).toBe("/api/v1/chat");
 expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({session_id:"s1",message:response.message,
  presentation_preferences:{plain_language:false,step_by_step:false,concise:false}});
 release(ok(response));await screen.findByText(response.text);
 expect((screen.getByRole("textbox",{name:"Your message"}) as HTMLTextAreaElement).value).toBe("");
 await user.click(screen.getByRole("tab",{name:"Study desk",exact:true}));
 await user.click(screen.getByRole("tab",{name:"Chatbot",exact:true}));
 expect(screen.getByText(response.text)).toBeTruthy();
 fetch.mockResolvedValueOnce(ok({...initial,session_id:"s2"}));
 await user.click(screen.getByRole("button",{name:"New practice session"}));
 await screen.findByRole("radio");await user.click(screen.getByRole("tab",{name:"Chatbot",exact:true}));
 expect(screen.queryByText(response.text)).toBeNull();
});

it("keeps a failed draft for retry and never renders an untrusted mismatched response",async()=>{
 const fetch=vi.fn().mockResolvedValueOnce(ok(initial)).mockResolvedValueOnce({ok:false,status:503})
  .mockResolvedValueOnce(ok({...response,session_id:"foreign"})).mockResolvedValueOnce(ok(response));
 vi.stubGlobal("fetch",fetch);const user=userEvent.setup();render(<App/>);await screen.findByRole("radio");
 await user.click(screen.getByRole("tab",{name:"Chatbot",exact:true}));
 await user.type(screen.getByRole("textbox",{name:"Your message"}),response.message);
 await user.click(screen.getByRole("button",{name:"Send"}));await screen.findByRole("alert");
 expect((screen.getByRole("textbox",{name:"Your message"}) as HTMLTextAreaElement).value).toBe(response.message);
 await user.click(screen.getByRole("button",{name:"Send"}));
 await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(3));
 expect(screen.queryByText(response.text)).toBeNull();
 await user.click(screen.getByRole("button",{name:"Send"}));await screen.findByText(response.text);
 expect(screen.queryByRole("alert")).toBeNull();
});
