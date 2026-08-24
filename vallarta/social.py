#!/usr/bin/env python3
"""Normalize public Facebook scraper exports into the Vallarta intake scheme.

This script does not scrape. It reads JSON exports produced elsewhere, strips
poster/commenter identity fields by omission, and writes a worklist for the
same judgement step used by news and hand-collected UGC.

Typical flow:

  python3 social.py queries --city "Puerto Vallarta" --topic pollution
  python3 social.py build data/social/raw/*.json --path keyword_search --topic pollution
  # classify data/social-worklist-<date>.json with an LLM / operator
  python3 social.py records data/social-classified-<date>.json --out data/extract-social-<date>.json
  python3 store.py data/extract-social-<date>.json
"""

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone

import store
import ugc

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
STATE = os.path.join(ROOT, "state")
DEFAULT_SOURCES = os.path.join(STATE, "social_sources.json")

TOPICS = {
    "pollution": {
        "queries": [
            '"{city}" contaminacion',
            '"{city}" aguas negras',
            '"{city}" basura',
            '"{city}" drenaje',
            '"{alias}" playa sucia',
            '"{alias}" contaminacion',
            '"PV" contaminacion',
        ],
        "terms": [
            "contaminacion", "contaminado", "contaminada", "aguas negras",
            "aguas residuales", "drenaje", "alcantarillado", "basura",
            "tiradero", "relleno sanitario", "playa sucia", "mal olor",
            "apestoso", "derrame",
        ],
        "subtopics": {
            "sewage": ["aguas negras", "aguas residuales", "drenaje", "alcantarillado", "coladera"],
            "garbage": ["basura", "tiradero", "relleno sanitario", "residuos", "aseo publico"],
            "beach_water": ["playa", "mar", "rio", "canal", "derrame"],
            "air_smell": ["mal olor", "apestoso", "olor", "huele"],
        },
    },
}

TEXT_KEYS = (
    "text", "message", "postText", "post_text", "caption", "description",
    "content", "body", "commentText", "comment_text", "reviewText",
)
URL_KEYS = (
    "url", "postUrl", "post_url", "facebookUrl", "facebook_url",
    "permalink", "permalinkUrl", "link", "href",
)
SOURCE_URL_KEYS = (
    "pageUrl", "page_url", "profileUrl", "profile_url", "groupUrl",
    "group_url", "sourceUrl", "source_url", "authorUrl", "ownerUrl",
)
SOURCE_NAME_KEYS = (
    "pageName", "page_name", "groupName", "group_name", "profileName",
    "profile_name", "sourceName", "source_name", "ownerName", "owner_name",
)
DATE_KEYS = (
    "date", "time", "timestamp", "createdAt", "created_at", "postDate",
    "post_date", "creationTime", "creation_time", "publishedAt", "published_at",
)
COMMENT_KEYS = ("comments", "topComments", "top_comments", "latestComments", "latest_comments")
COMMENT_ID_KEYS = ("id", "commentId", "comment_id", "legacyId", "legacy_id")


def fold(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def whole_word(term):
    return re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(fold(term)))


def match_terms(text, terms):
    folded = fold(text)
    hits = []
    for term in terms:
        if whole_word(term).search(folded):
            hits.append(term)
    return hits


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def get_any(obj, keys):
    for key in keys:
        cur = obj
        ok = True
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, ""):
            return cur
    return None


def as_items(obj):
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, dict):
        return []
    for key in ("items", "results", "data", "posts", "records", "datasetItems"):
        value = obj.get(key)
        if isinstance(value, list):
            return value
    if any(k in obj for k in TEXT_KEYS + URL_KEYS):
        return [obj]
    return []


