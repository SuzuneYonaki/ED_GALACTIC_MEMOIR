import html
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

SEARCH_CATEGORIES: Tuple[str, ...] = (
    "bookmark",
    "system",
    "body",
    "bio",
    "codex",
    "mining",
    "station",
    "physics",
)

CATEGORY_PRIORITY: Dict[str, int] = {
    "bookmark": 1,
    "system": 2,
    "body": 3,
    "bio": 4,
    "mining": 5,
    "codex": 6,
    "station": 7,
    "physics": 8,
}

MAX_QUERY_LEN = 500
MAX_QUERY_TERMS = 15
MAX_PAREN_DEPTH = 10


def _now_iso() -> str:
    return datetime.now().isoformat()


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return s


def _join_terms(parts: Sequence[Any]) -> str:
    cleaned = []
    for p in parts:
        s = _clean_str(p)
        if s:
            cleaned.append(s)
    return " | ".join(cleaned)


def _extract_json_terms(raw: Optional[str]) -> str:
    """Safely flattens JSON lists/dicts (rings, materials, anomalies, bio) into searchable text."""
    if not raw or not isinstance(raw, str):
        return ""
    raw_s = raw.strip()
    if not raw_s or raw_s in ("[]", "{}"):
        return ""
    try:
        data = json.loads(raw_s)
    except Exception:
        return raw_s

    tokens: List[str] = []

    def _walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, str):
            s = node.strip()
            if s:
                tokens.append(s)
        elif isinstance(node, (int, float, bool)):
            return
        elif isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, dict):
            for k, v in node.items():
                if k in ("type", "color", "count"):
                    continue
                if isinstance(v, (int, float)) and k not in ("Name", "name", "tag"):
                    # Material dict style: {"iron": 12.3}
                    if not isinstance(k, str) or k in ("Percent", "percent", "InnerRad", "OuterRad", "MassMT"):
                        continue
                    tokens.append(str(k))
                else:
                    _walk(v)

    _walk(data)
    # Deduplicate while preserving order
    seen: Set[str] = set()
    uniq: List[str] = []
    for t in tokens:
        low = t.lower()
        if low not in seen:
            seen.add(low)
            uniq.append(t)
    return " ".join(uniq)


