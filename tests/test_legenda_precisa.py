import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from liveclips import captions
from liveclips.app import App
from liveclips.engine import Engine
from liveclips.store import Store,DEFAULT_PROFILE,profile_checked


def word(text,start,end,p=None):
    w=dict(text=text,start=start,end=end)
    if p is not None:w['p']=p
    return w


class CorrectionRuleTests(unittest.TestCase):
    def test_rules_accept_the_usual_arrows_and_ignore_broken_lines(self):
        rules=captions.parse_corrections('kringa => Coringa\nvalo rant -> Valorant\nfoo → Foo\nbar = Bar\nsem seta\n => vazio\nalgo =>')
        self.assertEqual([r[1] for r in rules],['Valorant','Coringa','Foo','Bar'])
        self.assertEqual(rules[0][0],['valo','rant'])

    def test_single_word_is_replaced_keeping_punctuation_and_timing(self):
        words,changes=captions.apply_corrections([word('Kringa,',1.0,1.4,.6),word('fez',1.4,1.7)],'kringa => Coringa')
        self.assertEqual([w['text'] for w in words],['Coringa,','fez'])
        self.assertEqual((words[0]['start'],words[0]['end'],words[0]['p']),(1.0,1.4,.6))
        self.assertEqual(changes,[dict(de='Kringa,',para='Coringa',time=1.0)])

    def test_several_words_become_one_spanning_the_whole_phrase(self):
        words,_=captions.apply_corrections([word('o',0,.2),word('valo',.2,.5,.9),word('rant.',.5,.9,.4),word('é',.9,1)],'valo rant => Valorant')
        self.assertEqual([w['text'] for w in words],['o','Valorant.','é'])
        self.assertEqual((words[1]['start'],words[1]['end'],words[1]['p']),(.2,.9,.4))

    def test_accents_and_case_do_not_matter_for_matching(self):
        words,_=captions.apply_corrections([word('INCRÍVEL',0,1)],'incrivel => incrível')
        self.assertEqual(words[0]['text'],'incrível')

    def test_longer_rule_wins_and_unmatched_text_is_untouched(self):
        words,_=captions.apply_corrections([word('go',0,.1),word('ro',.1,.2),word('go',.2,.3)],'go => Gol\ngo ro => Coringa')
        self.assertEqual([w['text'] for w in words],['Coringa','Gol'])
        same,changes=captions.apply_corrections([word('nada',0,1)],'kringa => Coringa')
        self.assertEqual((same[0]['text'],changes),('nada',[]))

    def test_corrections_reach_the_caption_lines_and_the_subtitle_file(self):
        seg=[dict(start=0,end=2,text='o kringa fez',words=[dict(word='o',start=0,end=.5),dict(word='kringa',start=.5,end=1.2),dict(word='fez',start=1.2,end=2)])]
        lines,fixes=captions.lines_from_transcript(seg,0,2,'',corrections='kringa => Coringa')
        self.assertIn('Coringa',' '.join(l['text'] for l in lines))
        self.assertEqual(fixes[0]['para'],'Coringa')
        ass=captions.make_ass(seg,0,2,46,260,'00E8FF','dynamic',smart=True,corrections='kringa => Coringa')
        self.assertIn('Coringa',ass);self.assertNotIn('kringa',ass.lower())

    def test_profile_keeps_rules_trimmed_and_limited(self):
        profile=profile_checked(dict(DEFAULT_PROFILE,corrections='  kringa   =>  Coringa \n\n\x00\nfoo=>Foo'))
        self.assertEqual(profile['corrections'],'kringa => Coringa\nfoo=>Foo')
        self.assertLessEqual(len(profile_checked(dict(DEFAULT_PROFILE,corrections='a=>b\n'*2000))['corrections']),3000)


class MigrationTests(unittest.TestCase):
    def test_old_profiles_turn_precise_captions_on_once_and_respect_a_later_choice(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        store=Store(temp.name)
        sid=store.create_streamer('ANTIGO')
        with store.connect(True) as c:   # perfil como o das versões antigas, com a 2ª passagem desligada por padrão
            c.execute('UPDATE streamers SET profile=? WHERE id=?',(json.dumps(dict(DEFAULT_PROFILE,second_pass='off')),sid))
            c.execute("DELETE FROM settings WHERE key='migracao_0_17_legenda_precisa'")
        reopened=Store(temp.name)
        self.assertEqual(reopened.streamer(sid)['profile']['second_pass'],'small')
        profile=dict(reopened.streamer(sid)['profile'],second_pass='off')
        reopened.save_profile(sid,profile)
        again=Store(temp.name)
        self.assertEqual(again.streamer(sid)['profile']['second_pass'],'off')

    def test_new_streamers_start_with_precise_captions(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        store=Store(temp.name);sid=store.create_streamer('NOVO')
        self.assertEqual(store.streamer(sid)['profile']['second_pass'],'small')


class SpareModelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.engine=Engine(self.store)
        self.loaded=[]
        outer=self
        class Fake:
            def __init__(self,name,**kw):outer.loaded.append(name);self.name=name
        self.fake=types.SimpleNamespace(WhisperModel=Fake)
        self.profile=dict(DEFAULT_PROFILE,threads=2,whisper_device='cpu')

    def test_alternating_between_live_and_precise_models_loads_each_only_once(self):
        with patch.dict(sys.modules,{'faster_whisper':self.fake}):
            first=self.engine.get_model(self.profile,'base')
            second=self.engine.get_model(self.profile,'small')
            for _ in range(3):
                self.assertIs(self.engine.get_model(self.profile,'base'),first)
                self.assertIs(self.engine.get_model(self.profile,'small'),second)
        self.assertEqual(self.loaded,['base','small'])

    def test_large_models_are_not_kept_in_memory_next_to_another(self):
        with patch.dict(sys.modules,{'faster_whisper':self.fake}):
            self.engine.get_model(self.profile,'base')
            self.engine.get_model(self.profile,'medium')
            self.engine.get_model(self.profile,'base')
        self.assertEqual(self.loaded,['base','medium','base'])


class RefineCooldownTests(unittest.TestCase):
    def setUp(self):
        from tests.helpers import setup_session,candidate
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=App(self.temp.name,worker=False);self.addCleanup(self.app.close)
        _,sid,_=setup_session(self.app.store,durations=(120,))
        item,_=candidate(self.app.store,sid,10,40);self.id=item['id']
        with self.app.store.connect(True) as c:c.execute("UPDATE candidates SET status='approved' WHERE id=?",(self.id,))
        self.calls=[]
        self.app.engine.do_refine=lambda cid,name=None:self.calls.append(cid) or False

    def export(self):
        self.app.engine.do_render(self.id,False)

    def test_export_runs_the_precise_pass_first(self):
        self.export()
        self.assertEqual(self.calls,[self.id])

    def test_a_recent_failure_makes_the_export_skip_it(self):
        import time
        self.app.engine.refine_failed_at=time.time()
        self.export()
        self.assertEqual(self.calls,[])

    def test_an_old_failure_is_forgotten(self):
        import time
        self.app.engine.refine_failed_at=time.time()-601
        self.export()
        self.assertEqual(self.calls,[self.id])


if __name__=='__main__':unittest.main()