def clean_text(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[email]", text)
    text = re.sub(r"(?:\+?\d[\d\s().-]{7,}\d)", "[phone]", text)
    return text


def trim(text, limit=300):
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def parse_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if text.isdigit():
        return parse_date(int(text))
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        pass
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if match:
        return match.group(0)
    return None


def canonical_url(raw, text, content_type, parent_url=None):
    url = get_any(raw, URL_KEYS)
    if url:
        return str(url).strip()
    base = parent_url or "facebook://content"
    digest = hashlib.sha1(("%s\n%s" % (content_type, text)).encode("utf-8")).hexdigest()[:16]
    return "%s#%s-%s" % (base, content_type, digest)


def comment_url(parent_url, comment, text):
    url = get_any(comment, URL_KEYS)
    if url:
        return str(url).strip()
    cid = get_any(comment, COMMENT_ID_KEYS)
    if not cid:
        cid = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return "%s#comment-%s" % (parent_url, cid)


def norm_url(url):
    if not url:
        return ""
    text = str(url).strip().lower()
    text = re.sub(r"[?#].*$", "", text)
    return text.rstrip("/")


def load_social_sources(path):
    if not path or not os.path.exists(path):
        return {}, []
    payload = load_json(path)
    rows = payload.get("sources", []) if isinstance(payload, dict) else payload
    index = {}
    for src in rows:
        if not isinstance(src, dict):
            continue
        urls = [src.get("url"), src.get("page_url"), src.get("group_url")]
        urls += src.get("aliases", []) if isinstance(src.get("aliases"), list) else []
        for url in urls:
            key = norm_url(url)
            if key:
                index[key] = src
    return index, rows


def raw_source_url(raw):
    return get_any(raw, SOURCE_URL_KEYS) or get_any(raw, URL_KEYS)


def raw_source_name(raw):
    return get_any(raw, SOURCE_NAME_KEYS)


def source_info(raw, path, source_index, keep_source_names):
    src = source_index.get(norm_url(raw_source_url(raw)))
    if not src:
        # Sometimes the only URL is the post URL. Match a configured Page URL as
        # a prefix of that post URL.
        raw_url = norm_url(get_any(raw, URL_KEYS))
        src = next((v for k, v in source_index.items() if raw_url.startswith(k)), None)
    if src:
        name = src.get("name") or raw_source_name(raw) or "Facebook local source"
        status = str(src.get("status") or "")
        return {
            "name": name,
            "outlet": "facebook:%s" % name,
            "url": src.get("url") or src.get("page_url") or src.get("group_url"),
            "kind": src.get("kind", "local_source"),
            "scope_city": src.get("scope_city"),
            "scope_colonia": src.get("scope_colonia"),
            "approved": status == "approved" or status.startswith("approved_by_operator"),
            "configured": True,
        }
    if keep_source_names and raw_source_name(raw):
        name = str(raw_source_name(raw)).strip()
        return {
            "name": name,
            "outlet": "facebook:%s" % name,
            "url": raw_source_url(raw),
            "kind": "unconfigured_source",
            "scope_city": None,
            "scope_colonia": None,
            "approved": False,
            "configured": False,
        }
    label = "Facebook local source" if path == "local_sources" else "Facebook public search"
    return {
        "name": label,
        "outlet": "facebook:%s" % label,
        "url": raw_source_url(raw),
        "kind": path,
        "scope_city": None,
        "scope_colonia": None,
        "approved": False,
        "configured": False,
    }


def metric(raw, *keys):
    value = get_any(raw, keys)
    if isinstance(value, dict):
        return sum(metric(value, k) for k in value)
    if isinstance(value, list):
        return len(value)
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def metrics(raw):
    likes = metric(raw, "likes", "likesCount", "likeCount")
    comments = metric(raw, "commentsCount", "commentCount", "comments_count")
    shares = metric(raw, "shares", "sharesCount", "shareCount")
    reactions = metric(raw, "reactionsCount", "reactionCount")
    total = likes + comments + shares + reactions
    return {
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "reactions": reactions,
        "engagement_total": total,
    }


def load_local_terms(city):
    sources = store.load(os.path.join(STATE, "sources.json"), {})
    conf = (sources.get("cities") or {}).get(store.CITY, {})
    terms = list(conf.get("local_terms") or [])
    terms.append(city)
    if fold(city) == "puerto vallarta":
        terms += ["vallarta", "pv"]
    return sorted(set(t for t in terms if t), key=len, reverse=True)


def topic_config(topic):
    return TOPICS.get(fold(topic), {"queries": ['"{city}" ' + topic], "terms": [topic], "subtopics": {}})


def default_aliases(city):
    aliases = [city]
    if fold(city) == "puerto vallarta":
        aliases += ["Vallarta", "PV"]
    return aliases


def build_queries(city, topic, aliases):
    conf = topic_config(topic)
    out = []
    for template in conf["queries"]:
        if "{alias}" in template:
            for alias in aliases:
                out.append(template.format(city=city, alias=alias))
        else:
            out.append(template.format(city=city, alias=aliases[0] if aliases else city))
    return list(dict.fromkeys(out))


def category_hints(text):
    vocab = store.load(os.path.join(STATE, "vocabulary.json"), {})
    active = vocab.get("active", {})
    hits = {}
    for cat, terms in active.items():
        if cat == "complaint_signals":
            continue
        found = match_terms(text, terms)
        if found:
            hits[cat] = found
    signals = match_terms(text, active.get("complaint_signals", []))
    return hits, signals


def subtopic_hints(text, topic):
    conf = topic_config(topic)
    out = {}
    for name, terms in conf.get("subtopics", {}).items():
        hits = match_terms(text, terms)
        if hits:
            out[name] = hits
    return out


def suggested_location(text, source):
    hits = ugc.match_places(text, ugc.gazetteer_patterns())
    if hits["streets"] or hits["landmarks"]:
        return {
            "location_certainty": "exact",
            "location_basis": "gazetteer_match",
            "street": hits["streets"][0]["display"] if hits["streets"] else None,
            "colonia": hits["colonias"][0]["display"] if hits["colonias"] else None,
            "landmark": hits["landmarks"][0]["display"] if hits["landmarks"] else None,
            "location_evidence": (hits["streets"] or hits["landmarks"])[0]["snippet"],
            "gazetteer_hits": hits,
        }
    if hits["colonias"]:
        return {
            "location_certainty": "approximate",
            "location_basis": "gazetteer_match",
            "street": None,
            "colonia": hits["colonias"][0]["display"],
            "landmark": None,
            "location_evidence": hits["colonias"][0]["snippet"],
            "gazetteer_hits": hits,
        }
    if source.get("scope_colonia"):
        colonia = source["scope_colonia"]
        return {
            "location_certainty": "approximate",
            "location_basis": "source_colonia_scope",
            "street": None,
            "colonia": colonia,
            "landmark": None,
            "location_evidence": "fuente de la colonia %s (%s)" % (colonia, source["name"]),
            "gazetteer_hits": hits,
        }
    return {
        "location_certainty": "none",
        "location_basis": "none",
        "street": None,
        "colonia": None,
        "landmark": None,
        "location_evidence": None,
        "gazetteer_hits": hits,
    }


def city_basis(text, query, source, city, local_terms):
    if source.get("scope_city") and fold(source["scope_city"]) == fold(city):
        return "local_source_scope"
    if source.get("scope_colonia"):
        return "source_colonia_scope"
    if match_terms("%s %s" % (text, query or ""), local_terms):
        return "text_or_query"
    return "unproven"


def record_seed(item):
    loc = item["signals"]["suggested_location"]
    return {
        "article_url": item["content_url"],
        "article_date": item["content_date"],
        "source_outlet": item["source"]["outlet"],
        "author": None,
        "qualifies": "yes|unsure",
        "categories": list(item["signals"]["category_hints"].keys()) or ["other"],
        "status": "new_complaint|ongoing|failed_repair|resolved|unclear",
        "location_certainty": loc["location_certainty"],
        "location_evidence": loc["location_evidence"],
        "street": loc["street"],
        "colonia": loc["colonia"],
        "landmark": loc["landmark"],
        "summary": "",
        "affected_people_clue": None,
        "duration_clue": None,
        "source_type": "facebook",
        "source_path": item["ingestion"]["path"],
        "content_type": item["content_type"],
        "topic": item["topic_requested"],
        "subtopic": None,
        "sentiment": None,
        "severity": None,
        "engagement": item["metrics"]["engagement_total"],
        "location_basis": loc["location_basis"],
        "city_relevance_basis": item["signals"]["city_relevance_basis"],
    }


def normalize_one(raw, *, content_type, source, path, city, topic, query, input_file,
                  parent=None, parent_url=None):
    text = clean_text(get_any(raw, TEXT_KEYS))
    if not text:
        return None
    url = canonical_url(raw, text, content_type, parent_url=parent_url)
    if content_type == "comment":
        url = comment_url(parent_url, raw, text)
    content_date = parse_date(get_any(raw, DATE_KEYS))
    cat_hits, complaint_signals = category_hints(text)
    local_terms = load_local_terms(city)
    topic_terms = match_terms(text, topic_config(topic).get("terms", []))
    loc = suggested_location(text, source)
    item = {
        "content_id": "fb:%s:%s" % (content_type, hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]),
        "content_type": content_type,
        "content_url": url,
        "content_date": content_date,
        "city": city,
        "topic_requested": topic,
        "text": text,
        "text_preview": trim(text),
        "source": source,
        "parent": parent,
        "metrics": metrics(raw),
        "ingestion": {
            "path": path,
            "query": query,
            "input_file": input_file,
        },
        "signals": {
            "city_relevance_basis": city_basis(text, query, source, city, local_terms),
            "local_terms": match_terms("%s %s" % (text, query or ""), local_terms),
            "topic_terms": topic_terms,
            "subtopic_hints": subtopic_hints(text, topic),
            "category_hints": cat_hits,
            "complaint_signals": complaint_signals,
            "suggested_location": loc,
        },
    }
    item["record_seed"] = record_seed(item)
    return item


