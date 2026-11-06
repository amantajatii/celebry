import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5ioAAAAASUVORK5CYII=', 'base64');
const fixture = { catalogSize: 35, metric: 'cosine_similarity', notice: 'Entertainment only. Similarity is not an identity probability.', matches: Array.from({length:5}, (_, i) => ({rank:i+1,cosineSimilarity:.7-i*.15,celebrity:{id:String(i),name:`Test celebrity ${i+1}`,imageUrl:'https://upload.wikimedia.org/test-celebry-fixture.png',sourceUrl:'https://commons.wikimedia.org/',license:'Test fixture',licenseUrl:null,attribution:'Browser test fixture'}})) };
const headers = { 'access-control-allow-origin': '*' };

async function open(page: Page) {
  await page.route('**/media/celebrities/*.jpg', route => route.fulfill({contentType:'image/png', body:png}));
  await page.goto('/match');
}
async function choose(page: Page) {
  await page.locator('input[type=file]').setInputFiles({name:'fixture.png',mimeType:'image/png',buffer:png});
}
async function agree(page: Page) { await page.getByRole('checkbox').check(); }
async function submit(page: Page) { await page.getByRole('button',{name:'Find my celebrity twin',exact:true}).click(); }
async function success(page: Page) {
  await page.route('**/api/match', route => route.fulfill({json:fixture,headers}));
  await open(page); await choose(page); await agree(page); await submit(page);
  await expect(page.getByRole('heading',{name:'Your star moment.'})).toBeVisible();
}

test('validates uploads and consent before sending anything', async ({page}) => {
  let calls=0;
  await page.route('**/api/match', route => { calls++; return route.abort(); });
  await open(page); await submit(page);
  await expect(page.locator('.upload-card').getByRole('alert')).toHaveText('Choose a photo first.');
  await page.locator('input[type=file]').setInputFiles({name:'invalid.txt',mimeType:'text/plain',buffer:Buffer.from('invalid')});
  await expect(page.locator('.upload-card').getByRole('alert')).toContainText('JPEG, PNG, or WebP');
  await choose(page); await submit(page);
  await expect(page.locator('.upload-card').getByRole('alert')).toContainText('agree to photo analysis');
  await expect(page.getByRole('img',{name:'Your selected selfie preview'})).toBeVisible();
  expect(calls).toBe(0);
  await agree(page);
  await page.getByRole('button',{name:'Remove photo'}).click();
  await expect(page.getByRole('checkbox')).not.toBeChecked();
  await expect(page.getByRole('heading',{name:'Drop your selfie here'})).toBeVisible();
});

test('renders actual API structure, credits, and resets', async ({page}) => {
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  await success(page);
  await expect(page.locator('.match-ranking li')).toHaveCount(5);
  await expect(page.locator('.comparison')).toContainText('CLOSEST OF 35 FACES');
  await expect(page.locator('.rank-score').first()).toHaveText('0.700');
  await page.getByText('Celebrity photo credits',{exact:true}).click();
  await expect(page.locator('.photo-credits a')).toHaveCount(5);
  await expect(page.locator('.photo-credits a').first()).toHaveAttribute('rel','noreferrer');
  await page.getByRole('button',{name:'Try another photo'}).click();
  await expect(page.getByRole('heading',{name:'Drop your selfie here'})).toBeVisible();
  await expect(page.getByRole('checkbox')).not.toBeChecked();
  expect(errors).toEqual([]);
});

for(const [code,message] of [['NO_FACE','No face found'],['MULTIPLE_FACES','more than one face'],['MATCHING_NOT_READY','unavailable right now'],['RATE_LIMITED','wait a minute']]) {
  test(`shows recoverable ${code} feedback`,async({page})=>{
    await page.route('**/api/match',route=>route.fulfill({status:code==='RATE_LIMITED'?429:422,json:{error:{code,message:'server detail'}},headers}));
    await open(page); await choose(page); await agree(page); await submit(page);
    await expect(page.locator('.upload-card').getByRole('alert')).toContainText(message);
    await expect(page.getByRole('button',{name:'Find my celebrity twin',exact:true})).toBeEnabled();
    await expect(page.getByRole('img',{name:'Your selected selfie preview'})).toBeVisible();
  });
}

