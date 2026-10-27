"""Validate the handoff contract, privacy boundary, links, and archive fidelity."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote
import hashlib
import json
import re
import zipfile
import sys
from importlib.util import spec_from_file_location, module_from_spec

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PAGE = DIST / "content-studio"
DOWNLOADS = PAGE / "downloads"

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.urls=[]; self.ids=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if "id" in attrs:self.ids.append(attrs["id"])
        for name in ("href","src"):
            if attrs.get(name):self.urls.append(attrs[name])

def main():
    checks=[]
    def require(ok,name):
        if not ok:raise AssertionError(name)
        checks.append(name)
    data=json.loads((PAGE/"hub-data.json").read_text(encoding="utf-8"))
    require(len(data["requested_tool_coverage"])==29 and all(data["requested_tool_coverage"].values()),"requested_29_coverage")
    ids={t["id"] for t in data["tools"]}
    require(len(ids)==len(data["tools"]),"unique_tool_ids")
    require(all(x in ids for p in data["pipeline"] for x in p["tools"]),"stage_tool_references")
    require(len(data["pipeline"])==12 and len({p["id"] for p in data["pipeline"]})==12,"twelve_unique_stages")
    require(len(data["ideas"])==len({x["id"] for x in data["ideas"]}) and bool(data["ideas"]),"unique_nonempty_ideas")
    require(len(data["sources"])==len({x["id"] for x in data["sources"]}) and bool(data["sources"]),"unique_nonempty_sources")
    require([g["id"] for g in data["gates"]]==["G0","G1","G2","G3"],"approval_meanings_unchanged")
    require(next(t for t in data["tools"] if t["id"]=="upside")["urls"]==[],"unknown_upside_not_substituted")
    resources=data["resources"]
    require(resources["verified_count"]==resources["existing_count"]+resources["new_count"],"pdf_existing_new_separated")
    require(len(resources["pdfs"])==5 and sum(p["pages"] for p in resources["pdfs"])==87,"new_pdf_metadata")
    require(resources["subscription_new_count"]==0,"subscription_export_not_claimed")
    blueprint=json.loads((DOWNLOADS/"pipeline-blueprint.json").read_text(encoding="utf-8"))
    d=blueprint["defaults"]
    require(d["budget_usd"]==0 and not d["execute_external"] and not d["paid_generation_enabled"],"zero_spend_defaults")
    require(not any(d[k] for k in ("external_publication_enabled","newsletter_send_enabled","coupon_write_enabled")),"writes_disabled")
    require(d["default_visibility"]=="private","explicit_private_default")
    require(blueprint["execution_verdict"]=="not_executed" and blueprint["current_implementation"]["new_model_quality_winner"] is None,"no_execution_or_winner_fabricated")
    require(blueprint["current_implementation"]["issue_approval_and_send_3"]=="not_connected","issue_label_not_delivery")
    cm=data.get("cost_model",{})
    require(cm==json.loads((ROOT/"content-studio/cost-scenarios.json").read_text(encoding="utf-8")),"calculator_uses_single_reviewed_data_source")
    require(cm.get("verification",{}).get("actual_generation_tests")==0 and cm.get("verification",{}).get("paid_api_calls")==0,"calculator_examples_not_actual_generations")
    signals=json.loads((DOWNLOADS/"public-signals.json").read_text(encoding="utf-8"))
    require(not signals["is_operational_collector"] and not signals["collection_enabled"] and not signals["article_bodies_saved"],"one_time_feed_sample_not_operational_collection")
    require(len(signals["signals"])==6 and signals["deduplication"]["unique_feed_urls"]==3,"feed_sample_scope_preserved")
    records=blueprint["required_records"]
    require({"product_revision","product_hash","fetched_at","valid_until","starts_at","ends_at","usage_limit","issuance_limit","snapshot_hash"}.issubset(records["OfferSnapshot"]),"offer_version_validity_and_limits_portable")
    require({"channel","account_ref","scheduled_at","timezone","source_approval_id","release_approval_ids","manifest_hash","offer_snapshot_hash"}.issubset(records["IssueDraft"]),"issue_binds_approved_assets_and_destination")
    require(blueprint["record_rules"]["required_records_status"]=="proposed_contracts_not_current_database_schemas","contracts_not_misreported_as_database")
    require(all(g.get("current_checks") and g.get("proposed_extensions") for g in blueprint["approval_gates"]),"current_checks_separated_from_extensions")
    spec=spec_from_file_location("build_content",ROOT/"scripts"/"build-content-studio.py")
    module=module_from_spec(spec);spec.loader.exec_module(module)
    module.public_check("https://example.com/a","valid HTTPS")
    rejected=False
    try:module.public_check("C:/Users/example/private.txt","fixture")
    except ValueError:rejected=True
    require(rejected,"privacy_detector_rejects_local_path_accepts_https")
    for p in PAGE.rglob("*"):
        if p.is_file() and p.suffix in (".json",".md",".html",".js",".css"):
            module.public_check(p.read_text(encoding="utf-8"),str(p.relative_to(PAGE)))
    require(not list(PAGE.rglob("*.pdf")),"no_third_party_original_pdf_export")
    parser=Links();parser.feed((PAGE/"index.html").read_text(encoding="utf-8"))
    require(len(parser.ids)==len(set(parser.ids)),"unique_html_ids")
    for link in parser.urls:
        u=urlparse(link)
        if u.scheme:
            require(u.scheme in ("http","https") and not u.username,"safe_html_url")
            continue
        if not u.path:
            if u.fragment:require(unquote(u.fragment) in parser.ids,"existing_fragment_"+u.fragment)
            continue
        target=(DIST/u.path.lstrip("/")) if u.path.startswith("/") else (PAGE/unquote(u.path))
        target=target.resolve()
        require(target==DIST.resolve() or DIST.resolve() in target.parents,"local_link_stays_in_dist")
        if target.is_dir():target=target/"index.html"
        require(target.is_file(),"local_link_exists_"+u.path)
    manifest=json.loads((DOWNLOADS/"manifest.json").read_text(encoding="utf-8"))
    canonical=json.loads((DOWNLOADS/"integrated-guide.json").read_text(encoding="utf-8"))
    require(manifest["canonical_reference"]["version"]==canonical["version"],"canonical_snapshot_version_matches_manifest")
    require(blueprint["parent_guide"]==manifest["canonical_reference"],"blueprint_and_archive_share_canonical_reference")
    require(not canonical["scope"]["activate_external_integrations"] and canonical["scope"]["additional_cash_krw"]==0,"integrated_snapshot_does_not_authorize_execution")
    for row in manifest["files"]:
        target=DOWNLOADS/row["name"]
        require(target.stat().st_size==row["bytes"] and module.digest(target)==row["sha256"],"export_hash_"+row["name"])
    with zipfile.ZipFile(DOWNLOADS/"content-studio-handoff.zip") as z:
        require(z.testzip() is None,"zip_crc")
        require(set(z.namelist())==set(r["name"] for r in manifest["files"])|{"manifest.json"},"zip_allowlist")
        for row in manifest["files"]:
            require(hashlib.sha256(z.read(row["name"])).hexdigest()==row["sha256"],"zip_hash_"+row["name"])
        require(not any("PRIVATE" in n or n.lower().endswith(".pdf") or ".." in Path(n).parts for n in z.namelist()),"zip_no_private_originals_or_traversal")
    hosting=ROOT/".openai"/"hosting.json"
    identity=hosting if hosting.is_file() else ROOT/"site-target.json"
    require(json.loads(identity.read_text(encoding="utf-8"))["project_id"]=="appgprj_6adf947030f48191b1332eff1c396042","site_identity_preserved")
    require(json.loads((ROOT/"site-target.json").read_text(encoding="utf-8"))["access"]=="owner-private","portable_metadata_preserves_audience")
    with zipfile.ZipFile(DOWNLOADS/"content-studio-source.zip") as z:
        require(z.testzip() is None,"source_zip_crc")
        sm=json.loads(z.read("SOURCE_MANIFEST.json"))
        require(set(z.namelist())=={r["name"] for r in sm["files"]}|{"SOURCE_MANIFEST.json"},"source_zip_allowlist")
        require(not any(".." in Path(n).parts or n.startswith('/') or '\\' in n or 'PRIVATE' in n or n.lower().endswith(('.pdf','.pyc','.zip')) or '.openai/' in n or '.git/' in n for n in z.namelist()),"source_zip_no_private_originals_state_or_nested_archives")
        for row in sm["files"]:
            b=z.read(row["name"])
            require(len(b)==row["bytes"] and hashlib.sha256(b).hexdigest()==row["sha256"],"source_hash_"+row["name"])
    result=dict(status="passed",checks=len(checks),check_names=checks,scope="Static contract/privacy/link/archive checks, not provider/account/publication E2E")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":main()
