"""Taxonomia editorial e estrutura narrativa explicaveis da V6.8."""
import re
import unicodedata


MOMENT_LABELS = {
    'humor': 'Humor / momento engraçado',
    'surpresa': 'Surpresa / acontecimento inesperado',
    'jogada': 'Jogada / conquista',
    'tensao': 'Tensão / quase aconteceu',
    'opiniao': 'Opinião / argumento',
    'historia': 'História pessoal / relato',
    'educacional': 'Explicação / aprendizado',
    'emocional': 'Reflexão / momento sensível',
    'reacao': 'Reação do streamer',
    'exploratorio': 'Candidato exploratório · revise',
}

LEXICONS = {
    'reacao': ('meu deus','nao acredito','que isso','caraca','caramba','impossivel',
               'inacreditavel','ta maluco','voce viu','olha isso','no way','oh my god',
               'what the','madre mia','no puede ser'),
    'surpresa': ('que susto','do nada','nao esperava','de repente','plot twist','surpresa',
                 'what just happened','que aconteceu','como assim','wtf'),
    'jogada': ('ganhei','ganhamos','vitoria','clutch','headshot','matei','eliminei',
               'consegui','recorde','campeao','victory','win','ace','mvp','gol'),
    'humor': ('kkkk','hahaha','morri de rir','que vergonha','trolei','troll','bugou',
              'olha esse cara','piada','engracado','funny','lol','lmao'),
    'tensao': ('cuidado','corre','vai vai','calma','socorro','atras','ultimo','agora',
               'quase','nao nao','espera','falta pouco','por um triz'),
    'opiniao': ('eu acho','na minha opiniao','pra mim','eu discordo','eu concordo',
                'o problema e','a verdade e','meu ponto e','i think','in my opinion'),
    'historia': ('aconteceu comigo','quando eu','na epoca','eu lembro','uma vez','minha vida',
                 'minha historia','eu passei','eu estava','years ago','when i was'),
    'educacional': ('como fazer','o segredo','a dica','funciona assim','passo a passo',
                    'voce precisa','aprendi que','o motivo e','por causa disso','tutorial',
                    'a diferenca','presta atencao','this is how','the reason'),
    'emocional': ('foi dificil','eu chorei','me marcou','sou grato','obrigado por tudo',
                  'nao foi facil','tenho medo','sinto falta','mudou minha vida',
                  'orgulho','desabafo','i am grateful','it was hard'),
    'desfecho': ('deu certo','nao deu','acabou','morri','perdi','ganhei','consegui',
                 'foi','era isso','pronto','resultado','no final','finalmente'),
    'gancho': ('voce nao vai acreditar','olha isso','presta atencao','sabia que',
               'o que aconteceu','deixa eu contar','tenho que falar','a verdade e'),
}


def normalize(text):
    value=''.join(c for c in unicodedata.normalize('NFD',str(text).casefold())
                  if unicodedata.category(c)!='Mn')
    return ' '.join(re.findall(r'\w+',value))


def term_hits(text, terms):
    padded=' '+normalize(text)+' '
    return [term for term in terms if ' '+term+' ' in padded]


def text_evidence(text):
    return {kind:term_hits(text,terms) for kind,terms in LEXICONS.items()}


def narrative_scores(early_text,late_text,speech_ratio,*,crescendo=False,corroborated=False,
                     boundary_warning=False,has_outcome=False):
    early=text_evidence(early_text);late=text_evidence(late_text)
    early_words=len(normalize(early_text).split());late_words=len(normalize(late_text).split())
    hook=min(10.0,2.5*bool(early['gancho'] or early['reacao'] or early['surpresa'])+
             1.5*bool(early['opiniao'] or early['historia'])+min(4.5,early_words/5))
    setup=min(10.0,min(5.0,early_words/4)+2.5*bool(early['tensao'] or early['historia'] or early['opiniao'])+
              2.0*min(1,float(speech_ratio)))
    climax=min(10.0,3.0*bool(late['reacao'] or late['jogada'] or late['surpresa'] or late['humor'])+
                2.0*bool(crescendo)+2.5*bool(corroborated)+min(2.5,late_words/6))
    closure=min(10.0,4.5*bool(has_outcome or late['desfecho'])+min(3.0,late_words/5)+
                (0 if boundary_warning else 2.5))
    complete=(hook+setup+climax+closure)/4
    return {key:round(value,1) for key,value in {
        'gancho':hook,'preparacao':setup,'climax':climax,'encerramento':closure,
        'historia_completa':complete}.items()}


def classify_moment(evidence,*,laughs=False,behavior=None,chat=None,crescendo=False,
                    setup_payoff=False,content_mode='live'):
    behavior=behavior or [];chat=chat or []
    cues={item.get('cue') for item in behavior}
    chat_reactions=sum(int(item.get('reactions',0) or 0)+int(item.get('emotes',0) or 0)
                       for item in chat)
    scores={
        'humor':len(evidence['humor'])*3+4*bool(laughs)+2*('sorriso' in cues)+min(3,chat_reactions/3),
        'surpresa':len(evidence['surpresa'])*3+len(evidence['reacao'])*1.5+
                   1.5*len(cues&{'boca_aberta','sobrancelhas_elevadas','olhos_abertos','virada_cabeca'})+
                   1.5*bool(crescendo),
        'jogada':len(evidence['jogada'])*4+2*bool(setup_payoff)+1.5*bool(crescendo),
        'tensao':len(evidence['tensao'])*2.5+2*bool(crescendo)+1.5*bool(setup_payoff),
        'opiniao':len(evidence['opiniao'])*4+(1 if content_mode=='video' else 0),
        'historia':len(evidence['historia'])*4+len(evidence['desfecho'])*1.5+
                   (1 if content_mode=='video' else 0),
        'educacional':len(evidence['educacional'])*4+(1 if content_mode=='video' else 0),
        'emocional':len(evidence['emocional'])*4+
                    1.2*len(cues&{'labios_pressos','sobrancelhas_contraidas','olhos_apertados'}),
        'reacao':len(evidence['reacao'])*3+1.2*len(cues)+min(2,chat_reactions/4),
    }
    ordered=sorted(scores.items(),key=lambda item:(-item[1],item[0]))
    kind,top=ordered[0];second=ordered[1][1]
    if top<=0:
        kind='reacao';top=0
    modalities=sum(bool(value) for value in (
        sum(len(value) for value in evidence.values()), behavior, chat, crescendo))
    confidence=min(.98,.30+min(.42,top/18)+min(.18,modalities*.045)+min(.08,max(0,top-second)/10))
    return {
        'type':kind,
        'label':MOMENT_LABELS[kind],
        'confidence':round(confidence,3),
        'scores':{name:round(value,2) for name,value in scores.items()},
    }


def priority_bonus(priority,moment_type):
    mapping={'reacoes':'reacao','jogadas':'jogada','humor':'humor','surpresa':'surpresa',
             'tensao':'tensao','opiniao':'opiniao','historia':'historia',
             'educacional':'educacional','emocional':'emocional'}
    return 5.0 if mapping.get(priority)==moment_type else 0.0
