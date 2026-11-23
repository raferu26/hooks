"""Memória editorial persistente (F13, F22, F28, P09, P15, P18).

Dados estruturados em SQLite (arquivo próprio, sobrevive a reinícios). Cada registro tem identidade, escopo, origem,
força da evidência, validade e versões que podem ser revertidas. A recuperação FILTRA antes de comparar texto
(escopo, validade, permissão, tarefa) e devolve pouco contexto com a proveniência. Texto vindo da mídia, do chat ou de
documentos é dado da cena e nunca vira regra. Uma correção pontual fica local; só vira preferência do streamer quando o
usuário pede ("sempre", "para este streamer").
"""
import json
import re
import sqlite3
import time
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path

NAMESPACES = ('fundamentos', 'receitas', 'perfis', 'vocabulario', 'ativos', 'casos_aprovados', 'casos_rejeitados',
              'feedback', 'tendencias', 'trabalho', 'regras')
SCOPES = ('global', 'projeto', 'streamer', 'job')
ORIGINS = ('semente', 'instrucao_explicita', 'correcao_observada', 'avaliacao_humana', 'inferencia')
# Ordem do dossiê (7.9): pedido atual > regra do projeto > perfil confirmado > cena > repertório > tendência.
TIERS = {'job': 0, 'projeto': 1, 'streamer': 2, 'global': 4}
STATUS = ('ativo', 'hipotese', 'revertido', 'expirado')
MAX_TEXT = 600
SCHEMA = 1

ERROR_TAXONOMY = ('contexto_insuficiente', 'payoff_cortado', 'causalidade_alterada', 'fala_truncada', 'crop_incorreto',
                  'rosto_truncado', 'alvo_oculto', 'hud_necessario_oculto', 'texto_ilegivel', 'palavra_incorreta',
                  'legenda_dessincronizada', 'voz_mascarada', 'clipping_introduzido', 'mascara_instavel', 'identidade_trocada',
                  'replay_confuso', 'cor_inconsistente', 'duracao_incorreta', 'render_incompleto')

GENERALIZE = re.compile(r'\b(sempre|nunca mais|toda vez|todo (?:corte|clipe|video)|para (?:este|esse) streamer|desse streamer|'
                        r'deste streamer|em todos)\b', re.I)


