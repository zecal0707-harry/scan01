import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Download, Search, Loader2, Server, Database, ExternalLink, Link, RefreshCw, Zap, HardDrive } from "lucide-react";

type Hit = {
  server: string;
  role: "scan" | "film" | string;
  kind?: string; // "scan" | "recipe" | "mixed"
  level?: string; // "lot" | "film" | "film_name" | "folder"
  path: string;
  wafer?: string;
  lot?: string;
  film?: string;
  date?: string;
  recipe_linked?: boolean;
  recipe_name?: string;
  recipe_paths?: string[];
  recipe_primary?: string;
  recipe_server?: string;
};

export default function App() {
  // ---- Endpoints (프록시 사용: /scanner, /downloader) ----
  const [scannerBase] = useState("/scanner");
  const [downloaderBase] = useState("/downloader"); // d5.7.8은 serve 없음 → health 미사용

  // ---- Search form ----
  const [mode, setMode] = useState<"cache" | "direct" | "both">("both");
  const [searchSource, setSearchSource] = useState<"cache" | "direct" | "">("");
  const [role, setRole] = useState<"scan" | "film">("scan");

  // ---- Index Management ----
  type IndexStatus = {
    server: string;
    last_bootstrap: string | null;
    last_update: string | null;
    indexed_lots: number;
    indexed_films: number;
  };
  const [indexStatuses, setIndexStatuses] = useState<IndexStatus[]>([]);
  const [indexLoading, setIndexLoading] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [serversCsv, setServersCsv] = useState("");
  const [wafer, setWafer] = useState("");
  const [lot, setLot] = useState("");
  const [film, setFilm] = useState("");
  const [linkRecipe, setLinkRecipe] = useState(true);
  const [exact, setExact] = useState(false);
  const [regex, setRegex] = useState(false);
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [expandCap] = useState(0); // v19996ab는 films_index map/names 정책 → UI cap은 보류

  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<Hit[]>([]);
  const [error, setError] = useState<string | null>(null);

  // ---- Download ----
  const [destRoot, setDestRoot] = useState("D:\\DATA");
  const [downloading, setDownloading] = useState(false);
  const [downloadResult, setDownloadResult] = useState<{success: number; errors: number; total: number} | null>(null);

  // ---- Selection ----
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const allSelected = useMemo(() => hits.length > 0 && hits.every((h) => selected[key(h)]), [hits, selected]);

  function key(h: Hit) { return `${h.server}|${h.role}|${h.path}`; }

  async function doSearch() {
    setSearching(true);
    setError(null);
    setHits([]);
    setSelected({});
    setSearchSource("");

    const servers = serversCsv.split(/[,\s]+/).map(s => s.trim()).filter(Boolean);

    const body = {
      servers: servers.length ? servers : undefined,
      roles: [role],
      wafer: wafer ? [wafer] : [],
      lot: lot ? [lot] : [],
      film: film ? [film] : [],
      exact,
      regex,
      case_sensitive: caseSensitive,
      link_recipe: linkRecipe,
    };

    try {
      if (mode === "cache") {
        // Cache only (index search)
        const r = await fetch(`${scannerBase}/v1/search/cache`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (!r.ok) throw new Error(`scanner HTTP ${r.status}`);
        const js = await r.json();
        const hh: Hit[] = Array.isArray(js?.hits) ? js.hits : [];
        setHits(hh);
        setSearchSource("cache");
      } else if (mode === "direct") {
        // Direct only (server traversal)
        const r = await fetch(`${scannerBase}/v1/search/direct`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (!r.ok) throw new Error(`scanner HTTP ${r.status}`);
        const js = await r.json();
        const hh: Hit[] = Array.isArray(js?.hits) ? js.hits : [];
        setHits(hh);
        setSearchSource("direct");
      } else {
        // Both: try cache first, then direct if no results
        const cacheR = await fetch(`${scannerBase}/v1/search/cache`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (!cacheR.ok) throw new Error(`scanner HTTP ${cacheR.status}`);
        const cacheJs = await cacheR.json();
        const cacheHits: Hit[] = Array.isArray(cacheJs?.hits) ? cacheJs.hits : [];

        if (cacheHits.length > 0) {
          setHits(cacheHits);
          setSearchSource("cache");
        } else {
          // No cache results, try direct
          const directR = await fetch(`${scannerBase}/v1/search/direct`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
          if (!directR.ok) throw new Error(`scanner HTTP ${directR.status}`);
          const directJs = await directR.json();
          const directHits: Hit[] = Array.isArray(directJs?.hits) ? directJs.hits : [];
          setHits(directHits);
          setSearchSource("direct");
        }
      }
    } catch (e: any) {
      setError(`검색 실패: ${e?.message || e}`);
    } finally {
      setSearching(false);
    }
  }

  function exportSelectedAsJSON() {
    const chosen = hits.filter((h) => selected[key(h)]);
    if (chosen.length === 0) return alert("선택된 항목이 없습니다.");
    const data = { generated_at: new Date().toISOString(), hits: chosen };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `search_selected_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function doDownload() {
    const chosen = hits.filter((h) => selected[key(h)]);
    if (chosen.length === 0) return alert("선택된 항목이 없습니다.");
    if (!destRoot.trim()) return alert("다운로드 경로를 입력해주세요.");

    setDownloading(true);
    setDownloadResult(null);
    setError(null);

    const body = {
      hits: chosen,
      dest_root: destRoot.trim(),
      overwrite: "resume",
      dest_mode: "simple",
    };

    try {
      const r = await fetch(`${scannerBase}/v1/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const js = await r.json();
      setDownloadResult({
        success: js.success || 0,
        errors: js.errors || 0,
        total: js.total || 0,
      });
    } catch (e: any) {
      setError(`다운로드 실패: ${e?.message || e}`);
    } finally {
      setDownloading(false);
    }
  }

  // ---- Index Management Functions ----
  async function fetchIndexStatus() {
    setIndexLoading(true);
    try {
      const r = await fetch(`${scannerBase}/v1/index/status`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const js = await r.json();
      setIndexStatuses(js.statuses || []);
    } catch (e: any) {
      setError(`인덱스 상태 조회 실패: ${e?.message || e}`);
    } finally {
      setIndexLoading(false);
    }
  }

  async function doBootstrap() {
    if (!confirm("전체 인덱스를 재생성합니다. 시간이 오래 걸릴 수 있습니다. 계속하시겠습니까?")) return;
    setBootstrapping(true);
    setError(null);
    try {
      const r = await fetch(`${scannerBase}/v1/index/bootstrap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const js = await r.json();
      alert(`Bootstrap 완료: ${JSON.stringify(js.results)}`);
      fetchIndexStatus();
    } catch (e: any) {
      setError(`Bootstrap 실패: ${e?.message || e}`);
    } finally {
      setBootstrapping(false);
    }
  }

  async function doIndexUpdate() {
    setUpdating(true);
    setError(null);
    try {
      const r = await fetch(`${scannerBase}/v1/index/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const js = await r.json();
      alert(`Update 완료: ${JSON.stringify(js.results)}`);
      fetchIndexStatus();
    } catch (e: any) {
      setError(`Update 실패: ${e?.message || e}`);
    } finally {
      setUpdating(false);
    }
  }

  return (
    <div className="min-h-screen w-full p-6 space-y-6 bg-gradient-to-b from-slate-50 to-white">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Server className="h-5 w-5" />
          <h1 className="text-xl font-semibold">FAB 데이터 검색 시스템</h1>
          <Badge variant="secondary">v1.0</Badge>
        </div>
        <div className="text-xs text-slate-500">API: 127.0.0.1:8081</div>
      </header>

      <Card className="shadow-sm border-blue-100">
        <CardHeader className="pb-3 bg-blue-50/50">
          <CardTitle className="flex items-center gap-2"><Search className="h-5 w-5 text-blue-600" />데이터 검색</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-4">
          <form onSubmit={(e) => { e.preventDefault(); doSearch(); }}>
          {/* 검색 모드 선택 */}
          <div className="p-3 bg-slate-50 rounded-lg mb-4">
            <Label className="text-sm font-medium mb-2 block">검색 모드</Label>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant={mode === "both" ? "default" : "outline"}
                size="sm"
                onClick={() => setMode("both")}
                className="flex-1 min-w-[120px]"
              >
                <Zap className="mr-1 h-3 w-3" />
                자동 (권장)
              </Button>
              <Button
                type="button"
                variant={mode === "cache" ? "default" : "outline"}
                size="sm"
                onClick={() => setMode("cache")}
                className="flex-1 min-w-[120px]"
              >
                <Database className="mr-1 h-3 w-3" />
                캐시 검색
              </Button>
              <Button
                type="button"
                variant={mode === "direct" ? "default" : "outline"}
                size="sm"
                onClick={() => setMode("direct")}
                className="flex-1 min-w-[120px]"
              >
                <Server className="mr-1 h-3 w-3" />
                서버 직접 탐색
              </Button>
            </div>
            <div className="text-xs text-slate-500 mt-2">
              {mode === "both" && "캐시에서 먼저 검색 후, 없으면 서버 직접 탐색 (가장 빠름)"}
              {mode === "cache" && "인덱스 파일에서 검색 (빠르지만 최신 데이터 누락 가능)"}
              {mode === "direct" && "서버 폴더를 직접 탐색 (느리지만 최신 데이터 확인 가능)"}
            </div>
          </div>

          {/* 검색 조건 */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            <div>
              <Label className="text-sm">데이터 타입</Label>
              <Select value={role} onValueChange={(v: any) => setRole(v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="scan">Scan 데이터</SelectItem>
                  <SelectItem value="film">Film 데이터</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm">Wafer Recipe</Label>
              <Input value={wafer} onChange={(e) => setWafer(e.target.value)} placeholder="예: CN2T_CLN_..." />
            </div>
            <div>
              <Label className="text-sm">Lot ID</Label>
              <Input value={lot} onChange={(e) => setLot(e.target.value)} placeholder="예: AHNL4204" />
            </div>
            <div>
              <Label className="text-sm">Film Recipe</Label>
              <Input value={film} onChange={(e) => setFilm(e.target.value)} placeholder="예: VBMQ_CLN_..." />
            </div>
          </div>

          {/* 서버 필터 (옵션) */}
          <div>
            <Label className="text-sm text-slate-600">서버 필터 (선택)</Label>
            <Input value={serversCsv} onChange={(e) => setServersCsv(e.target.value)} placeholder="비워두면 전체 서버 검색, 여러 서버는 쉼표로 구분" />
          </div>

          {/* 검색 옵션 */}
          <div className="flex flex-wrap items-center gap-4 p-3 bg-slate-50 rounded-lg">
            <span className="text-sm font-medium text-slate-700">옵션:</span>
            <label className="flex items-center gap-2 text-sm cursor-pointer"><Checkbox checked={linkRecipe} onCheckedChange={(v) => setLinkRecipe(!!v)} />레시피 연결</label>
            <Separator orientation="vertical" className="h-5" />
            <label className="flex items-center gap-2 text-sm cursor-pointer"><Checkbox checked={exact} onCheckedChange={(v) => setExact(!!v)} />정확히 일치</label>
            <label className="flex items-center gap-2 text-sm cursor-pointer"><Checkbox checked={regex} onCheckedChange={(v) => setRegex(!!v)} />정규식</label>
            <label className="flex items-center gap-2 text-sm cursor-pointer"><Checkbox checked={caseSensitive} onCheckedChange={(v) => setCaseSensitive(!!v)} />대소문자 구분</label>
          </div>

          {/* 검색 버튼 */}
          <div className="flex justify-end">
            <Button type="submit" disabled={searching} size="lg" className="px-8">
              {searching ? (<><Loader2 className="mr-2 h-4 w-4 animate-spin" />검색 중...</>) : (<><Search className="mr-2 h-4 w-4" />검색</>)}
            </Button>
          </div>

          {error && <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">{error}</div>}
          </form>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Database className="h-5 w-5" />Results ({hits.length})
              {searchSource && <Badge variant={searchSource === "cache" ? "secondary" : "default"}>{searchSource}</Badge>}
            </CardTitle>
            <Button variant="secondary" onClick={exportSelectedAsJSON}><ExternalLink className="mr-2 h-4 w-4" />Export JSON</Button>
          </div>
          <div className="flex items-center gap-3 mt-3 pt-3 border-t">
            <Label className="whitespace-nowrap">Download to:</Label>
            <Input
              value={destRoot}
              onChange={(e) => setDestRoot(e.target.value)}
              placeholder="D:\DATA"
              className="max-w-xs"
            />
            <Button onClick={doDownload} disabled={downloading || Object.values(selected).filter(Boolean).length === 0}>
              {downloading ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Downloading...</>
              ) : (
                <><Download className="mr-2 h-4 w-4" />Download Selected ({Object.values(selected).filter(Boolean).length})</>
              )}
            </Button>
            {downloadResult && (
              <div className="text-sm">
                <span className="text-green-600">Success: {downloadResult.success}</span>
                {downloadResult.errors > 0 && <span className="text-red-600 ml-2">Errors: {downloadResult.errors}</span>}
                <span className="text-slate-500 ml-2">/ {downloadResult.total}</span>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border overflow-hidden overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead className="w-10"><Checkbox checked={allSelected} onCheckedChange={(v) => setSelected(v ? Object.fromEntries(hits.map(h => [key(h), true])) : {})} /></TableHead>
                  <TableHead className="whitespace-nowrap">Server</TableHead>
                  <TableHead className="whitespace-nowrap">Wafer Recipe</TableHead>
                  <TableHead className="whitespace-nowrap">Lot</TableHead>
                  <TableHead className="whitespace-nowrap">Film Recipe</TableHead>
                  <TableHead className="whitespace-nowrap">Path</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {hits.map((h) => (
                  <TableRow key={key(h)} className="hover:bg-slate-50">
                    <TableCell><Checkbox checked={!!selected[key(h)]} onCheckedChange={(v) => setSelected((m) => ({ ...m, [key(h)]: !!v }))} /></TableCell>
                    <TableCell className="font-medium text-sm">{h.server}</TableCell>
                    <TableCell className="text-sm">{h.wafer || "-"}</TableCell>
                    <TableCell className="text-sm font-medium">{h.lot || "-"}</TableCell>
                    <TableCell className="text-sm">
                      <div className="flex items-center gap-1">
                        {h.recipe_linked ? (
                          <Link className="h-3 w-3 text-green-600" title={(h.recipe_paths || []).join("\n")} />
                        ) : (
                          <span className="text-red-400 text-xs">✕</span>
                        )}
                        <span>{h.film || "-"}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs font-mono text-slate-500 max-w-xs truncate" title={h.path}>{h.path}</TableCell>
                  </TableRow>
                ))}
                {hits.length === 0 && (
                  <TableRow><TableCell colSpan={6} className="text-center text-sm text-slate-500 py-10">검색 결과가 비어 있습니다.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <HardDrive className="h-5 w-5" />Index Management
            </CardTitle>
            <Button variant="outline" size="sm" onClick={fetchIndexStatus} disabled={indexLoading}>
              {indexLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {indexStatuses.length === 0 ? (
            <div className="text-sm text-slate-500 text-center py-4">
              상태 조회 버튼을 클릭하세요
            </div>
          ) : (
            <div className="space-y-3">
              {indexStatuses.map((st) => (
                <div key={st.server} className="p-3 border rounded-md bg-slate-50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium">{st.server}</span>
                    <div className="flex gap-2">
                      <Badge variant="secondary">Lots: {st.indexed_lots}</Badge>
                      <Badge variant="secondary">Films: {st.indexed_films}</Badge>
                    </div>
                  </div>
                  <div className="text-xs text-slate-600 space-y-1">
                    <div>Last Bootstrap: {st.last_bootstrap || "-"}</div>
                    <div>Last Update: {st.last_update || "-"}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-3 pt-2 border-t items-center">
            <Button onClick={doBootstrap} disabled={bootstrapping} variant="outline">
              {bootstrapping ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Bootstrapping...</>
              ) : (
                <><RefreshCw className="mr-2 h-4 w-4" />Bootstrap</>
              )}
            </Button>
            <Button onClick={doIndexUpdate} disabled={updating} variant="default">
              {updating ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Updating...</>
              ) : (
                <><Zap className="mr-2 h-4 w-4" />Update</>
              )}
            </Button>
            <div className="text-xs text-slate-500 ml-auto">
              Bootstrap: 전체 재인덱싱 | Update: 증분 업데이트
            </div>
          </div>
        </CardContent>
      </Card>

      <footer className="pt-2 text-xs text-slate-500 text-center">
        UI에서 직접 다운로드하거나, JSON 저장 후 CLI에서<br />
        <code>python -m downloader.cli --server-file servers.txt --file exported.json --dest-root D:\DATA</code>
      </footer>
    </div>
  );
}
