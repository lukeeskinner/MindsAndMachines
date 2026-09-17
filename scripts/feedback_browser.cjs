// Optional live audit: start make dev first. Requires Playwright + Chrome and
// pdftotext. PLAYWRIGHT_MODULE can point to an existing external installation.
// Uses only public browser responses and the synthetic Calculus source PDF.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const pdf = path.join(root, 'backend/tests/ingestion/fixtures/calculus_derivatives_mini_lecture.pdf');
const dir = process.env.AUDIT_DIR || '/tmp/minds-feedback-audit';
fs.mkdirSync(dir, {recursive: true});
const save = (name, data) => fs.writeFileSync(path.join(dir, `${name}.json`), JSON.stringify(data, null, 2));
const normalize = s => s.toLowerCase().normalize('NFKC').replace(/\s+/g, ' ').trim();
const source = normalize(execFileSync('pdftotext', ['-enc', 'UTF-8', '-nopgbrk', pdf, '-'], {encoding: 'utf8'}));
const pct = n => `${(n * 100).toFixed(1)}%`;

(async () => {
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
  const errors = [], badResponses = [], requests = [], turns = [], sessions = [];
  const layoutChecks = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('response', r => { if (r.status() >= 400) badResponses.push({url: r.url(), status: r.status()}); });
  page.on('request', r => { if (r.url().includes('/api/')) requests.push({path: new URL(r.url()).pathname, body: r.postData()}); });
  const button = name => page.getByRole('button', {name, exact: true});
  const pending = route => page.waitForResponse(r => r.url().endsWith(`/api/v1/${route}`) && r.request().method() === 'POST', {timeout: 125000});
  async function postClick(route, action, status = 200) {
    const [response] = await Promise.all([pending(route), action()]);
    const data = await response.json();
    assert.equal(response.status(), status, JSON.stringify(data));
    return data;
  }
  async function layout(width, name) {
    await page.setViewportSize({width, height: 1000});
    await page.locator('.study-surface').scrollIntoViewIfNeeded();
    const sizes = await page.evaluate(() => {
      const graph = document.querySelector('.impact-chart svg')?.getBoundingClientRect();
      const surface = document.querySelector('.study-surface').getBoundingClientRect();
      const next = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Continue')?.getBoundingClientRect();
      return {scroll: document.documentElement.scrollWidth, width: innerWidth,
        graph: graph && {left: graph.left, right: graph.right, height: graph.height},
        surface: {left: surface.left, right: surface.right, height: surface.height},
        next: next && {left: next.left, right: next.right}};
    });
    assert(sizes.scroll <= sizes.width + 1, `Horizontal overflow at ${width}: ${JSON.stringify(sizes)}`);
    assert(sizes.graph && sizes.graph.height > 90 && sizes.graph.left >= 0 && sizes.graph.right <= width);
    assert(sizes.next && sizes.next.left >= 0 && sizes.next.right <= width);
    layoutChecks.push({name, ...sizes});
    await page.screenshot({path: path.join(dir, `${name}.png`), fullPage: true});
  }
  async function inspectFeedback(result, q, before, screenshots = false) {
    const impact = page.getByRole('region', {name: 'What changed?', exact: true});
    await impact.waitFor();
    const after = result.concepts.find(c => c.concept_id === q.concept_id);
    const old = before.find(c => c.concept_id === q.concept_id);
    assert.equal(await impact.getByRole('img').getAttribute('aria-label'), `Beta(${after.alpha}, ${after.beta}); mean ${pct(after.mean)}; 90% interval ${pct(after.interval90.lower)} to ${pct(after.interval90.upper)}; ${after.evidence_count} observations.`);
    assert.equal(await impact.locator('.impact-values strong').innerText(), pct(after.mean));
    assert((await impact.innerText()).includes(`${after.evidence_count} ${after.evidence_count === 1 ? 'observation' : 'observations'}`));
    assert.equal(await button('See model details').getAttribute('aria-expanded'), 'false');
    assert.equal(await page.getByRole('table').count(), 0);
    assert.equal(await page.locator('.study-surface').getByRole('img').count(), 1);
    const feedback = page.locator('.feedback-explanation');
    assert.equal(await feedback.innerText(), Array.from(new Intl.Segmenter('en', {granularity: 'sentence'}).segment(result.tutor.text)).map(s => s.segment.trim()).filter(Boolean).slice(0, 3).join(' '));
    assert(await button(result.next_question ? 'Continue' : 'Session recap').isVisible());
    if (screenshots) {
      await layout(1440, 'feedback-desktop');
      await layout(768, 'feedback-tablet');
      await layout(390, 'feedback-mobile');
      await layout(320, 'feedback-narrow');
      await page.setViewportSize({width: 1440, height: 1000});
    }
    const count = requests.length;
    await button('See model details').focus();
    await page.keyboard.press('Enter');
    assert.equal(await button('See model details').getAttribute('aria-expanded'), 'true');
    const details = page.getByRole('region', {name: 'Model comparison'});
    await details.waitFor();
    for (const [label, a, b] of [
      ['Estimate', pct(old.mean), pct(after.mean)],
      ['Observations', String(old.evidence_count), String(after.evidence_count)],
      ['Beta parameters (α, β)', `${old.alpha}, ${old.beta}`, `${after.alpha}, ${after.beta}`],
      ['90% uncertainty range', `${pct(old.interval90.lower)} – ${pct(old.interval90.upper)}`, `${pct(after.interval90.lower)} – ${pct(after.interval90.upper)}`],
      ['Interval width', `${((old.interval90.upper-old.interval90.lower)*100).toFixed(1)} pp`, `${((after.interval90.upper-after.interval90.lower)*100).toFixed(1)} pp`],
    ]) assert.deepEqual(await details.getByRole('row', {name: `${label} ${a} ${b}`, exact: true}).getByRole('cell').allTextContents(), [a,b]);
    if (result.decision) assert(await details.getByText(result.decision.reason, {exact: true}).isVisible());
    if (screenshots) await page.screenshot({path: path.join(dir, 'model-details.png'), fullPage: true});
    await button('See model details').focus(); await page.keyboard.press('Space');
    assert.equal(await button('See model details').getAttribute('aria-expanded'), 'false');
    assert.equal(requests.length, count, 'Inspecting model details made a request');
  }
  async function answer(session, q, before, outcome, screenshots = false) {
    await page.getByRole('group', {name: q.prompt, exact: true}).waitFor();
    assert.equal(await page.locator('input[name=answer]:checked').count(), 0);
    assert.equal(await page.getByRole('region', {name: 'What changed?', exact: true}).count(), 0);
    assert(await button('Check answer').isDisabled());
    const choice = outcome === 'unclear' ? q.choices.find(c => c.id === 'unsure')
      : q.choices.find(c => c.id !== 'unsure' && source.includes(normalize(c.text)) === (outcome === 'correct'));
    assert(choice, `No ${outcome} answer identifiable in public source: ${JSON.stringify(q)}`);
    await page.getByRole('radio', {name: choice.text, exact: true}).check();
    const result = await postClick('turns', () => button('Check answer').click());
    assert.equal(result.session_id, session.session_id);
    assert.equal(result.assessment.outcome, outcome);
    assert.deepEqual(result.trace, ['assess', 'update', 'select', 'teach']);
    const accepted = outcome !== 'unclear' && !q.review;
    for (const old of before) {
      const current = result.concepts.find(c => c.concept_id === old.concept_id);
      if (old.concept_id !== q.concept_id || !accepted) assert.deepEqual(current, old);
      else {
        assert.equal(current.alpha, old.alpha + (outcome === 'correct' ? 1 : 0));
        assert.equal(current.beta, old.beta + (outcome === 'incorrect' ? 1 : 0));
        assert.equal(current.evidence_count, old.evidence_count + 1);
        assert.equal(current.mean, current.alpha / (current.alpha + current.beta));
      }
    }
    turns.push({session: session.session_id, question: q, outcome, before, result}); save('turns', turns);
    await inspectFeedback(result, q, before, screenshots);
    console.log(`TURN ${turns.length}: ${outcome}, ${q.review ? 'review' : 'fresh'}, ${result.tutor.teaching_source}`);
    return result;
  }
  async function continueTo(result) {
    await button(result.next_question ? 'Continue' : 'Session recap').click();
    if (result.next_question) await page.getByRole('group', {name: result.next_question.prompt, exact: true}).waitFor();
  }
  async function chat(session, analytics) {
    await page.getByRole('tab', {name: 'Chatbot', exact: true}).click();
    await page.getByRole('textbox', {name: 'Your message', exact: true}).fill('How did I do, and what should I focus on next?');
    const data = await postClick('chat', () => button('Send').click());
    save('chat', data);
    assert.equal(data.session_id, session.session_id);
    assert(['bedrock', 'authored'].includes(data.teaching_source));
    for (const c of analytics.focus_ranking) {
      assert(data.text.includes(`${pct(c.mastery_mean)} estimate`));
      assert(data.text.includes(`${c.evidence_count} accepted observations`));
      assert(data.text.includes(`${pct(c.interval90.lower)}–${pct(c.interval90.upper)}`));
    }
    assert.deepEqual(data.analytics, analytics);
    assert(data.text.length > 40);
    await page.getByRole('region', {name: 'Study conversation'}).getByText(data.text.split(/\n\s*\n/)[0], {exact: true}).waitFor();
    await page.screenshot({path: path.join(dir, 'chat.png'), fullPage: true});
    return data;
  }
  try {
    await page.goto(process.env.AUDIT_URL || 'http://127.0.0.1:5173/');
    let course, session;
    if (process.env.AUDIT_EXISTING_COURSE_JSON) {
      // Recovery audit only: mount the real product with metadata from a
      // previously successful live upload. No API requests are intercepted.
      // This explicitly does NOT verify a fresh upload or the sign-in/setup UI.
      course = JSON.parse(fs.readFileSync(process.env.AUDIT_EXISTING_COURSE_JSON, 'utf8'));
      session = await postClick('sessions', () => page.evaluate(async metadata => {
        const React = (await import('/node_modules/.vite/deps/react.js')).default;
        const {createRoot} = (await import('/node_modules/.vite/deps/react-dom_client.js')).default;
        const {App} = await import('/src/App.tsx');
        const {CourseProvider, useCourse} = await import('/src/components/course/CourseContext.tsx');
        document.getElementById('root').hidden = true;
        const target = document.createElement('div'); document.body.append(target);
        function SelectedCourse() {
          const controller = useCourse();
          React.useEffect(() => { controller.selectCourse(metadata); }, []);
          return controller.selectedCourse ? React.createElement(App) : null;
        }
        createRoot(target).render(React.createElement(CourseProvider, null, React.createElement(SelectedCourse)));
      }, course), 201);
    } else {
    await page.getByLabel('Email', {exact: true}).fill('demo@example.test');
    await page.getByLabel('Password', {exact: true}).fill('synthetic-demo');
    await button('Continue to setup').click();
    await page.getByLabel('Course name', {exact: true}).fill('Calculus feedback audit');
    await page.locator('input[type=file]').setInputFiles(pdf);
    course = await postClick('courses', () => button('Upload course').click(), 201);
    session = await postClick('sessions', () => button('Activate course').click(), 201);
    }
    save('course', course);
    assert.equal(course.concepts.length, 4); assert(course.question_count >= 12);
    sessions.push(session); save('sessions', sessions);
    assert.equal(session.course_id, course.course_id);
    assert(session.concepts.every(c => c.alpha === 1 && c.beta === 1 && c.mean === .5 && c.evidence_count === 0));
    assert.deepEqual(session.session_start, session.concepts);
    console.log(`COURSE ${process.env.AUDIT_EXISTING_COURSE_JSON ? 'REUSED (upload unverified)' : '201'} / SESSION 201: ${course.concepts.length} concepts, ${course.question_count} pool questions`);
    let q = session.question, before = session.concepts, result, count = 0;
    const seen = new Set(), perConcept = {};
    while (q) {
      assert(!seen.has(q.question_id)); seen.add(q.question_id); count++;
      assert(count <= session.question_count);
      perConcept[q.concept_id] = (perConcept[q.concept_id] || 0) + 1;
      const outcome = count === 1 ? 'incorrect' : count === 3 ? 'unclear' : 'correct';
      result = await answer(session, q, before, outcome, count === 1);
      if (count === 1) {
        assert.equal(result.next_question.concept_id, q.concept_id);
        assert.notEqual(result.next_question.question_id, q.question_id);
        assert.equal(result.flashcards[0].concept_id, q.concept_id);
      }
      await continueTo(result); q = result.next_question; before = result.concepts;
    }
    assert(Object.values(perConcept).every(n => n >= 3));
    assert.equal(Object.keys(perConcept).length, 4);
    const recap = page.getByRole('region', {name: 'Returned concept changes'});
    await recap.waitFor(); assert.equal(await recap.getByRole('img').count(), 4);
    assert((await recap.innerText()).includes('90% interval'));
    assert((await recap.innerText()).includes('Observations:'));
    await page.getByRole('region', {name: 'Practice priorities'}).waitFor();
    await page.screenshot({path: path.join(dir, 'completion.png'), fullPage: true});
    const diagnostic = result; save('diagnostic', diagnostic);
    const coaching = await chat(session, result.analytics);
    const ranking = result.analytics.focus_ranking;
    const top = ranking[0];
    session = await postClick('focus-practice', () => button(`Start ${top.concept_name} focus set`).click(), 201);
    sessions.push(session); save('sessions', sessions);
    assert.equal(session.focus_concept_id, top.concept_id);
    assert.equal(session.session_kind, 'focus');
    assert.deepEqual(session.concepts, diagnostic.concepts);
    assert.deepEqual(session.session_start, diagnostic.concepts);
    await page.getByRole('region', {name: 'Focus practice progress'}).waitFor();
    q = session.question; before = session.concepts; let focusCount = 0, freshFocus = 0;
    while (q) {
      focusCount++; assert(focusCount <= 3);
      assert.equal(q.concept_id, top.concept_id);
      if (!q.review) { freshFocus++; assert(!seen.has(q.question_id)); }
      result = await answer(session, q, before, 'correct');
      await continueTo(result); q = result.next_question; before = result.concepts;
    }
    assert(freshFocus > 0, 'No fresh focus evidence available in this live run');
    assert(result.counts.focus_observations > 0);
    assert.notDeepEqual(result.analytics.focus_ranking, diagnostic.analytics.focus_ranking);
    save('focus', result);
    await page.screenshot({path: path.join(dir, 'focus-completion.png'), fullPage: true});
    await button('Flashcards').click();
    const cards = page.getByRole('region', {name: 'Flashcard study'}); await cards.waitFor();
    const first = result.flashcards[0];
    assert((await cards.innerText()).includes(first.front));
    // Flashcards retain authored order for tied priorities; focus ranking uses
    // question availability as a tie-break. Compare the returned priorities.
    assert.equal(result.analytics.focus_ranking.find(c => c.concept_id === first.concept_id).focus_priority,
      result.analytics.focus_ranking[0].focus_priority);
    const requestCount = requests.length;
    await button('Show answer').click(); await page.getByRole('region', {name: 'Card answer'}).waitFor();
    await page.screenshot({path: path.join(dir, 'flashcards.png'), fullPage: true});
    await button('Review again').click(); await button('Next card').click(); await button('Previous card').click();
    assert.equal(requests.length, requestCount);
    await page.getByRole('tab', {name: 'Chatbot', exact: true}).click();
    await page.getByRole('region', {name: 'Practice priorities'}).waitFor();
    await page.getByRole('tab', {name: 'Study desk', exact: true}).click();
    await cards.waitFor(); await button('Practice quiz').click();
    const again = await postClick('sessions', () => button('Practice again').click(), 201);
    assert.deepEqual(again.concepts, result.concepts);
    assert.deepEqual(again.session_start, result.concepts);
    sessions.push(again); save('sessions', sessions);
    await button('Reset learner profile').click();
    assert.equal(requests.length, requestCount + 1, 'Reset happened before confirmation');
    const reset = await postClick('sessions', () => button('Erase evidence and restart').click(), 201);
    assert(reset.concepts.every(c => c.alpha === 1 && c.beta === 1 && c.mean === .5 && c.evidence_count === 0));
    sessions.push(reset); save('sessions', sessions);
    await page.getByRole('group', {name: reset.question.prompt, exact: true}).waitFor();
    assert.equal(await page.getByRole('region', {name: 'What changed?', exact: true}).count(), 0);
    assert.deepEqual(errors, []); assert.deepEqual(badResponses, []);
    const summary = {passed: true, freshUpload: !process.env.AUDIT_EXISTING_COURSE_JSON, diagnosticQuestions: count, perConcept, focusQuestions: focusCount, freshFocus,
      acceptedDiagnostic: diagnostic.counts.accepted_observations, focusObservations: result.counts.focus_observations,
      focusRankChanged: diagnostic.analytics.focus_ranking[0].concept_id !== result.analytics.focus_ranking[0].concept_id,
      chatbot: coaching.teaching_source, practiceAgain: 'preserved', reset: 'Beta(1,1)', layoutChecks, errors, badResponses};
    save('summary', summary); console.log('PASS', JSON.stringify(summary));
  } catch (error) {
    await page.screenshot({path: path.join(dir, 'failure.png'), fullPage: true});
    save('failure', {message: error.message, stack: error.stack, body: await page.locator('body').innerText(), errors, badResponses});
    console.error(error); process.exitCode = 1;
  } finally { save('requests', requests); await browser.close(); }
})();
