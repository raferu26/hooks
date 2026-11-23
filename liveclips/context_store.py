"""Memória de contexto com proveniência (N07, N08, N09, N24, N25, N28).

Tudo aqui é DADO sobre a sessão, nunca instrução: o texto da fala, do chat ou da tela entra como citação e nunca é
interpretado como comando. Cada fato apoiado precisa de pelo menos uma referência de evidência (intervalo + citação).
Registros têm escopo (job, sessão, criador), validade e versão; corrigir um fato marca os dependentes para revisão e
dá para voltar atrás. Sessões e criadores nunca se misturam: toda consulta filtra por sessão (e por criador no escopo
'creator'). O banco é um arquivo próprio (`contexto.sqlite3`), separado do banco principal e do backup editorial.
"""
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

SCOPES = ('job', 'session', 'creator')
FACT_KINDS = ('fato', 'hipotese', 'pergunta_aberta', 'regra_editorial')
FACT_STATUS = ('apoiado', 'hipotese', 'corrigido', 'expirado', 'revisar', 'aberto', 'resolvido')
EVIDENCE_KINDS = ('fala', 'observacao', 'chat', 'confirmacao_humana', 'memoria', 'quadro')
REL_KINDS = ('antes_de', 'prepara', 'responde', 'contradiz', 'retoma', 'resolve', 'confirma', 'possivelmente_associado',
             'causa_declarada')
EPISODE_KINDS = ('promessa', 'tentativa', 'pergunta', 'piada_candidata', 'relato', 'desafio')
EPISODE_STATUS = ('aberto', 'resolvido', 'expirado', 'revisar')
CASE_KINDS = ('approved', 'rejected', 'missed', 'ambiguous')
ERROR_TAXONOMY = (
    'missed_silent_reaction', 'missed_visual_event', 'missing_setup', 'missing_resolution', 'wrong_reference',
    'invented_memory', 'wrong_cause_reaction_link', 'third_party_voice_attribution', 'sound_energy_misread',
    'blink_or_yawn_false_event', 'camera_motion_confound', 'lighting_or_compression_confound',
    'tracking_identity_switch', 'tracking_reacquisition_spike', 'sampling_coverage_overstated',
    'uncalibrated_confidence_presented_as_probability', 'duplicate_candidate', 'new_event_wrongly_deduplicated',
    'queue_starvation', 'capture_gap_hidden', 'chat_misaligned', 'publication_result_uncertain')
MAX_TEXT = 400
# Prazo padrão (s de mídia) para um episódio aberto virar "revisar" se o desfecho não chegar.
DEFAULT_REVIEW_S = 900.0


class ContextError(ValueError):
    pass


def _text(value, limit=MAX_TEXT):
    return ' '.join(str(value or '').split())[:limit]


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def clean_evidence(refs):
    """Valida referências de evidência: tipo conhecido, intervalo finito e citação curta (dado, não instrução)."""
    out = []
    for ref in refs or []:
        if not isinstance(ref, dict) or ref.get('kind') not in EVIDENCE_KINDS:
            raise ContextError('Referência de evidência inválida.')
        try:
            start, end = float(ref['start']), float(ref.get('end', ref['start']))
        except (KeyError, TypeError, ValueError):
            raise ContextError('A evidência precisa de um intervalo de tempo.')
        if not (start == start and end == end) or end < start or start < 0:
            raise ContextError('Intervalo de evidência inválido.')
        item = dict(kind=ref['kind'], start=round(start, 3), end=round(end, 3), quote=_text(ref.get('quote'), 160))
        if ref.get('seq') is not None:
            item['seq'] = int(ref['seq'])
        out.append(item)
    return out