def iter_normalized(files, args, source_index):
    for path in files:
        payload = load_json(path)
        default_query = args.query or (payload.get("query") if isinstance(payload, dict) else None)
        for raw in as_items(payload):
            if not isinstance(raw, dict):
                continue
            source = source_info(raw, args.path, source_index, args.keep_source_names)
            post = normalize_one(raw, content_type="post", source=source, path=args.path,
                                 city=args.city, topic=args.topic, query=default_query,
                                 input_file=path)
            if post:
                yield post
            comments = []
            for key in COMMENT_KEYS:
                value = raw.get(key)
                if isinstance(value, list):
                    comments = value
                    break
            for comment in comments[:args.max_comments]:
                if not isinstance(comment, dict) or not post:
                    continue
                parent = {
                    "content_url": post["content_url"],
                    "content_date": post["content_date"],
                    "text_preview": post["text_preview"],
                }
                item = normalize_one(comment, content_type="comment", source=source,
                                     path=args.path, city=args.city, topic=args.topic,
                                     query=default_query, input_file=path, parent=parent,
                                     parent_url=post["content_url"])
                if item:
                    yield item


def build_worklist(args):
    source_index, configured_sources = load_social_sources(args.source_config)
    seen, items, dupes = set(), [], 0
    for item in iter_normalized(args.files, args, source_index):
        key = item["content_url"]
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        items.append(item)

    by_basis = Counter(i["signals"]["city_relevance_basis"] for i in items)
    by_type = Counter(i["content_type"] for i in items)
    payload = {
        "kind": "social_worklist",
        "collected": args.collected,
        "city": args.city,
        "topic": args.topic,
        "inputs": args.files,
        "source_config": args.source_config if os.path.exists(args.source_config) else None,
        "configured_source_count": len(configured_sources),
        "total_items": len(items),
        "duplicates_dropped": dupes,
        "content_types": dict(by_type),
        "city_relevance_basis": dict(by_basis),
        "privacy_note": (
            "Poster and commenter identity fields are deliberately omitted. "
            "Use Page/group/source names only when they are configured local sources."
        ),
        "llm_classification_schema": {
            "relevant_to_city": "yes|no",
            "qualifies": "yes|unsure|no",
            "reason_code_if_no": "out_of_area|off_topic_other|event_not_complaint|...",
            "categories": list(sorted(store.CATEGORIES)),
            "status": list(sorted(store.STATUSES)),
            "topic": args.topic,
            "subtopic": "sewage|garbage|beach_water|air_smell|other|null",
            "sentiment": "complaint|question|neutral|support|null",
            "severity": "low|medium|high|unknown|null",
            "location_evidence": "short phrase from the post/comment naming the place, or null",
            "street": "only if named in location_evidence",
            "colonia": "only if named in location_evidence or source_colonia_scope",
            "landmark": "only if named in location_evidence",
            "summary": "Oracion en espanol, maximo 25 palabras",
            "affected_people_clue": "short phrase or null",
            "duration_clue": "short phrase or null",
        },
        "items": items,
    }
    out = args.out or os.path.join(DATA, "social-worklist-%s.json" % args.collected)
    save_json(out, payload)
    print("%d social items -> %s" % (len(items), out))
    print("content types:", json.dumps(dict(by_type), ensure_ascii=False))
    print("city basis:", json.dumps(dict(by_basis), ensure_ascii=False))


