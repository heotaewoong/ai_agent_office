import {test, expect, type Page} from "@playwright/test";
import {readFileSync} from "node:fs";

const doc=JSON.parse(readFileSync(new URL("../../../backend/config/architecture.json",import.meta.url),"utf8"));
async function harness(page:Page) {
  const writes:string[]=[];
  let architectureFailure=false, mapFailure=false;
  const overview={doc,git:{commit:"20bbd8ed97e70143738eafaa71de45a6b8814eb1",committed_at:null,subject:null,recent:[]},build:null,build_matches_running_code:false,keys:{},profiles:{text:"fixture",image:"none"},window:{status:"closed",authorized_end:null},worker:{state:"stopped",heartbeat:null},budget:{cap_krw:0,spent_krw:0,reserved_krw:0,remaining_krw:0},usage:[]};
  await page.route("**/api/**",async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    if(request.method()!=="GET"){writes.push(path);return route.fulfill({status:405,json:{detail:"Read-only contract"}});}
    if(path==="/api/session")return route.fulfill({headers:{"Set-Cookie":"hb_office_session=fixture; Path=/; HttpOnly; SameSite=Strict"},json:{csrf:"fixture"}});
    if(path==="/api/architecture")return route.fulfill({status:architectureFailure?503:200,json:architectureFailure?{detail:"운영 상태 조회 실패"}:overview});
    if(path==="/api/pipeline-studio")return route.fulfill({status:mapFailure?503:200,contentType:mapFailure?"application/json":"text/html",body:mapFailure?JSON.stringify({detail:"지도 연결 실패"}):'<html lang="ko"><body><div id="currentView">개인 편집 지도 fixture</div><input aria-label="검토 메모"></body></html>'});
    if(path==="/api/dashboard")return route.fulfill({json:{articles:[],jobs:[],feeds:[],agents:[],tasks:[],events:[],budget:overview.budget,window:overview.window,provider:{},knowledge:{}}});
    if(path==="/api/jobs/summaries")return route.fulfill({json:{jobs:[]}});
    if(path==="/api/channels")return route.fulfill({json:{channels:[]}});
    return route.fulfill({status:404,json:{detail:"Fixture not configured"}});
  });
  return {writes,failArchitecture:(value:boolean)=>{architectureFailure=value;},failMap:(value:boolean)=>{mapFailure=value;}};
}

for(const width of [1440,390])test(`파이프라인 ${width}px 지도·운영 상세 전환은 읽기 전용이며 메모를 유지한다`,async({page})=>{
  const fixture=await harness(page);await page.setViewportSize({width,height:1000});await page.goto("/pipeline");
  const studio=page.getByTestId("pipeline-studio");await expect(studio.getByRole("heading",{name:"콘텐츠 파이프라인",exact:true})).toBeVisible();
  await expect(page.getByTestId("pipeline-live-budget")).toContainText("0원");await expect(page.getByTestId("pipeline-live-window")).toContainText("닫힘");
  await expect(page.getByTestId("pipeline-live-worker")).toContainText("중지");await expect(page.getByTestId("pipeline-live-updated")).not.toContainText("확인 전");
  const frame=page.frameLocator('[data-testid="pipeline-map-frame"]');await expect(frame.locator("#currentView")).toBeVisible();await frame.getByLabel("검토 메모").fill("보존할 검토 입력");
  await page.getByTestId("pipeline-tab-operations").click();await expect(page.getByRole("heading",{name:"한눈에 보는 제작 순서"})).toBeVisible();
  await page.getByTestId("pipeline-tab-map").click();await expect(frame.getByLabel("검토 메모")).toHaveValue("보존할 검토 입력");
  await expect(page.getByTestId("pipeline-map-new-tab")).toHaveAttribute("href","/api/pipeline-studio");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);expect(fixture.writes).toEqual([]);
});

test("운영 조회 실패는 확인 불가로 표시하고 재조회로 복구한다",async({page})=>{
  const fixture=await harness(page);fixture.failArchitecture(true);await page.goto("/pipeline");
  await expect(page.getByTestId("pipeline-live-error")).toContainText("운영 상태 조회 실패");await expect(page.getByTestId("pipeline-live-budget")).toContainText("확인 불가");
  fixture.failArchitecture(false);await page.getByTestId("pipeline-live-refresh").click();await expect(page.getByTestId("pipeline-live-budget")).toContainText("0원");expect(fixture.writes).toEqual([]);
});

test("지도 HTTP 오류와 전체화면 거부는 성공으로 숨기지 않고 다시 확인한다",async({page})=>{
  const fixture=await harness(page);fixture.failMap(true);await page.goto("/pipeline");
  await expect(page.getByTestId("pipeline-map-error")).toBeVisible();fixture.failMap(false);await page.getByTestId("pipeline-map-reload").click();
  await expect(page.frameLocator('[data-testid="pipeline-map-frame"]').locator("#currentView")).toBeVisible();await expect(page.getByTestId("pipeline-map-error")).toHaveCount(0);
  await page.evaluate(()=>{Element.prototype.requestFullscreen=()=>Promise.reject(new Error("fixture fullscreen denied"));});
  await page.getByTestId("pipeline-map-fullscreen").click();await expect(page.getByTestId("pipeline-fullscreen-error")).toBeVisible();expect(fixture.writes).toEqual([]);
});