class ContextStore:
    """Persistência SQLite simples; cada operação abre uma conexão curta (seguro entre threads)."""

    def __init__(self, root, clock=time.time):
        self.path = Path(root) / 'contexto.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.lock = threading.RLock()
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS facts(id TEXT PRIMARY KEY, session TEXT, creator TEXT, kind TEXT, text TEXT,
                    status TEXT, scope TEXT, evidence TEXT, valid_from REAL, expires_at REAL, version INTEGER,
                    supersedes TEXT, depends_on TEXT, source TEXT, created REAL, rollback_ref TEXT);
                CREATE INDEX IF NOT EXISTS facts_session ON facts(session, status);
                CREATE TABLE IF NOT EXISTS entities(session TEXT, name TEXT, aliases TEXT, role TEXT, evidence TEXT,
                    PRIMARY KEY(session, name));
                CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY, session TEXT, creator TEXT, kind TEXT, text TEXT,
                    status TEXT, opened REAL, resolved REAL, review_deadline REAL, expect TEXT, evidence TEXT,
                    resolution TEXT, version INTEGER, created REAL, key TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS episodes_key ON episodes(session, key);
                CREATE TABLE IF NOT EXISTS relations(id TEXT PRIMARY KEY, session TEXT, src TEXT, dst TEXT, kind TEXT,
                    temporal_only INTEGER, evidence TEXT, confidence REAL, alternatives TEXT, key TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS relations_key ON relations(session, key);
                CREATE TABLE IF NOT EXISTS history(tbl TEXT, row_id TEXT, version INTEGER, payload TEXT, ts REAL);
                CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, kind TEXT, session TEXT, creator TEXT, payload TEXT,
                    reserved INTEGER, created REAL);
                CREATE TABLE IF NOT EXISTS traces(event_id TEXT, session TEXT, stage TEXT, ts REAL, detail TEXT);
                CREATE INDEX IF NOT EXISTS traces_event ON traces(event_id);
            ''')

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            c.execute('PRAGMA journal_mode=WAL')
            with c:
                yield c
        finally:
            c.close()

    # ---------------------------------------------------------------- fatos e hipóteses
    def add_fact(self, session, kind, text, evidence=None, *, creator='', scope='session', status=None, valid_from=0.0,
                 expires_at=None, depends_on=None, source='sistema', supersedes=None, version=1):
        if kind not in FACT_KINDS:
            raise ContextError('Tipo de registro desconhecido.')
        if scope not in SCOPES:
            raise ContextError('Escopo inválido.')
        refs = clean_evidence(evidence)
        text = _text(text)
        if not text:
            raise ContextError('O registro está vazio.')
        if kind == 'fato' and not refs:
            raise ContextError('Um fato precisa de evidência (intervalo e citação). Sem fonte, registre como hipótese.')
        if scope == 'creator' and not creator:
            raise ContextError('Memória do criador precisa do criador.')
        status = status or {'fato': 'apoiado', 'hipotese': 'hipotese', 'pergunta_aberta': 'aberto', 'regra_editorial': 'apoiado'}[kind]
        if status not in FACT_STATUS:
            raise ContextError('Estado inválido.')
        fid = 'f' + uuid.uuid4().hex[:12]
        with self.lock, self.connect() as c:
            c.execute('INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (fid, session, creator, kind, text, status, scope, _json(refs), float(valid_from),
                       None if expires_at is None else float(expires_at), int(version), supersedes,
                       _json(list(depends_on or [])), _text(source, 40), self.clock(), None))
        return fid

    def get_fact(self, fid):
        with self.connect() as c:
            row = c.execute('SELECT * FROM facts WHERE id=?', (fid,)).fetchone()
        return self._fact(row) if row else None

    @staticmethod
    def _fact(row):
        d = dict(row)
        d['evidence'] = json.loads(d['evidence'] or '[]')
        d['depends_on'] = json.loads(d['depends_on'] or '[]')
        return d

    def facts(self, session, *, creator='', kinds=None, include_inactive=False, at=None):
        """Registros válidos da sessão; do criador só entram os de escopo 'creator' DAQUELE criador."""
        with self.connect() as c:
            rows = c.execute('SELECT * FROM facts WHERE (session=? OR (scope=\'creator\' AND creator=? AND creator!=\'\')) '
                             'ORDER BY created', (session, creator)).fetchall()
        out = []
        for row in rows:
            d = self._fact(row)
            if d['scope'] != 'creator' and d['session'] != session:
                continue
            if kinds and d['kind'] not in kinds:
                continue
            if not include_inactive and d['status'] in ('corrigido', 'expirado'):
                continue
            if at is not None and d['expires_at'] is not None and d['expires_at'] < at:
                continue
            out.append(d)
        return out

    def add_evidence(self, fid, evidence):
        """Evidência nova sustenta uma hipótese; ela só vira fato por confirmação explícita (confirm)."""
        refs = clean_evidence(evidence)
        with self.lock, self.connect() as c:
            row = c.execute('SELECT evidence FROM facts WHERE id=?', (fid,)).fetchone()
            if not row:
                raise ContextError('Registro não encontrado.')
            merged = json.loads(row['evidence'] or '[]') + refs
            c.execute('UPDATE facts SET evidence=? WHERE id=?', (_json(merged), fid))

    def confirm(self, fid, evidence, by='usuario'):
        """Confirmação humana transforma hipótese em fato apoiado, com a confirmação como evidência."""
        item = self.get_fact(fid)
        if not item or item['status'] in ('corrigido', 'expirado'):
            raise ContextError('Registro não encontrado ou inativo.')
        refs = clean_evidence(evidence) or clean_evidence([dict(kind='confirmacao_humana', start=0, quote=f'confirmado por {by}')])
        with self.lock, self.connect() as c:
            self._remember(c, 'facts', fid, item['version'], item)
            c.execute('UPDATE facts SET kind=\'fato\', status=\'apoiado\', evidence=?, version=version+1, source=? WHERE id=?',
                      (_json(item['evidence'] + refs), _text(by, 40), fid))

    def correct_fact(self, fid, text, evidence, why='', by='usuario'):
        """Corrige um fato: o antigo fica 'corrigido', o novo o substitui e quem dependia dele vai para 'revisar'."""
        old = self.get_fact(fid)
        if not old:
            raise ContextError('Registro não encontrado.')
        refs = clean_evidence(evidence) or clean_evidence([dict(kind='confirmacao_humana', start=0, quote=_text(why or 'correção manual', 160))])
        new_id = self.add_fact(old['session'], old['kind'] if old['kind'] != 'pergunta_aberta' else 'hipotese', text, refs,
                               creator=old['creator'], scope=old['scope'], valid_from=old['valid_from'],
                               expires_at=old['expires_at'], depends_on=old['depends_on'], source=_text(by, 40),
                               supersedes=fid, version=old['version'] + 1)
        invalid = []
        with self.lock, self.connect() as c:
            self._remember(c, 'facts', fid, old['version'], old)
            c.execute("UPDATE facts SET status='corrigido', rollback_ref=? WHERE id=?", (new_id, fid))
            for row in c.execute("SELECT id, depends_on FROM facts WHERE session=? AND status NOT IN ('corrigido','expirado')",
                                 (old['session'],)).fetchall():
                if fid in json.loads(row['depends_on'] or '[]'):
                    c.execute("UPDATE facts SET status='revisar' WHERE id=?", (row['id'],))
                    invalid.append(row['id'])
            for row in c.execute('SELECT id, evidence FROM relations WHERE session=? AND (src=? OR dst=?)', (old['session'], fid, fid)).fetchall():
                c.execute('UPDATE relations SET confidence=0 WHERE id=?', (row['id'],))
        return dict(novo=new_id, dependentes_para_revisar=invalid)

    def rollback_fact(self, fid):
        """Desfaz a última correção do fato 'fid' (reativa a versão anterior, descarta a substituta)."""
        item = self.get_fact(fid)
        if not item or item['status'] != 'corrigido' or not item['rollback_ref']:
            raise ContextError('Não há correção para desfazer neste registro.')
        with self.lock, self.connect() as c:
            c.execute("UPDATE facts SET status=?, rollback_ref=NULL WHERE id=?",
                      ('apoiado' if item['kind'] != 'hipotese' else 'hipotese', fid))
            c.execute("UPDATE facts SET status='expirado' WHERE id=?", (item['rollback_ref'],))
            for row in c.execute("SELECT id, depends_on FROM facts WHERE session=? AND status='revisar'", (item['session'],)).fetchall():
                if fid in json.loads(row['depends_on'] or '[]'):
                    c.execute("UPDATE facts SET status='apoiado' WHERE id=?", (row['id'],))
        return fid

    def expire(self, now_media=None):
        """Hipóteses vencidas sem apoio expiram; episódios abertos além do prazo vão para 'revisar' (não esperam para sempre)."""
        wall = self.clock()
        n = 0
        with self.lock, self.connect() as c:
            for row in c.execute("SELECT id, evidence, expires_at FROM facts WHERE status='hipotese' AND expires_at IS NOT NULL").fetchall():
                if row['expires_at'] < wall and len(json.loads(row['evidence'] or '[]')) < 2:
                    c.execute("UPDATE facts SET status='expirado' WHERE id=?", (row['id'],))
                    n += 1
            if now_media is not None:
                n += c.execute("UPDATE episodes SET status='revisar' WHERE status='aberto' AND review_deadline IS NOT NULL AND review_deadline<=?",
                               (float(now_media),)).rowcount
        return n

    # ---------------------------------------------------------------- participantes
    def set_entity(self, session, name, aliases=(), role='', evidence=None):
        name = _text(name, 60)
        if not name:
            raise ContextError('Nome vazio.')
        aliases = sorted({_text(a, 60) for a in aliases if _text(a, 60)})
        with self.lock, self.connect() as c:
            c.execute('INSERT OR REPLACE INTO entities VALUES(?,?,?,?,?)',
                      (session, name, _json(aliases), _text(role, 40), _json(clean_evidence(evidence))))

    def entities(self, session):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM entities WHERE session=? ORDER BY name', (session,)).fetchall()
        return [dict(session=r['session'], name=r['name'], aliases=json.loads(r['aliases']), role=r['role'],
                     evidence=json.loads(r['evidence'])) for r in rows]

    # ---------------------------------------------------------------- episódios e relações
    def upsert_episode(self, session, kind, text, opened, *, key=None, creator='', expect='', evidence=None, review_in=DEFAULT_REVIEW_S):
        """Idempotente por `key`: redetectar o mesmo episódio não duplica nem reabre um resolvido."""
        if kind not in EPISODE_KINDS:
            raise ContextError('Tipo de episódio desconhecido.')
        key = key or hashlib.sha1(f'{kind}|{round(float(opened), 1)}|{_text(text, 80)}'.encode()).hexdigest()[:16]
        with self.lock, self.connect() as c:
            row = c.execute('SELECT id FROM episodes WHERE session=? AND key=?', (session, key)).fetchone()
            if row:
                return row['id'], False
            eid = 'e' + uuid.uuid4().hex[:12]
            c.execute('INSERT INTO episodes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (eid, session, creator, kind, _text(text), 'aberto', float(opened), None, float(opened) + float(review_in),
                       _text(expect), _json(clean_evidence(evidence)), None, 1, self.clock(), key))
        return eid, True

    def resolve_episode(self, eid, resolved_at, resolution, evidence=None, outcome='resolvido'):
        if outcome not in ('resolvido', 'expirado', 'revisar'):
            raise ContextError('Desfecho inválido.')
        with self.lock, self.connect() as c:
            row = c.execute('SELECT * FROM episodes WHERE id=?', (eid,)).fetchone()
            if not row:
                raise ContextError('Episódio não encontrado.')
            self._remember(c, 'episodes', eid, row['version'], dict(row))
            c.execute('UPDATE episodes SET status=?, resolved=?, resolution=?, version=version+1, evidence=? WHERE id=?',
                      (outcome, float(resolved_at), _text(resolution), _json(json.loads(row['evidence'] or '[]') + clean_evidence(evidence)), eid))

    def episodes(self, session, status=None):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM episodes WHERE session=? ORDER BY opened', (session,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['evidence'] = json.loads(d['evidence'] or '[]')
            if status and d['status'] not in ((status,) if isinstance(status, str) else tuple(status)):
                continue
            out.append(d)
        return out

    def add_relation(self, session, src, dst, kind, evidence, *, temporal_only=True, confidence=.5, alternatives=()):
        """Relação temporal é o padrão; 'causa_declarada' só com evidência explícita (nunca por proximidade)."""
        if kind not in REL_KINDS:
            raise ContextError('Relação desconhecida.')
        refs = clean_evidence(evidence)
        if not refs:
            raise ContextError('Uma relação precisa de evidência.')
        if kind == 'causa_declarada':
            temporal_only = False
        key = f'{src}|{dst}|{kind}'
        with self.lock, self.connect() as c:
            row = c.execute('SELECT id FROM relations WHERE session=? AND key=?', (session, key)).fetchone()
            if row:
                return row['id'], False
            rid = 'r' + uuid.uuid4().hex[:12]
            c.execute('INSERT INTO relations VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (rid, session, src, dst, kind, int(bool(temporal_only)), _json(refs), round(float(confidence), 2),
                       _json([_text(a, 120) for a in alternatives]), key))
        return rid, True

    def relations(self, session):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM relations WHERE session=?', (session,)).fetchall()
        return [dict(r, evidence=json.loads(r['evidence']), alternatives=json.loads(r['alternatives'] or '[]'),
                     temporal_only=bool(r['temporal_only'])) for r in rows]

    # ---------------------------------------------------------------- casos de seleção (N25)
    def add_case(self, kind, session, *, creator='', event_refs=(), candidate=None, human_intervals=None, reason='',
                 error_type=None, coverage=None, before_after=(), reserved=None):
        if kind not in CASE_KINDS:
            raise ContextError('Tipo de caso inválido.')
        if error_type is not None and error_type not in ERROR_TAXONOMY:
            raise ContextError('Tipo de erro fora da taxonomia.')
        intervals = []
        for a in human_intervals or []:
            s, e = float(a[0]), float(a[1])
            if not (0 <= s < e):
                raise ContextError('Intervalo humano inválido.')
            intervals.append([round(s, 3), round(e, 3)])
        if kind == 'missed' and not intervals:
            raise ContextError('Um momento perdido precisa do intervalo que a pessoa marcou.')
        payload = dict(case_kind=kind, session_id=session, creator_id=creator, event_refs=list(event_refs),
                       original_candidate_ref=candidate, human_intervals=intervals or None,
                       human_reason_verbatim=_text(reason, 600) or None, error_type=error_type, coverage_at_decision=coverage,
                       before_after_refs=list(before_after), evidence_status='not_evaluated')
        cid = 'c' + uuid.uuid4().hex[:12]
        with self.lock, self.connect() as c:
            c.execute('INSERT INTO cases VALUES(?,?,?,?,?,?,?)', (cid, kind, session, creator, _json(payload),
                                                                  None if reserved is None else int(bool(reserved)), self.clock()))
        return cid

    def cases(self, *, session=None, creator=None, kind=None, reserved=None):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM cases ORDER BY created').fetchall()
        out = []
        for r in rows:
            if session and r['session'] != session or creator and r['creator'] != creator or kind and r['kind'] != kind:
                continue
            if reserved is not None and (r['reserved'] is None or bool(r['reserved']) != reserved):
                continue
            out.append(dict(id=r['id'], reserved=None if r['reserved'] is None else bool(r['reserved']), **json.loads(r['payload'])))
        return out

    def reserve_cases(self, fraction=.3, seed=13):
        """Separa casos para teste (por sessão inteira, nunca partindo uma sessão entre ajuste e teste)."""
        sessions = sorted({r['session_id'] for r in self.cases()})
        ordered = sorted(sessions, key=lambda s: hashlib.sha1(f'{seed}|{s}'.encode()).hexdigest())
        k = max(1, int(round(len(ordered) * fraction))) if len(ordered) > 1 else 0
        test = set(ordered[:k])
        with self.lock, self.connect() as c:
            for s in sessions:
                c.execute('UPDATE cases SET reserved=? WHERE session=?', (int(s in test), s))
        return dict(teste=sorted(test), ajuste=sorted(set(sessions) - test))

    # ---------------------------------------------------------------- rastreio por evento (N28)
    def trace(self, event_id, session, stage, detail=None, ts=None):
        with self.lock, self.connect() as c:
            c.execute('INSERT INTO traces VALUES(?,?,?,?,?)',
                      (event_id, session, _text(stage, 40), self.clock() if ts is None else float(ts), _json(detail or {})))

    def trace_of(self, event_id):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM traces WHERE event_id=? ORDER BY ts', (event_id,)).fetchall()
        return [dict(stage=r['stage'], ts=r['ts'], detail=json.loads(r['detail'])) for r in rows]

    # ---------------------------------------------------------------- interno
    @staticmethod
    def _remember(c, table, row_id, version, payload):
        c.execute('INSERT INTO history VALUES(?,?,?,?,?)', (table, row_id, int(version), _json(payload), time.time()))