def classify_value(obj):
    return obj.get("classification") or obj.get("classified") or obj.get("llm") or obj


def boolish(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return fold(str(value)) in {"yes", "true", "1", "si", "relevant", "relevante"}


SUBTOPIC_CATEGORIES = {
    "sewage": ["drainage"],
    "garbage": ["trash"],
    "beach_water": ["water", "drainage"],
    "air_smell": ["other"],
}


def clean_categories(values, subtopic, hints):
    cats = values or SUBTOPIC_CATEGORIES.get(fold(subtopic), [])
    if not cats and hints:
        cats = list(hints)
    cats = [fold(c).replace("-", "_") for c in cats]
    cats = [c if c in store.CATEGORIES else "other" for c in cats]
    return sorted(set(cats or ["other"]))


def clean_status(value):
    status = fold(value).replace("-", "_")
    return status if status in store.STATUSES else "unclear"


def first_text_match(text, phrase):
    if not text or not phrase:
        return None
    ftext, fphrase = fold(text), fold(phrase)
    pos = ftext.find(fphrase)
    if pos < 0:
        return None
    return text[pos:pos + len(phrase)]


def location_from_classification(item, cls):
    loc = item.get("signals", {}).get("suggested_location", {})
    street = cls.get("street")
    colonia = cls.get("colonia")
    landmark = cls.get("landmark")
    evidence = cls.get("location_evidence")
    mentioned = cls.get("location_mentioned") or cls.get("place")
    if mentioned and not evidence:
        evidence = first_text_match(item.get("text", ""), mentioned)
    if not any([street, colonia, landmark]) and mentioned:
        # If the gazetteer/location suggestion already knows the same phrase,
        # reuse its structured kind. Otherwise keep it as extra metadata only.
        for field in ("street", "colonia", "landmark"):
            if loc.get(field) and fold(loc[field]) == fold(mentioned):
                return {
                    "location_certainty": loc.get("location_certainty", "approximate"),
                    "location_basis": "gazetteer_match",
                    "location_evidence": evidence or loc.get("location_evidence"),
                    "street": loc.get("street"),
                    "colonia": loc.get("colonia"),
                    "landmark": loc.get("landmark"),
                }
    if any([street, colonia, landmark]):
        certainty = cls.get("location_certainty")
        if certainty not in store.CERTAINTY:
            certainty = "exact" if street or landmark else "approximate"
        return {
            "location_certainty": certainty,
            "location_basis": cls.get("location_basis") or "llm_text",
            "location_evidence": evidence,
            "street": street,
            "colonia": colonia,
            "landmark": landmark,
        }
    return {
        "location_certainty": loc.get("location_certainty", "none"),
        "location_basis": loc.get("location_basis", "none"),
        "location_evidence": loc.get("location_evidence"),
        "street": loc.get("street"),
        "colonia": loc.get("colonia"),
        "landmark": loc.get("landmark"),
    }


def decision_for(cls):
    qualifies = fold(cls.get("qualifies") or cls.get("decision"))
    relevant = boolish(cls.get("relevant_to_city"))
    if relevant is False:
        return "no"
    if qualifies in {"yes", "unsure", "no"}:
        return qualifies
    if relevant is True and fold(cls.get("sentiment")) == "complaint":
        return "yes"
    if relevant is True:
        return "unsure"
    return "no"


def materialize_record(item, cls):
    decision = decision_for(cls)
    if decision not in {"yes", "unsure"}:
        return None
    subtopic = cls.get("subtopic")
    loc = location_from_classification(item, cls)
    summary = clean_text(cls.get("summary") or "Publicacion social reporta una preocupacion local de infraestructura.")
    rec = {
        "article_url": item["content_url"],
        "article_date": item.get("content_date") or date.today().isoformat(),
        "source_outlet": item.get("source", {}).get("outlet", "facebook:public_search"),
        "author": None,
        "qualifies": decision,
        "categories": clean_categories(cls.get("categories"), subtopic,
                                       item.get("signals", {}).get("category_hints", {})),
        "status": clean_status(cls.get("status")),
        "location_certainty": loc["location_certainty"],
        "location_evidence": loc["location_evidence"],
        "street": loc["street"],
        "colonia": loc["colonia"],
        "landmark": loc["landmark"],
        "summary": summary,
        "affected_people_clue": cls.get("affected_people_clue"),
        "duration_clue": cls.get("duration_clue"),
        "source_type": "facebook",
        "source_path": item.get("ingestion", {}).get("path"),
        "content_type": item.get("content_type"),
        "topic": cls.get("topic") or item.get("topic_requested"),
        "subtopic": subtopic,
        "sentiment": cls.get("sentiment"),
        "severity": cls.get("severity"),
        "engagement": item.get("metrics", {}).get("engagement_total", 0),
        "location_basis": loc["location_basis"],
        "city_relevance_basis": item.get("signals", {}).get("city_relevance_basis"),
    }
    return rec


def materialize(args):
    payload = load_json(args.classified)
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        sys.exit("classified input must be a JSON array or an object with items")

    records, decisions, rejected = [], [], []
    for idx, item in enumerate(items):
        cls = classify_value(item)
        decision = decision_for(cls)
        decisions.append({
            "index": idx,
            "article_url": item.get("content_url") or item.get("article_url"),
            "title": item.get("text_preview"),
            "source_outlet": item.get("source", {}).get("outlet", "facebook:public_search"),
            "pub_date": item.get("content_date"),
            "decision": decision,
            "reason_code": cls.get("reason_code_if_no") or cls.get("reason_code") or
            ("qualified" if decision == "yes" else "unsure" if decision == "unsure" else "off_topic_other"),
            "note": cls.get("note") or cls.get("summary"),
            "read_by_agent": True,
            "extraction_source": "facebook_scraper_export",
        })
        rec = materialize_record(item, cls)
        if not rec:
            continue
        problems = store.validate(rec)
        if problems:
            rejected.append({"article_url": rec["article_url"], "problems": problems})
            continue
        records.append(rec)

    if rejected and args.strict:
        print(json.dumps({"rejected": rejected}, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit("refusing to write invalid social records")

    save_json(args.out, records)
    triage_out = args.triage or os.path.join(DATA, "triage-social-%s.json" % args.collected)
    save_json(triage_out, {
        "cycle": "social-%s" % args.collected,
        "source_type": "facebook",
        "scanned": len(decisions),
        "decisions": decisions,
        "rejected_records": rejected,
    })
    print("%d records -> %s" % (len(records), args.out))
    print("%d decisions -> %s" % (len(decisions), triage_out))
    if rejected:
        print("%d invalid records were left out" % len(rejected), file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("queries", help="print keyword searches for a city/topic")
    q.add_argument("--city", default="Puerto Vallarta")
    q.add_argument("--topic", default="pollution")
    q.add_argument("--alias", action="append", default=[])

    b = sub.add_parser("build", help="convert scraper JSON exports to a social worklist")
    b.add_argument("files", nargs="+")
    b.add_argument("--path", choices=["keyword_search", "local_sources"], required=True)
    b.add_argument("--city", default="Puerto Vallarta")
    b.add_argument("--topic", default="pollution")
    b.add_argument("--query")
    b.add_argument("--source-config", default=DEFAULT_SOURCES)
    b.add_argument("--collected", default=date.today().isoformat())
    b.add_argument("--max-comments", type=int, default=10)
    b.add_argument("--keep-source-names", action="store_true",
                   help="preserve scraper source names for unconfigured Pages; never preserves poster/commenter names")
    b.add_argument("--out")

    r = sub.add_parser("records", help="convert classified social worklist items to store.py records")
    r.add_argument("classified", help="worklist with classification objects on each item")
    r.add_argument("--out", required=True)
    r.add_argument("--triage")
    r.add_argument("--collected", default=date.today().isoformat())
    r.add_argument("--no-strict", dest="strict", action="store_false")
    r.set_defaults(strict=True)

    args = ap.parse_args()
    if args.cmd == "queries":
        aliases = args.alias or default_aliases(args.city)
        print(json.dumps({
            "city": args.city,
            "topic": args.topic,
            "queries": build_queries(args.city, args.topic, aliases),
        }, indent=2, ensure_ascii=False))
    elif args.cmd == "build":
        build_worklist(args)
    elif args.cmd == "records":
        materialize(args)


if __name__ == "__main__":
    main()