def _has_search_table(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='search_documents'"
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _has_fts5_table(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='search_documents_fts'"
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _collect_documents(
    conn: sqlite3.Connection, system_address: Optional[int] = None
) -> List[Tuple[str, str, int, str, Optional[int], str, str, str, str]]:
    """
    Collects normalized search document tuples:
    (doc_key, category, system_address, star_system, body_id, body_name, title, content, updated_at)
    """
    cur = conn.cursor()
    docs: List[Tuple[str, str, int, str, Optional[int], str, str, str, str]] = []
    now = _now_iso()

    where_sys = "WHERE system_address = ?" if system_address is not None else ""
    params_sys: Tuple[Any, ...] = (system_address,) if system_address is not None else ()

    # Build lookup for system_address -> star_system
    sys_name_map: Dict[int, str] = {}
    cur.execute(f"SELECT * FROM systems {where_sys}", params_sys)
    sys_rows = cur.fetchall()
    for s in sys_rows:
        s_dict = dict(s)
        addr = s_dict["system_address"]
        star_sys = s_dict.get("star_system") or ""
        sys_name_map[addr] = star_sys

        factions_txt = _extract_json_terms(s_dict.get("edsm_factions_json"))
        content = _join_terms([
            star_sys,
            s_dict.get("main_star_type"),
            s_dict.get("system_allegiance"),
            s_dict.get("system_economy"),
            s_dict.get("system_second_economy"),
            s_dict.get("system_government"),
            s_dict.get("system_security"),
            s_dict.get("controlling_faction"),
            s_dict.get("system_state"),
            s_dict.get("system_reserve"),
            s_dict.get("shared_by"),
            s_dict.get("shared_notes"),
            s_dict.get("mining_scout_grade"),
            factions_txt,
        ])
        docs.append((
            f"system:{addr}",
            "system",
            addr,
            star_sys,
            None,
            "",
            star_sys,
            content,
            _clean_str(s_dict.get("last_visited")) or now,
        ))

    def _sys_name(addr: int, fallback: Optional[str] = None) -> str:
        return sys_name_map.get(addr) or (fallback or "")

    # 2. Bodies
    cur.execute(f"SELECT * FROM bodies {where_sys}", params_sys)
    for b in cur.fetchall():
        bd = dict(b)
        addr = bd["system_address"]
        b_id = bd.get("body_id")
        b_name = bd.get("body_name") or ""
        star_sys = _sys_name(addr, bd.get("star_system"))

        rings_txt = _extract_json_terms(bd.get("rings"))
        mats_txt = _extract_json_terms(bd.get("materials"))
        anom_txt = _extract_json_terms(bd.get("anomalies_json"))
        gen_txt = _extract_json_terms(bd.get("confirmed_genuses"))
        pred_txt = _extract_json_terms(bd.get("exobiology_predictions"))

        content = _join_terms([
            star_sys,
            b_name,
            bd.get("star_type"),
            bd.get("luminosity"),
            bd.get("planet_class"),
            bd.get("atmosphere"),
            bd.get("atmosphere_type"),
            bd.get("volcanism"),
            bd.get("terraforming_state"),
            bd.get("reserve_level"),
            rings_txt,
            mats_txt,
            anom_txt,
            gen_txt,
            pred_txt,
        ])
        key_id = b_id if b_id is not None else f"row{bd['id']}"
        docs.append((
            f"body:{addr}:{key_id}",
            "body",
            addr,
            star_sys,
            b_id,
            b_name,
            b_name or star_sys,
            content,
            _clean_str(bd.get("updated_timestamp") or bd.get("scan_timestamp")) or now,
        ))

    # 3. Bookmarks & Markdown Notes
    cur.execute(f"SELECT * FROM body_bookmarks {where_sys}", params_sys)
    for bm in cur.fetchall():
        bmd = dict(bm)
        addr = bmd["system_address"]
        b_id = bmd.get("body_id")
        b_name = bmd.get("body_name") or ""
        star_sys = _sys_name(addr, bmd.get("star_system"))
        alias = _clean_str(bmd.get("alias_name"))
        note = _clean_str(bmd.get("note_markdown"))
        title = f"{alias} ({b_name})" if alias and b_name else (alias or b_name or star_sys)
        content = _join_terms([star_sys, b_name, alias, note])
        docs.append((
            f"bookmark:{addr}:{b_id}",
            "bookmark",
            addr,
            star_sys,
            b_id,
            b_name,
            title,
            content,
            _clean_str(bmd.get("updated_at")) or now,
        ))

    # 4. Scanned Organics (Exobiology)
    cur.execute(f"SELECT * FROM scanned_organics {where_sys}", params_sys)
    for org in cur.fetchall():
        od = dict(org)
        addr = od["system_address"]
        b_id = od.get("body_id")
        b_name = od.get("body_name") or ""
        star_sys = _sys_name(addr)
        title = _clean_str(
            od.get("variant_localised")
            or od.get("species_localised")
            or od.get("species")
            or od.get("genus_localised")
            or od.get("genus")
        ) or b_name or star_sys
        content = _join_terms([
            star_sys,
            b_name,
            od.get("genus"),
            od.get("genus_localised"),
            od.get("species"),
            od.get("species_localised"),
            od.get("variant"),
            od.get("variant_localised"),
            od.get("scan_type"),
        ])
        docs.append((
            f"bio:{od['id']}",
            "bio",
            addr,
            star_sys,
            b_id,
            b_name,
            title,
            content,
            _clean_str(od.get("timestamp")) or now,
        ))

    # 5. Codex Entries
    try:
        cur.execute(f"SELECT * FROM codex_entries {where_sys}", params_sys)
        for ce in cur.fetchall():
            cd = dict(ce)
            addr = cd["system_address"]
            b_id = cd.get("body_id")
            b_name = cd.get("body_name") or ""
            star_sys = _sys_name(addr)
            title = _clean_str(cd.get("name_localised") or cd.get("name")) or star_sys
            content = _join_terms([
                star_sys,
                b_name,
                cd.get("name"),
                cd.get("name_localised"),
                cd.get("category"),
                cd.get("sub_category"),
                cd.get("region_name"),
                cd.get("ggg_variant"),
            ])
            docs.append((
                f"codex:{cd['id']}",
                "codex",
                addr,
                star_sys,
                b_id,
                b_name,
                title,
                content,
                _clean_str(cd.get("timestamp") or cd.get("created_at")) or now,
            ))
    except sqlite3.OperationalError:
        pass

    # 6. Surface Mining Sites
    try:
        cur.execute(f"SELECT * FROM surface_mining_sites {where_sys}", params_sys)
        for ms in cur.fetchall():
            md = dict(ms)
            addr = md["system_address"]
            b_id = md.get("body_id")
            b_name = md.get("body_name") or ""
            star_sys = _sys_name(addr, md.get("star_system"))
            hotspot = _clean_str(md.get("hotspot"))
            title = f"{hotspot} ({b_name})" if hotspot and b_name else (hotspot or b_name or star_sys)
            content = _join_terms([
                star_sys,
                b_name,
                hotspot,
                md.get("minerals"),
                md.get("note"),
            ])
            docs.append((
                f"mining:{md['id']}",
                "mining",
                addr,
                star_sys,
                b_id,
                b_name,
                title,
                content,
                _clean_str(md.get("updated_at")) or now,
            ))
    except sqlite3.OperationalError:
        pass

    # 7. Stations & Settlements
    try:
        cur.execute(f"SELECT * FROM stations {where_sys}", params_sys)
        for st in cur.fetchall():
            sd = dict(st)
            addr = sd["system_address"]
            b_id = sd.get("body_id")
            b_name = sd.get("body_name") or ""
            star_sys = _sys_name(addr)
            st_name = _clean_str(sd.get("station_name"))
            content = _join_terms([
                star_sys,
                b_name,
                st_name,
                sd.get("station_type"),
                sd.get("allegiance"),
                sd.get("economy"),
                sd.get("government"),
                sd.get("controlling_faction"),
            ])
            docs.append((
                f"station:{sd['id']}",
                "station",
                addr,
                star_sys,
                b_id,
                b_name,
                st_name or star_sys,
                content,
                _clean_str(sd.get("updated_at")) or now,
            ))
    except sqlite3.OperationalError:
        pass

    # 8. Astrophysical Physics Reports
    try:
        cur.execute(f"SELECT * FROM system_physics_evaluations {where_sys}", params_sys)
        for pe in cur.fetchall():
            pd = dict(pe)
            addr = pd["system_address"]
            star_sys = _sys_name(addr, pd.get("star_system"))
            anom_txt = _extract_json_terms(pd.get("anomalies_json"))
            content = _join_terms([
                star_sys,
                anom_txt,
                pd.get("narrative_report"),
            ])
            docs.append((
                f"physics:{addr}",
                "physics",
                addr,
                star_sys,
                None,
                "",
                star_sys,
                content,
                _clean_str(pd.get("evaluated_at")) or now,
            ))
    except sqlite3.OperationalError:
        pass

    return docs


_FTS_TRIGGERS_SQL = (
    """
    CREATE TRIGGER IF NOT EXISTS search_docs_ai AFTER INSERT ON search_documents BEGIN
        INSERT INTO search_documents_fts(rowid, title, content)
        VALUES (new.doc_id, new.title, new.content);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_docs_ad AFTER DELETE ON search_documents BEGIN
        INSERT INTO search_documents_fts(search_documents_fts, rowid, title, content)
        VALUES ('delete', old.doc_id, old.title, old.content);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_docs_au AFTER UPDATE ON search_documents BEGIN
        INSERT INTO search_documents_fts(search_documents_fts, rowid, title, content)
        VALUES ('delete', old.doc_id, old.title, old.content);
        INSERT INTO search_documents_fts(rowid, title, content)
        VALUES (new.doc_id, new.title, new.content);
    END;
    """,
)


def rebuild_search_index(conn: sqlite3.Connection) -> int:
    """Rebuilds the entire full-text search index from all database tables."""
    cur = conn.cursor()
    try:
        cur.execute("PRAGMA cache_size = -64000;")
        cur.execute("PRAGMA temp_store = MEMORY;")
    except sqlite3.Error:
        pass

    docs = _collect_documents(conn, system_address=None)
    has_fts = _has_fts5_table(conn)

    if has_fts:
        cur.execute("DROP TRIGGER IF EXISTS search_docs_ai;")
        cur.execute("DROP TRIGGER IF EXISTS search_docs_ad;")
        cur.execute("DROP TRIGGER IF EXISTS search_docs_au;")

    try:
        cur.execute("DELETE FROM search_documents;")
        if docs:
            cur.executemany(
                """
                INSERT INTO search_documents
                (doc_key, category, system_address, star_system, body_id, body_name, title, content, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                docs,
            )
        if has_fts:
            cur.execute("INSERT INTO search_documents_fts(search_documents_fts) VALUES('rebuild');")
    finally:
        if has_fts:
            for trig_sql in _FTS_TRIGGERS_SQL:
                cur.execute(trig_sql)

    conn.commit()
    return len(docs)


def sync_system_search_index(conn: sqlite3.Connection, system_address: int) -> int:
    """Incrementally re-indexes a single star system's search documents."""
    if system_address is None:
        return 0
    docs = _collect_documents(conn, system_address=system_address)
    cur = conn.cursor()
    cur.execute("DELETE FROM search_documents WHERE system_address = ?", (system_address,))
    if docs:
        cur.executemany(
            """
            INSERT OR REPLACE INTO search_documents
            (doc_key, category, system_address, star_system, body_id, body_name, title, content, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            docs,
        )
    conn.commit()
    return len(docs)


def ensure_search_index(conn: sqlite3.Connection) -> None:
    """Builds the search index on-demand if search_documents is empty while systems exist."""
    cur = conn.cursor()
    try:
        doc_count = cur.execute("SELECT COUNT(*) FROM search_documents").fetchone()[0]
        if doc_count == 0:
            sys_count = cur.execute("SELECT COUNT(*) FROM systems").fetchone()[0]
            if sys_count > 0:
                rebuild_search_index(conn)
    except sqlite3.OperationalError:
        pass


_LEX_RE = re.compile(r'(-?)"([^"]*)"|([()])|([^\s()"]+)')


@dataclass(frozen=True)
class _TermNode:
    term: str
    negated: bool = False


@dataclass(frozen=True)
class _NotNode:
    child: Any


@dataclass(frozen=True)
class _AndNode:
    children: Tuple[Any, ...]


@dataclass(frozen=True)
class _OrNode:
    children: Tuple[Any, ...]


def _tokenize_search_query(raw_query: Optional[str]) -> List[Tuple[str, str]]:
    """
    Tokenizes a search query into labeled tokens for boolean expression parsing.
    Respects MAX_QUERY_LEN and MAX_QUERY_TERMS bounds against DoS.
    Quoted strings preserve operators ("OR", "AND") and parens as literal terms.
    """
    if not raw_query or not isinstance(raw_query, str):
        return []
    q = raw_query.replace("\x00", "").strip()[:MAX_QUERY_LEN]
    if not q:
        return []

    tokens: List[Tuple[str, str]] = []
    term_count = 0

    for match in _LEX_RE.finditer(q):
        neg_prefix, quoted, paren, bare = match.groups()
        if paren is not None:
            tokens.append(("LPAREN" if paren == "(" else "RPAREN", paren))
        elif quoted is not None:
            term = quoted.strip()
            if not term:
                continue
            if term_count >= MAX_QUERY_TERMS:
                break
            term_count += 1
            tokens.append(("NEG_TERM" if neg_prefix == "-" else "POS_TERM", term))
        elif bare is not None:
            word = bare.strip()
            if not word:
                continue
            if word == "-":
                tokens.append(("MINUS", "-"))
            elif word.startswith("-") and len(word) > 1:
                if term_count >= MAX_QUERY_TERMS:
                    break
                term_count += 1
                tokens.append(("NEG_TERM", word[1:]))
            elif word.upper() == "OR":
                tokens.append(("OR", "OR"))
            elif word.upper() == "AND":
                tokens.append(("AND", "AND"))
            else:
                if term_count >= MAX_QUERY_TERMS:
                    break
                term_count += 1
                tokens.append(("POS_TERM", word))

    return tokens


class _QueryParser:
    """Fault-tolerant recursive-descent parser for NOT/neg > AND (implicit/explicit) > OR."""

    def __init__(self, tokens: List[Tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.depth = 0

    def _peek(self) -> Optional[Tuple[str, str]]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self) -> Optional[Tuple[str, str]]:
        tok = self._peek()
        if tok is not None:
            self.pos += 1
        return tok

    def _skip_ops(self) -> None:
        while (tok := self._peek()) is not None and tok[0] in ("AND", "OR"):
            self._advance()

    def parse(self) -> Optional[Any]:
        parts: List[Any] = []
        while self._peek() is not None:
            node = self._parse_or()
            if node is not None:
                parts.append(node)
            # Recover gracefully past stray RPAREN or leading/trailing ops
            while (tok := self._peek()) is not None and tok[0] in ("RPAREN", "AND", "OR", "MINUS"):
                self._advance()
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else _AndNode(tuple(parts))

    def _parse_or(self) -> Optional[Any]:
        self._skip_ops()
        first = self._parse_and()
        if first is None:
            return None
        branches = [first]
        while (tok := self._peek()) is not None and tok[0] == "OR":
            self._advance()
            self._skip_ops()
            nxt = self._parse_and()
            if nxt is not None:
                branches.append(nxt)
        return branches[0] if len(branches) == 1 else _OrNode(tuple(branches))

    def _parse_and(self) -> Optional[Any]:
        first = self._parse_factor()
        if first is None:
            return None
        factors = [first]
        while (tok := self._peek()) is not None:
            kind = tok[0]
            if kind in ("OR", "RPAREN"):
                break
            if kind == "AND":
                self._advance()
                while (nxt_tok := self._peek()) is not None and nxt_tok[0] == "AND":
                    self._advance()
                nxt = self._peek()
                if nxt is None or nxt[0] in ("OR", "RPAREN"):
                    break
            factor = self._parse_factor()
            if factor is not None:
                factors.append(factor)
            else:
                break
        return factors[0] if len(factors) == 1 else _AndNode(tuple(factors))

    def _parse_factor(self) -> Optional[Any]:
        while (tok := self._peek()) is not None:
            kind, val = tok
            if kind == "POS_TERM":
                self._advance()
                return _TermNode(val, negated=False)
            if kind == "NEG_TERM":
                self._advance()
                return _TermNode(val, negated=True)
            if kind == "MINUS":
                self._advance()
                nxt = self._peek()
                if nxt is not None and nxt[0] == "LPAREN":
                    sub = self._parse_group()
                    if sub is not None:
                        return _NotNode(sub)
                continue
            if kind == "LPAREN":
                return self._parse_group()
            break
        return None

    def _parse_group(self) -> Optional[Any]:
        self._advance()  # consume LPAREN
        if self.depth >= MAX_PAREN_DEPTH:
            inner = self._parse_or()
        else:
            self.depth += 1
            try:
                inner = self._parse_or()
            finally:
                self.depth -= 1
        if (tok := self._peek()) is not None and tok[0] == "RPAREN":
            self._advance()
        return inner


def _has_positive_term(node: Any) -> bool:
    if node is None:
        return False
    if isinstance(node, _TermNode):
        return not node.negated
    if isinstance(node, _NotNode):
        return False
    if isinstance(node, (_AndNode, _OrNode)):
        return any(_has_positive_term(c) for c in node.children)
    return False


def _normalize_ast(node: Any) -> Optional[Any]:
    if node is None:
        return None
    if isinstance(node, _TermNode):
        return node
    if isinstance(node, _NotNode):
        norm_child = _normalize_ast(node.child)
        return _NotNode(norm_child) if _has_positive_term(norm_child) else None
    if isinstance(node, _AndNode):
        flat: List[Any] = []
        for c in node.children:
            nc = _normalize_ast(c)
            if nc is None:
                continue
            if isinstance(nc, _AndNode):
                flat.extend(nc.children)
            else:
                flat.append(nc)
        if not flat:
            return None
        return flat[0] if len(flat) == 1 else _AndNode(tuple(flat))
    if isinstance(node, _OrNode):
        flat = []
        for c in node.children:
            nc = _normalize_ast(c)
            if nc is None or not _has_positive_term(nc):
                continue
            if isinstance(nc, _OrNode):
                flat.extend(nc.children)
            else:
                flat.append(nc)
        if not flat:
            return None
        return flat[0] if len(flat) == 1 else _OrNode(tuple(flat))
    return None


def _collect_terms(node: Any) -> Tuple[List[str], List[str]]:
    pos: List[str] = []
    neg: List[str] = []
    seen_pos: Set[str] = set()
    seen_neg: Set[str] = set()

    def _walk(n: Any, in_neg: bool) -> None:
        if n is None:
            return
        if isinstance(n, _TermNode):
            is_neg = in_neg or n.negated
            if is_neg:
                if n.term not in seen_neg:
                    seen_neg.add(n.term)
                    neg.append(n.term)
            else:
                if n.term not in seen_pos:
                    seen_pos.add(n.term)
                    pos.append(n.term)
        elif isinstance(n, _NotNode):
            _walk(n.child, True)
        elif isinstance(n, (_AndNode, _OrNode)):
            for c in n.children:
                _walk(c, in_neg)

    _walk(node, False)
    return pos, neg


def parse_search_expression(
    raw_query: Optional[str],
) -> Tuple[Optional[Any], List[str], List[str]]:
    """
    Parses a search query string into (ast_or_none, positive_terms, negative_terms).
    Supports space/AND intersection, OR union, ( ) grouping, "phrase" literals, and -exclusions.
    Returns ast=None if the query contains no positive terms.
    """
    tokens = _tokenize_search_query(raw_query)
    if not tokens:
        return None, [], []
    raw_ast = _QueryParser(tokens).parse()
    pos, neg = _collect_terms(raw_ast)
    norm_ast = _normalize_ast(raw_ast)
    if not _has_positive_term(norm_ast):
        return None, pos, neg
    return norm_ast, pos, neg


def parse_search_query(raw_query: Optional[str]) -> Tuple[List[str], List[str]]:
    """
    Parses a search query string into (positive_terms, negative_terms).
    Supports quoted phrases ("high metal"), boolean AND/OR, ( ) grouping, and -exclusions (-gas).
    Enforces length and term count bounds against DoS.
    """
    _, pos, neg = parse_search_expression(raw_query)
    return pos, neg


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _quote_fts5_term(term: str) -> str:
    escaped = term.replace('"', '""')
    return f'"{escaped}"'


def _find_match_spans(text: str, terms: Sequence[str]) -> List[Tuple[int, int]]:
    if not text or not terms:
        return []
    spans: List[Tuple[int, int]] = []
    for term in terms:
        if not term:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end()))
    if not spans:
        return []
    spans.sort()
    merged: List[Tuple[int, int]] = [spans[0]]
    for start, end in spans[1:]:
        prev_s, prev_e = merged[-1]
        if start <= prev_e:
            merged[-1] = (prev_s, max(prev_e, end))
        else:
            merged.append((start, end))
    return merged


def build_highlighted_html(text: str, terms: Sequence[str]) -> str:
    """Escapes text safely for HTML and wraps matched substrings in <mark> tags."""
    if not text:
        return ""
    spans = _find_match_spans(text, terms)
    if not spans:
        return html.escape(text)
    out: List[str] = []
    pos = 0
    for s, e in spans:
        if s > pos:
            out.append(html.escape(text[pos:s]))
        out.append(f'<mark class="search-hl">{html.escape(text[s:e])}</mark>')
        pos = e
    if pos < len(text):
        out.append(html.escape(text[pos:]))
    return "".join(out)


def build_highlighted_snippet(
    text: str, terms: Sequence[str], max_len: int = 160
) -> str:
    """Extracts a contextual excerpt around the first matched term and safely highlights matches."""
    if not text:
        return ""
    spans = _find_match_spans(text, terms)
    if not spans:
        excerpt = text[:max_len] + ("..." if len(text) > max_len else "")
        return html.escape(excerpt)

    first_s, _ = spans[0]
    win_start = max(0, first_s - 45)
    win_end = min(len(text), win_start + max_len)
    if win_end - win_start < max_len and win_start > 0:
        win_start = max(0, win_end - max_len)

    prefix = "..." if win_start > 0 else ""
    suffix = "..." if win_end < len(text) else ""
    window = text[win_start:win_end]
    return f"{prefix}{build_highlighted_html(window, terms)}{suffix}"


def _doc_like_expr(negated: bool = False) -> str:
    op = "NOT LIKE" if negated else "LIKE"
    return f"LOWER(COALESCE(sd.title, '') || ' ' || COALESCE(sd.content, '')) {op} ? ESCAPE '\\'"


def _compile_doc_node(node: Any, use_fts: bool) -> Tuple[str, List[Any]]:
    """
    Compiles a search AST node into a parameterized SQL predicate over table alias `sd`.
    Combines adjacent FTS5 trigram positive terms inside AND/OR into a single FTS5 MATCH subquery
    and falls back to parameterized LIKE for <3 char terms and exclusions.
    """
    if isinstance(node, _TermNode):
        if not node.negated and use_fts and len(node.term) >= 3:
            return (
                "sd.doc_id IN (SELECT rowid FROM search_documents_fts WHERE search_documents_fts MATCH ?)",
                [_quote_fts5_term(node.term)],
            )
        return _doc_like_expr(negated=node.negated), [f"%{_escape_like(node.term.lower())}%"]

    if isinstance(node, _NotNode):
        c_sql, c_params = _compile_doc_node(node.child, use_fts)
        return f"NOT ({c_sql})", c_params

    if isinstance(node, _AndNode):
        fts_pos = [c for c in node.children if isinstance(c, _TermNode) and not c.negated and use_fts and len(c.term) >= 3]
        others = [c for c in node.children if not (isinstance(c, _TermNode) and not c.negated and use_fts and len(c.term) >= 3)]
        clauses: List[str] = []
        params: List[Any] = []
        if fts_pos:
            fts_expr = " AND ".join(_quote_fts5_term(c.term) for c in fts_pos)
            clauses.append("sd.doc_id IN (SELECT rowid FROM search_documents_fts WHERE search_documents_fts MATCH ?)")
            params.append(fts_expr)
        for oc in others:
            o_sql, o_params = _compile_doc_node(oc, use_fts)
            clauses.append(o_sql)
            params.extend(o_params)
        if len(clauses) == 1:
            return clauses[0], params
        return f"({' AND '.join(clauses)})", params

    if isinstance(node, _OrNode):
        fts_pos = [c for c in node.children if isinstance(c, _TermNode) and not c.negated and use_fts and len(c.term) >= 3]
        others = [c for c in node.children if not (isinstance(c, _TermNode) and not c.negated and use_fts and len(c.term) >= 3)]
        clauses = []
        params = []
        if fts_pos:
            fts_expr = " OR ".join(_quote_fts5_term(c.term) for c in fts_pos)
            clauses.append("sd.doc_id IN (SELECT rowid FROM search_documents_fts WHERE search_documents_fts MATCH ?)")
            params.append(fts_expr)
        for oc in others:
            o_sql, o_params = _compile_doc_node(oc, use_fts)
            clauses.append(o_sql)
            params.extend(o_params)
        if len(clauses) == 1:
            return clauses[0], params
        return f"({' OR '.join(clauses)})", params

    return "1=0", []


def _build_sql_filter(
    conn: sqlite3.Connection,
    ast: Any,
    categories: Optional[List[str]] = None,
) -> Tuple[str, List[Any]]:
    """
    Constructs a hybrid SQL query fragment from a parsed query AST and optional category filter.
    Returns (sql_from_and_where, params).
    """
    use_fts = _has_fts5_table(conn)
    where_clauses: List[str] = []
    params: List[Any] = []

    ast_sql, ast_params = _compile_doc_node(ast, use_fts)
    where_clauses.append(ast_sql)
    params.extend(ast_params)

    if categories:
        valid_cats = [c for c in categories if c in SEARCH_CATEGORIES]
        if valid_cats:
            placeholders = ",".join("?" for _ in valid_cats)
            where_clauses.append(f"sd.category IN ({placeholders})")
            params.extend(valid_cats)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    return f"FROM search_documents sd WHERE {where_sql}", params


def search_fulltext(
    conn: sqlite3.Connection,
    query: str,
    categories: Optional[List[str]] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Executes a full-text search across all indexed exploration data.
    Returns {total, results, category_counts, query, positive_terms, negative_terms}.
    """
    if not _has_search_table(conn):
        return {
            "total": 0,
            "total_unfiltered": 0,
            "results": [],
            "category_counts": {},
            "query": query or "",
            "positive_terms": [],
            "negative_terms": [],
        }
    ensure_search_index(conn)
    ast, pos_terms, neg_terms = parse_search_expression(query)
    if ast is None or not pos_terms:
        return {
            "total": 0,
            "total_unfiltered": 0,
            "results": [],
            "category_counts": {},
            "query": query or "",
            "positive_terms": [],
            "negative_terms": neg_terms,
        }

    limit = min(200, max(1, int(limit)))
    offset = max(0, int(offset))

    # Category facet counts (without category filter)
    base_sql_all, base_params_all = _build_sql_filter(conn, ast, categories=None)
    cur = conn.cursor()
    cat_rows = cur.execute(
        f"SELECT sd.category, COUNT(*) as cnt {base_sql_all} GROUP BY sd.category",
        base_params_all,
    ).fetchall()
    category_counts = {r["category"]: r["cnt"] for r in cat_rows}
    total_unfiltered = sum(category_counts.values())

    # Filtered results
    sql_body, params = _build_sql_filter(conn, ast, categories=categories)
    if categories:
        total = cur.execute(f"SELECT COUNT(*) {sql_body}", params).fetchone()[0]
    else:
        total = total_unfiltered

    # Rank matches against ANY positive term in title higher, then category priority, then updated_at desc
    title_like_sql = " OR ".join("LOWER(COALESCE(sd.title, '')) LIKE ? ESCAPE '\\'" for _ in pos_terms)
    title_like_params = [f"%{_escape_like(t.lower())}%" for t in pos_terms]

    rows = cur.execute(
        f"""
        SELECT sd.doc_id, sd.doc_key, sd.category, sd.system_address, sd.star_system,
               sd.body_id, sd.body_name, sd.title, sd.content, sd.updated_at,
               CASE WHEN ({title_like_sql}) THEN 0 ELSE 1 END as title_rank,
               CASE sd.category
                   WHEN 'bookmark' THEN 1
                   WHEN 'system' THEN 2
                   WHEN 'body' THEN 3
                   WHEN 'bio' THEN 4
                   WHEN 'mining' THEN 5
                   WHEN 'codex' THEN 6
                   WHEN 'station' THEN 7
                   WHEN 'physics' THEN 8
                   ELSE 9
               END as cat_rank
        {sql_body}
        ORDER BY title_rank ASC, cat_rank ASC, sd.updated_at DESC
        LIMIT ? OFFSET ?
        """,
        title_like_params + params + [limit, offset],
    ).fetchall()

    results = []
    for r in rows:
        rd = dict(r)
        results.append({
            "doc_key": rd["doc_key"],
            "category": rd["category"],
            "system_address": rd["system_address"],
            "star_system": rd["star_system"],
            "body_id": rd["body_id"],
            "body_name": rd["body_name"] or "",
            "title": rd["title"],
            "highlighted_title": build_highlighted_html(rd["title"], pos_terms),
            "highlighted_snippet": build_highlighted_snippet(rd["content"], pos_terms),
            "updated_at": rd["updated_at"],
        })

    return {
        "total": total,
        "total_unfiltered": total_unfiltered,
        "results": results,
        "category_counts": category_counts,
        "query": query,
        "positive_terms": pos_terms,
        "negative_terms": neg_terms,
    }


def _single_term_sys_query(use_fts: bool, term: str) -> Tuple[str, List[Any]]:
    if use_fts and len(term) >= 3:
        return (
            "SELECT DISTINCT sd.system_address AS system_address FROM search_documents_fts fts "
            "JOIN search_documents sd ON fts.rowid = sd.doc_id "
            "WHERE search_documents_fts MATCH ?",
            [_quote_fts5_term(term)],
        )
    return (
        "SELECT DISTINCT sd.system_address AS system_address FROM search_documents sd "
        "WHERE LOWER(COALESCE(sd.title, '') || ' ' || COALESCE(sd.content, '')) LIKE ? ESCAPE '\\'",
        [f"%{_escape_like(term.lower())}%"],
    )


def _compile_sys_node(node: Any, use_fts: bool) -> Tuple[str, List[Any], bool]:
    """
    Compiles a query AST into a system_address SQL set expression using INTERSECT / UNION / EXCEPT
    across all documents belonging to each star system.
    Returns (sql, params, is_compound) so SQLite compound precedence is preserved cleanly.
    """
    if isinstance(node, _TermNode):
        sql_s, p_s = _single_term_sys_query(use_fts, node.term)
        return sql_s, p_s, False

    if isinstance(node, _AndNode):
        pos_children = [
            c for c in node.children
            if not (isinstance(c, _NotNode) or (isinstance(c, _TermNode) and c.negated))
        ]
        neg_children = [
            c for c in node.children
            if isinstance(c, _NotNode) or (isinstance(c, _TermNode) and c.negated)
        ]
        parts: List[str] = []
        params: List[Any] = []
        any_compound = False
        for pc in pos_children:
            p_sql, p_params, p_comp = _compile_sys_node(pc, use_fts)
            if p_comp:
                p_sql = f"SELECT system_address FROM ({p_sql})"
            parts.append(p_sql)
            params.extend(p_params)
            any_compound = any_compound or p_comp

        subquery = " INTERSECT ".join(parts)
        is_compound = any_compound or (len(parts) > 1) or bool(neg_children)

        for nc in neg_children:
            if isinstance(nc, _TermNode):
                n_sql, n_params = _single_term_sys_query(use_fts, nc.term)
            else:
                n_sql, n_params, n_comp = _compile_sys_node(nc.child, use_fts)
                if n_comp:
                    n_sql = f"SELECT system_address FROM ({n_sql})"
            subquery = f"{subquery} EXCEPT {n_sql}"
            params.extend(n_params)

        return subquery, params, is_compound

    if isinstance(node, _OrNode):
        parts = []
        params = []
        for c in node.children:
            c_sql, c_params, c_comp = _compile_sys_node(c, use_fts)
            if c_comp:
                c_sql = f"SELECT system_address FROM ({c_sql})"
            parts.append(c_sql)
            params.extend(c_params)
        return " UNION ".join(parts), params, len(parts) > 1

    # Fallback unreachable for valid ASTs
    return "SELECT system_address FROM systems WHERE 1=0", [], False


def build_system_address_subquery(
    conn: sqlite3.Connection, query: str
) -> Optional[Tuple[str, List[Any], List[str], List[str]]]:
    """
    Returns (subquery_sql, params, pos_terms, neg_terms) for filtering systems.system_address IN (...),
    evaluating boolean AND (INTERSECT), OR (UNION), ( ) grouping, and negative EXCEPT across
    all documents belonging to each system.
    Returns None if the search table is missing or the query has no positive terms.
    """
    if not _has_search_table(conn):
        return None
    ensure_search_index(conn)
    ast, pos_terms, neg_terms = parse_search_expression(query)
    if ast is None or not pos_terms:
        return None

    use_fts = _has_fts5_table(conn)
    subquery, params, _ = _compile_sys_node(ast, use_fts)
    return subquery, params, pos_terms, neg_terms


def search_matching_system_addresses(
    conn: sqlite3.Connection, query: str
) -> Optional[Set[int]]:
    """
    Returns matching system_address set for a query (used to enhance /api/systems?q=...).
    Returns None if query has no positive terms.
    """
    sub = build_system_address_subquery(conn, query)
    if sub is None:
        return None
    sub_sql, params, _, _ = sub
    rows = conn.execute(sub_sql, params).fetchall()
    return {r[0] for r in rows}


def safe_sync_system_search_index(conn: sqlite3.Connection, system_address: Optional[int]) -> int:
    """Safely updates search index for a single system without breaking callers if FTS table is absent."""
    if system_address is None:
        return 0
    try:
        return sync_system_search_index(conn, int(system_address))
    except Exception as e:
        print(f"[SearchIndex] Incremental sync warning for {system_address}: {e}")
        return 0