test('cancels slow requests and ignores stale results', async ({page}) => {
  let release!:()=>void;
  let finish!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve});
  const finished=new Promise<void>(resolve=>{finish=resolve});
  await page.route('**/api/match',async route=>{ await gate; try{await route.fulfill({json:fixture,headers});}catch{}finally{finish();} });
  await open(page); await choose(page); await agree(page); await submit(page);
  await expect(page.getByRole('button',{name:'Cancel request'})).toBeVisible();
  await expect(page.locator('.analysis-status [role=status]')).toContainText('Looking for your famous twin');
  await page.getByRole('button',{name:'Cancel request'}).click();
  await expect(page.getByRole('status')).toContainText('Request cancelled');
  release(); await finished;
  await expect(page.getByRole('heading',{name:'Your star moment.'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Find my celebrity twin',exact:true})).toBeEnabled();
});

test('offers native text sharing without transmitting the selfie',async({page})=>{
  await page.addInitScript(()=>{Object.defineProperty(navigator,'share',{configurable:true,value:async(data:unknown)=>{(window as unknown as {shared:unknown}).shared=data}})});
  await success(page);
  await page.getByRole('button',{name:'Share my results'}).click();
  const shared=await page.evaluate(()=>(window as unknown as {shared:Record<string,unknown>}).shared);
  expect(Object.keys(shared).sort()).toEqual(['text','title']);
  expect(shared.text).toContain('Test celebrity 1');
  expect(shared.text).toContain('0.700');
});

test('copies text when native sharing is unavailable',async({page})=>{
  await page.addInitScript(()=>{Object.defineProperty(navigator,'share',{configurable:true,value:undefined});Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(text:string)=>{(window as unknown as {copied:string}).copied=text}}})});
  await success(page);
  await page.getByRole('button',{name:'Share my results'}).click();
  await expect(page.getByRole('status')).toContainText('Result copied');
  expect(await page.evaluate(()=>(window as unknown as {copied:string}).copied)).toContain('not an identity probability');
});

test('match empty/results states pass WCAG checks and fit the viewport',async({page},testInfo)=>{
  await open(page);
  await page.screenshot({path:testInfo.outputPath('upload-collections.png'),fullPage:true});
  expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations).toEqual([]);
  await success(page);
  expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('results.png'),fullPage:true});
});

test('landing navigation, keyboard focus, reduced motion, and accessibility',async({page},testInfo)=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link',{name:'Skip to content'})).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();
  expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('landing.png'),fullPage:true});
  await page.locator('.hero').getByRole('link',{name:'Find my twin'}).click();
  await expect(page).toHaveURL(/\/match$/);
});

test('real inference returns a reference self-match in the browser',async({page},testInfo)=>{
  test.skip(!process.env.CELEBRY_REAL_BROWSER_TEST,'Requires prepared local model/catalog and running backend');
  await page.goto('/match');
  await page.locator('input[type=file]').setInputFiles('backend/data/hollywood/zendaya.jpg');
  await agree(page);
  const response = page.waitForResponse(response => response.url().endsWith('/api/match') && response.request().method() === 'POST');
  await submit(page);
  const result = await (await response).json();
  await expect(page.getByRole('heading',{name:'Your star moment.'})).toBeVisible();
  await expect(page.locator('.rank-name').first()).toHaveText('Zendaya');
  await expect(page.locator('.rank-score').first()).toHaveText(result.matches[0].cosineSimilarity.toFixed(3));
  await expect(page.locator('.collection-context')).toContainText('3 reference photos');
  await expect(page.locator('.match-ranking li')).toHaveCount(5);
  await page.locator('.match-ranking li').last().scrollIntoViewIfNeeded();
  await expect.poll(()=>page.locator('.comparison img').last().evaluate(image=>(image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await expect.poll(()=>page.locator('.match-ranking img').evaluateAll(images=>images.every(image=>(image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth>0))).toBe(true);
  await page.screenshot({path:testInfo.outputPath('real-inference.png'),fullPage:true});
  await page.getByRole('button',{name:'Try another photo'}).click();
  await page.getByRole('radio',{name:'Actors',exact:true}).check();
  await page.locator('input[type=file]').setInputFiles('backend/data/hollywood/tom-holland.jpg');
  await agree(page);
  const actorResponse=page.waitForResponse(response=>response.url().endsWith('/api/match') && response.request().method()==='POST');
  await submit(page);
  const actors=await (await actorResponse).json();
  expect(actors.catalogSize).toBe(17);
  expect(actors.matches.every((match:{celebrity:{collection:string}})=>match.celebrity.collection==='actors')).toBe(true);
  await expect(page.locator('.rank-name').first()).toHaveText('Tom Holland');
  await expect(page.locator('.collection-context')).toContainText('Actors');
  await page.screenshot({path:testInfo.outputPath('real-actors.png'),fullPage:true});
});


test('selected collection reaches the API and survives trying another photo',async({page})=>{
  const filtered={...fixture,collection:'actors',catalogSize:17,matches:fixture.matches.map(match=>({...match,celebrity:{...match.celebrity,collection:'actors'}}))};
  let body='';
  await page.route('**/api/match',route=>{body=route.request().postData()||'';return route.fulfill({json:filtered,headers})});
  await open(page);
  await page.getByRole('radio',{name:'Actors',exact:true}).check();
  await choose(page); await agree(page); await submit(page);
  await expect(page.locator('.collection-context')).toContainText('Actors');
  await expect(page.locator('.comparison')).toContainText('CLOSEST OF 17 FACES');
  expect(body).toContain('name="collection"\r\n\r\nactors');
  await page.getByRole('button',{name:'Try another photo'}).click();
  await expect(page.getByRole('radio',{name:'Actors',exact:true})).toBeChecked();
});