def plain(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().casefold()
    return re.sub(r'[^a-z0-9 ]+', ' ', text)


def tokens(value):
    return {t for t in plain(value).split() if len(t) > 2}


def clean_text(value, limit=MAX_TEXT):
    text = ''.join(c for c in str(value or '') if c == '\n' or c >= ' ')
    return ' '.join(text.split())[:limit]


class MemoryError_(ValueError):
    pass


class Memory:
    def __init__(self, root, clock=time.time):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'memoria_editorial.sqlite3'
        self.clock = clock
        with self.connect(True) as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,namespace TEXT,scope TEXT,scope_id TEXT DEFAULT '',
                key TEXT,body TEXT,origin TEXT,evidence TEXT DEFAULT '',confidence REAL DEFAULT .5,
                valid_until REAL,status TEXT DEFAULT 'ativo',version INTEGER DEFAULT 1,supersedes TEXT DEFAULT '',
                tags TEXT DEFAULT '',created REAL,updated REAL,uses INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS idx_rec ON records(namespace,scope,scope_id,key);
            CREATE TABLE IF NOT EXISTS history(record_id TEXT,version INTEGER,body TEXT,status TEXT,origin TEXT,at REAL,reason TEXT);
            CREATE TABLE IF NOT EXISTS usage(job_id TEXT,record_id TEXT,version INTEGER,at REAL,why TEXT);
            CREATE TABLE IF NOT EXISTS conflicts(id INTEGER PRIMARY KEY AUTOINCREMENT,a TEXT,b TEXT,kind TEXT,note TEXT,at REAL);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
            ''')
            c.execute("INSERT OR IGNORE INTO meta VALUES('schema',?)", (str(SCHEMA),))

    @contextmanager
    def connect(self, write=False):
        c = sqlite3.connect(self.path, timeout=20)
        c.row_factory = sqlite3.Row
        try:
            if write:
                c.execute('BEGIN IMMEDIATE')
            yield c
            if write:
                c.commit()
        except Exception:
            if write:
                c.rollback()
            raise
        finally:
            c.close()

    # ───────────── escrita ─────────────

    def put(self, namespace, key, body, origin='instrucao_explicita', scope='global', scope_id='', evidence='',
            confidence=.7, valid_until=None, tags=(), reason='', record_id=None, status=None):
        """Cria ou versiona um registro. Devolve o registro.

        Regras: texto da mídia não é aceito como origem; uma inferência nunca substitui uma instrução explícita
        (vira hipótese e o conflito é registrado); a versão anterior fica no histórico e pode ser restaurada."""
        if namespace not in NAMESPACES:
            raise MemoryError_('Área de memória desconhecida.')
        if scope not in SCOPES:
            raise MemoryError_('Escopo desconhecido.')
        if origin not in ORIGINS:
            raise MemoryError_('Origem não aceita: texto da mídia, do chat ou de documentos é dado da cena, não regra.')
        if scope in ('streamer', 'job') and not scope_id:
            raise MemoryError_('Esse escopo exige um identificador.')
        key = clean_text(key, 120)
        if not key:
            raise MemoryError_('Dê um nome ao registro.')
        body = self._body(body)
        now = self.clock()
        with self.connect(True) as c:
            row = c.execute("SELECT * FROM records WHERE namespace=? AND scope=? AND scope_id=? AND key=? AND status IN ('ativo','hipotese') ORDER BY version DESC LIMIT 1",
                            (namespace, scope, scope_id, key)).fetchone() if not record_id else \
                c.execute('SELECT * FROM records WHERE id=?', (record_id,)).fetchone()
            final_status = status or ('hipotese' if origin == 'inferencia' else 'ativo')
            if row:
                if origin == 'inferencia' and row['origin'] in ('instrucao_explicita', 'avaliacao_humana') and row['status'] == 'ativo':
                    # A inferência não derruba uma regra explícita: guarda como hipótese à parte e registra o conflito.
                    new_id = uuid.uuid4().hex[:12]
                    c.execute('INSERT INTO records(id,namespace,scope,scope_id,key,body,origin,evidence,confidence,valid_until,status,version,tags,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                              (new_id, namespace, scope, scope_id, key + ' (hipótese)', json.dumps(body, ensure_ascii=False), origin, evidence,
                               min(confidence, .4), valid_until, 'hipotese', 1, ','.join(tags), now, now))
                    c.execute('INSERT INTO conflicts(a,b,kind,note,at) VALUES(?,?,?,?,?)',
                              (row['id'], new_id, 'inferencia_x_explicita', 'A regra explícita foi mantida.', now))
                    return self._get(c, new_id)
                version = row['version'] + 1
                c.execute('INSERT INTO history VALUES(?,?,?,?,?,?,?)', (row['id'], row['version'], row['body'], row['status'], row['origin'], now, 'substituído'))
                c.execute('UPDATE records SET body=?,origin=?,evidence=?,confidence=?,valid_until=?,status=?,version=?,tags=?,updated=? WHERE id=?',
                          (json.dumps(body, ensure_ascii=False), origin, evidence, confidence, valid_until, final_status, version, ','.join(tags), now, row['id']))
                self._log(c, row['id'], version, body, final_status, origin, reason or 'atualização')
                return self._get(c, row['id'])
            new_id = record_id or uuid.uuid4().hex[:12]
            c.execute('INSERT INTO records(id,namespace,scope,scope_id,key,body,origin,evidence,confidence,valid_until,status,version,tags,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (new_id, namespace, scope, scope_id, key, json.dumps(body, ensure_ascii=False), origin, evidence, confidence,
                       valid_until, final_status, 1, ','.join(tags), now, now))
            self._log(c, new_id, 1, body, final_status, origin, reason or 'criação')
            return self._get(c, new_id)

    def _log(self, c, record_id, version, body, status, origin, reason):
        c.execute('INSERT INTO history VALUES(?,?,?,?,?,?,?)', (record_id, version, json.dumps(body, ensure_ascii=False), status, origin, self.clock(), reason))

    @staticmethod
    def _body(body):
        if isinstance(body, str):
            body = dict(texto=body)
        if not isinstance(body, dict):
            raise MemoryError_('O conteúdo precisa ser texto ou um objeto.')
        out = {}
        for k, v in body.items():
            k = clean_text(k, 60)
            if isinstance(v, str):
                out[k] = clean_text(v)
            elif isinstance(v, (int, float, bool)) or v is None:
                out[k] = v
            elif isinstance(v, (list, tuple)):
                out[k] = [clean_text(x, 160) if isinstance(x, str) else x for x in list(v)[:40] if isinstance(x, (str, int, float, bool))]
            elif isinstance(v, dict):
                out[k] = {clean_text(a, 60): (clean_text(b, 160) if isinstance(b, str) else b) for a, b in list(v.items())[:30]
                          if isinstance(b, (str, int, float, bool)) or b is None}
        if len(json.dumps(out, ensure_ascii=False)) > 6000:
            raise MemoryError_('O registro é grande demais.')
        return out

    def _get(self, c, record_id):
        row = c.execute('SELECT * FROM records WHERE id=?', (record_id,)).fetchone()
        return self._public(row) if row else None

    @staticmethod
    def _public(row):
        item = dict(row)
        item['body'] = json.loads(item['body'])
        item['tags'] = [t for t in item['tags'].split(',') if t]
        return item

    def get(self, record_id):
        with self.connect() as c:
            return self._get(c, record_id)

    def history(self, record_id):
        with self.connect() as c:
            return [dict(r, body=json.loads(r['body'])) for r in
                    c.execute('SELECT * FROM history WHERE record_id=? ORDER BY version,at', (record_id,))]

    def rollback(self, record_id, version=None):
        """Restaura uma versão anterior (a anterior por padrão). A restauração vira uma nova versão no histórico."""
        with self.connect(True) as c:
            row = c.execute('SELECT * FROM records WHERE id=?', (record_id,)).fetchone()
            if not row:
                raise MemoryError_('Registro não encontrado.')
            wanted = int(version) if version else row['version'] - 1
            old = c.execute('SELECT * FROM history WHERE record_id=? AND version=? ORDER BY at DESC LIMIT 1', (record_id, wanted)).fetchone()
            if not old:
                raise MemoryError_('Não existe essa versão anterior.')
            new_version = row['version'] + 1
            c.execute('UPDATE records SET body=?,status=?,origin=?,version=?,updated=? WHERE id=?',
                      (old['body'], 'ativo' if old['status'] != 'hipotese' else 'hipotese', old['origin'], new_version, self.clock(), record_id))
            self._log(c, record_id, new_version, json.loads(old['body']), old['status'], old['origin'], f'revertido para a versão {wanted}')
            return self._get(c, record_id)

    def forget(self, record_id):
        with self.connect(True) as c:
            row = c.execute('SELECT * FROM records WHERE id=?', (record_id,)).fetchone()
            if not row:
                raise MemoryError_('Registro não encontrado.')
            c.execute("UPDATE records SET status='revertido',updated=? WHERE id=?", (self.clock(), record_id))
            self._log(c, record_id, row['version'], json.loads(row['body']), 'revertido', row['origin'], 'esquecido pelo usuário')

    def purge_job(self, job_id):
        """Memória de trabalho de um job: apagada ao final; nada dela vira fato em outro job."""
        with self.connect(True) as c:
            c.execute("DELETE FROM records WHERE namespace='trabalho' AND scope='job' AND scope_id=?", (job_id,))

    def expire(self):
        now = self.clock()
        with self.connect(True) as c:
            n = c.execute("UPDATE records SET status='expirado' WHERE status IN ('ativo','hipotese') AND valid_until IS NOT NULL AND valid_until<?", (now,)).rowcount
        return n

    # ───────────── recuperação ─────────────

    def retrieve(self, job, limit=8, namespaces=None, record_use=True):
        """Poucas memórias relevantes, com proveniência.

        `job`: dict(job_id, streamer, task, text, destination, tool_version). Filtra primeiro (status, validade, escopo,
        permissão de ativo, tarefa), depois ordena por camada de precedência e semelhança. Inclui um contraexemplo útil."""
        now = self.clock()
        streamer = job.get('streamer') or ''
        want = tokens(' '.join([str(job.get('task') or ''), str(job.get('text') or '')]))
        with self.connect() as c:
            rows = [self._public(r) for r in c.execute("SELECT * FROM records WHERE status IN ('ativo') AND (valid_until IS NULL OR valid_until>=?)", (now,))]
        picked = []
        for item in rows:
            if namespaces and item['namespace'] not in namespaces:
                continue
            if item['namespace'] == 'trabalho' and not (item['scope'] == 'job' and item['scope_id'] == job.get('job_id')):
                continue
            if item['scope'] == 'streamer' and item['scope_id'] != streamer:
                continue            # preferência de um criador nunca vaza para outro
            if item['scope'] == 'job' and item['scope_id'] != job.get('job_id'):
                continue
            if item['namespace'] == 'ativos' and job.get('destination'):
                if job['destination'] not in (item['body'].get('destinos') or []):
                    continue        # disponível numa plataforma não é autorizado em todas
            task = item['body'].get('tarefas')
            if task and job.get('task') and job['task'] not in task:
                continue
            tier = TIERS[item['scope']] + (3 if item['namespace'] == 'tendencias' else 0)
            hay = tokens(item['key'] + ' ' + json.dumps(item['body'], ensure_ascii=False) + ' ' + ' '.join(item['tags']))
            sim = len(want & hay) / (len(want | hay) or 1) if want else 0.0
            picked.append((tier, -sim, -item['confidence'], item['updated'] * -1, item))
        picked.sort(key=lambda x: x[:4])
        chosen = []
        taken = set()
        for tier, neg, _, _, item in picked:
            if len(chosen) >= limit:
                break
            if want and neg == 0 and tier >= 4:
                continue                    # repertório sem relação com o pedido não entra no contexto
            if item['scope'] != 'global' and (item['scope'], item['key']) in taken:
                continue
            taken.add((item['scope'], item['key']))
            chosen.append(self._cite(item, tier, -neg))
        if not any(c['kind'] == 'contraexemplo' for c in chosen):
            for tier, neg, _, _, item in picked:
                if item['namespace'] in ('casos_rejeitados',) or item['body'].get('contraexemplo'):
                    if any(c['id'] == item['id'] for c in chosen):
                        continue
                    if want and neg == 0:
                        continue
                    chosen.append(self._cite(item, tier, -neg, counter=True))
                    break
        if record_use and job.get('job_id') and chosen:
            with self.connect(True) as c:
                for ref in chosen:
                    c.execute('INSERT INTO usage VALUES(?,?,?,?,?)', (job['job_id'], ref['id'], ref['version'], now, ref['why']))
                    c.execute('UPDATE records SET uses=uses+1 WHERE id=?', (ref['id'],))
        return chosen

    @staticmethod
    def _cite(item, tier, sim, counter=False):
        why = ['escopo ' + item['scope'], 'origem ' + item['origin']]
        if sim:
            why.append(f'semelhança {sim:.2f}')
        return dict(id=item['id'], version=item['version'], namespace=item['namespace'], key=item['key'], scope=item['scope'],
                    origin=item['origin'], body=item['body'], confidence=item['confidence'], tier=tier,
                    kind='contraexemplo' if counter else 'regra', why=', '.join(why))

    def used_by(self, job_id):
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT record_id,version,why FROM usage WHERE job_id=? ORDER BY at', (job_id,))]

    # ───────────── perfis, vocabulário, ativos, tendências ─────────────

    def streamer_prefs(self, streamer):
        """Preferências confirmadas do streamer, resolvidas por precedência (a mais forte ganha)."""
        with self.connect() as c:
            rows = [self._public(r) for r in c.execute("SELECT * FROM records WHERE namespace='perfis' AND status='ativo' AND ((scope='streamer' AND scope_id=?) OR scope IN ('projeto','global'))", (streamer,))]
        rows.sort(key=lambda r: (TIERS[r['scope']], ORIGINS.index(r['origin']) if r['origin'] != 'inferencia' else 9))
        out = {}
        for item in rows:
            out.setdefault(item['key'], item['body'].get('valor', item['body']))
        return out

    def set_pref(self, streamer, key, value, origin='instrucao_explicita', evidence='', reason=''):
        return self.put('perfis', key, dict(valor=value), origin=origin, scope='streamer', scope_id=streamer, evidence=evidence,
                        confidence=.9 if origin == 'instrucao_explicita' else .5, reason=reason)

    def vocabulary(self, streamer):
        """Termos do canal (nomes, jogos, bordões) para a legenda. Só grafia: nunca troca o que foi dito."""
        with self.connect() as c:
            rows = [self._public(r) for r in c.execute("SELECT * FROM records WHERE namespace='vocabulario' AND status='ativo' AND ((scope='streamer' AND scope_id=?) OR scope IN ('projeto','global'))", (streamer,))]
        return sorted({clean_text(r['body'].get('termo') or r['key'], 60) for r in rows})

    def add_vocabulary(self, streamer, term, origin='instrucao_explicita'):
        term = clean_text(term, 60)
        if not term:
            raise MemoryError_('Termo vazio.')
        return self.put('vocabulario', term, dict(termo=term), origin=origin, scope='streamer', scope_id=streamer)

    def register_asset(self, asset_id, kind, destinos, licenca='', credit='', valid_until=None, descricao=''):
        """Ativo com permissão por destino. Sem destino declarado, não é autorizado em lugar nenhum."""
        return self.put('ativos', asset_id, dict(tipo=kind, destinos=list(destinos), licenca=licenca, credito=credit, descricao=descricao),
                        origin='instrucao_explicita', evidence='declarado pelo usuário', valid_until=valid_until, tags=(kind,))

    def asset_allowed(self, asset_id, destination):
        with self.connect() as c:
            row = c.execute("SELECT * FROM records WHERE namespace='ativos' AND key=? AND status='ativo' AND (valid_until IS NULL OR valid_until>=?)",
                            (asset_id, self.clock())).fetchone()
        return bool(row) and destination in (json.loads(row['body']).get('destinos') or [])

    def add_trend(self, platform, niche, pattern, expires_at, region='BR', url='', observed_at=None, strength='exploratoria'):
        """Tendência SEMPRE com validade. Frequência observada ≠ prova de dominância no feed."""
        if not expires_at or expires_at <= self.clock():
            raise MemoryError_('Tendência precisa de uma data de validade futura.')
        return self.put('tendencias', f'{platform}/{niche}: {clean_text(pattern, 60)}',
                        dict(plataforma=platform, nicho=niche, regiao=region, padrao=pattern, url=url,
                             observado_em=observed_at or self.clock(), forca=strength, representativa=False),
                        origin='avaliacao_humana', scope='global', valid_until=expires_at, tags=(platform, niche), confidence=.4)

    # ───────────── aprendizado por correção (S03) ─────────────

    def learn(self, job_id, streamer, change, user_text='', before_ref='', after_ref='', scope_hint=None):
        """Registra uma correção humana.

        `change`: dict(kind, detail) — ex. kind='restaurar_pausa'. Sem pedido explícito de generalizar, fica como
        caso LOCAL (escopo job + registro de feedback). Com "sempre"/"para este streamer", vira preferência do
        streamer, com a fala do usuário preservada. Sem motivo declarado, o motivo vira hipótese de baixa força."""
        user_text = clean_text(user_text)
        explicit = bool(GENERALIZE.search(user_text)) or scope_hint == 'streamer'
        reason = user_text or None
        feedback = self.put('feedback', f'{job_id}:{change.get("kind")}:{uuid.uuid4().hex[:6]}',
                            dict(job=job_id, streamer=streamer, mudanca=change, fala_do_usuario=reason, antes=before_ref, depois=after_ref,
                                 motivo_declarado=bool(reason)),
                            origin='correcao_observada' if not explicit else 'instrucao_explicita', scope='job', scope_id=job_id,
                            evidence='diferença entre planos', confidence=.5)
        result = dict(feedback=feedback['id'], preference=None, hypothesis=None)
        if explicit and streamer:
            pref = self.set_pref(streamer, f'regra:{change.get("kind")}', dict(detalhe=change.get('detail'), fala=reason),
                                 evidence='pedido explícito do usuário', reason='generalizado a pedido')
            result['preference'] = pref['id']
        elif not reason:
            hyp = self.put('feedback', f'hipotese:{change.get("kind")}:{job_id}', dict(mudanca=change, nota='motivo não informado; força baixa'),
                           origin='inferencia', scope='job', scope_id=job_id, confidence=.2)
            result['hypothesis'] = hyp['id']
        return result

    def add_case(self, approved, situation, summary, streamer='', plan_ref='', reason='', defects=(), reserved=False):
        """Caso de ensino. `reserved`: separado para avaliação, nunca usado como exemplo de treino/recuperação."""
        for d in defects:
            if d not in ERROR_TAXONOMY:
                raise MemoryError_(f'Defeito fora da taxonomia: {d}')
        ns = 'casos_aprovados' if approved else 'casos_rejeitados'
        return self.put(ns, f'{situation}:{clean_text(summary, 50)}', dict(situacao=situation, resumo=summary, motivo=reason,
                                                                          defeitos=list(defects), plano=plan_ref, reservado=bool(reserved),
                                                                          contraexemplo=not approved),
                        origin='avaliacao_humana', scope='streamer' if streamer else 'global', scope_id=streamer,
                        tags=(situation,), confidence=.8)

    # ───────────── semente e diagnóstico ─────────────

    def seed(self, fundamentals, recipes=()):
        """Carrega os fundamentos e receitas do dossiê (idempotente). Não são aprendizado: são repertório declarado."""
        added = 0
        for item in fundamentals:
            with self.connect() as c:
                exists = c.execute('SELECT 1 FROM records WHERE id=?', (item['id'],)).fetchone()
            if exists:
                continue
            body = {k: v for k, v in item.items() if k != 'id'}
            self.put('fundamentos', item['concept'] if 'concept' in item else item['id'], body, origin='semente', scope='global',
                     evidence=item.get('evidence', 'dossie_2026_11_18'), confidence=.6, record_id=item['id'],
                     tags=tuple(plain(item.get('concept', '')).split()[:3]))
            added += 1
        for item in recipes:
            with self.connect() as c:
                exists = c.execute('SELECT 1 FROM records WHERE id=?', (item['id'],)).fetchone()
            if exists:
                continue
            self.put('receitas', f"{item['id']} {item['nome']}", dict(estado=item['status'], fallback=item['fallback'], nota=item['nota']),
                     origin='semente', scope='global', evidence='registro de capacidades', confidence=.8, record_id=item['id'],
                     tags=(item['status'],))
            added += 1
        return added

    def stats(self):
        with self.connect() as c:
            by = {r['namespace']: r['n'] for r in c.execute("SELECT namespace,COUNT(*) n FROM records WHERE status IN ('ativo','hipotese') GROUP BY namespace")}
            conflicts = c.execute('SELECT COUNT(*) FROM conflicts').fetchone()[0]
            cases = c.execute("SELECT COUNT(*) FROM records WHERE namespace IN ('casos_aprovados','casos_rejeitados') AND status='ativo'").fetchone()[0]
        return dict(por_area=by, conflitos=conflicts, casos=cases)

    def conflicts(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM conflicts ORDER BY at DESC LIMIT 50')]

    def list(self, namespace=None, scope_id=None, status=('ativo', 'hipotese'), limit=200):
        q = 'SELECT * FROM records WHERE status IN (%s)' % ','.join('?' * len(status))
        args = list(status)
        if namespace:
            q += ' AND namespace=?'
            args.append(namespace)
        if scope_id is not None:
            q += " AND (scope_id=? OR scope IN ('global','projeto'))"
            args.append(scope_id)
        with self.connect() as c:
            return [self._public(r) for r in c.execute(q + ' ORDER BY updated DESC LIMIT ?', (*args, limit))]
