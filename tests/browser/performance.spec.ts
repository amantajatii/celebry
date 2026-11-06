import { test, expect } from '@playwright/test';

test('production landing stays within lab loading budgets', async ({page},testInfo)=>{
  test.skip(!process.env.CELEBRY_PERFORMANCE_TEST,'Run against a production server, not Next dev');
  await page.addInitScript(()=>{
    const state={lcp:0,cls:0};
    (window as unknown as {lab:typeof state}).lab=state;
    new PerformanceObserver(list=>{for(const entry of list.getEntries())state.lcp=entry.startTime;}).observe({type:'largest-contentful-paint',buffered:true});
    new PerformanceObserver(list=>{for(const entry of list.getEntries()){const item=entry as PerformanceEntry & {hadRecentInput:boolean;value:number};if(!item.hadRecentInput)state.cls+=item.value;}}).observe({type:'layout-shift',buffered:true});
  });
  await page.goto('/',{waitUntil:'networkidle'});
  await page.evaluate(()=>document.fonts.ready);
  await expect(page.locator('.hero-photo img')).toBeVisible();
  await expect.poll(()=>page.locator('.hero-photo img').evaluate(image=>(image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  const metrics=await page.evaluate(()=>({
    ...(window as unknown as {lab:{lcp:number;cls:number}}).lab,
    scriptBytes:performance.getEntriesByType('resource').filter(e=>(e as PerformanceResourceTiming).initiatorType==='script').reduce((sum,e)=>sum+(e as PerformanceResourceTiming).encodedBodySize,0),
    viewport:window.innerWidth,
  }));
  console.log(testInfo.project.name,JSON.stringify(metrics));
  await testInfo.attach('lab-performance.json',{body:JSON.stringify(metrics,null,2),contentType:'application/json'});
  expect(metrics.lcp).toBeGreaterThan(0);
  expect(metrics.lcp).toBeLessThan(2500);
  expect(metrics.cls).toBeLessThanOrEqual(.1);
  expect(metrics.scriptBytes).toBeLessThan(500_000);
});
